"""
Repair Loop: Diagnose failures and generate repair strategies.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from core.data_models import ArchitectureBlueprint, DiffReport, RepairStrategy, ProgramSpec, Codebase
from core.evidence.models import test_case_json_payload
from core.prompting.behavior_contracts import (
    behavior_contract_prompt,
    spec_prompt_dict,
    spec_prompt_json,
)
from core.llm_output import extract_json_object
from core.repair.clustering import FailureCluster
from llm_clients.base import BaseLLMClient, Message
from llm_clients.options import configured_max_tokens


class RepairLoop:
    """Diagnose differential test failures and produce repair strategies."""
    
    SYSTEM_PROMPT = """You are a debugging expert analyzing behavioral differences between an original program and its replacement.
Given a failure report, diagnose the root cause and propose a precise repair strategy.

Output a JSON object:
- "strategy_type": One of ["fix_exit_code", "fix_output_format", "fix_file_handling", "fix_algorithm", "add_edge_case", "refactor"]
- "description": Detailed explanation of what went wrong and how to fix it
- "target_files": List of files that likely need modification
- "hints": Specific guidance for the implementer (e.g., "Sort output before printing", "Handle empty input by returning exit code 1")

Be specific and actionable."""
    
    def __init__(self, llm_client: BaseLLMClient):
        self.llm = llm_client
    
    async def diagnose(
        self,
        diff: DiffReport,
        spec: ProgramSpec,
        codebase: Codebase,
    ) -> RepairStrategy:
        """Diagnose a single failure and produce repair strategy."""
        
        # Build context
        context = {
            "failure": {
                "test_case": test_case_json_payload(diff.test_case),
                "original_stdout": diff.original_result.stdout[:500],
                "replacement_stdout": diff.replacement_result.stdout[:500],
                "original_stderr": diff.original_result.stderr[:300],
                "replacement_stderr": diff.replacement_result.stderr[:300],
                "original_exit": diff.original_result.exit_code,
                "replacement_exit": diff.replacement_result.exit_code,
                "stdout_match": diff.stdout_match,
                "stderr_match": diff.stderr_match,
                "exit_code_match": diff.exit_code_match,
            },
            "spec": spec_prompt_dict(spec),
            "existing_files": list(codebase.files.keys()),
        }
        
        messages = [
            self.llm.system_prompt(self.SYSTEM_PROMPT),
            self.llm.user_prompt(
                f"Failure context:\n{json.dumps(context, indent=2, ensure_ascii=False)}\n\n"
                f"{behavior_contract_prompt(spec)}"
                f"Diagnose and propose repair strategy as JSON."
            ),
        ]
        
        resp = await self.llm.chat(
            messages,
            temperature=0.3,
            max_tokens=configured_max_tokens(self.llm, 4096),
        )
        return self._parse_strategy(resp.content)

    async def diagnose_cluster(
        self,
        cluster: FailureCluster,
        spec: ProgramSpec,
        codebase: Codebase,
    ) -> RepairStrategy:
        """Diagnose a related group of exploration failures."""
        context = {
            "failure_cluster": {
                "kind": cluster.kind.value,
                "count": len(cluster.reports),
                "representatives": [
                    self._diff_summary(report)
                    for report in cluster.reports[:5]
                ],
            },
            "spec": spec_prompt_dict(spec),
            "existing_files": list(codebase.files.keys()),
        }

        messages = [
            self.llm.system_prompt(self.SYSTEM_PROMPT),
            self.llm.user_prompt(
                f"Failure context:\n{json.dumps(context, indent=2, ensure_ascii=False)}\n\n"
                f"{behavior_contract_prompt(spec)}"
                f"Diagnose the shared root cause and propose one repair strategy as JSON."
            ),
        ]

        resp = await self.llm.chat(
            messages,
            temperature=0.3,
            max_tokens=configured_max_tokens(self.llm, 4096),
        )
        return self._parse_strategy(resp.content)

    def _diff_summary(self, diff: DiffReport) -> dict:
        return {
            "test_case": test_case_json_payload(diff.test_case),
            "original_stdout": diff.original_result.stdout[:500],
            "replacement_stdout": diff.replacement_result.stdout[:500],
            "original_stderr": diff.original_result.stderr[:300],
            "replacement_stderr": diff.replacement_result.stderr[:300],
            "original_exit": diff.original_result.exit_code,
            "replacement_exit": diff.replacement_result.exit_code,
            "stdout_match": diff.stdout_match,
            "stderr_match": diff.stderr_match,
            "exit_code_match": diff.exit_code_match,
            "file_outputs_match": diff.file_outputs_match,
        }
    
    def _parse_strategy(self, text: str) -> RepairStrategy:
        import re
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"```(?:json)?\s*", "", text).replace("```", "")
        
        try:
            data = extract_json_object(text)
            hints = data.get("hints", "")
            if isinstance(hints, list):
                hints = "\n".join(str(item) for item in hints)
            elif not isinstance(hints, str):
                hints = json.dumps(hints, ensure_ascii=False)
            return RepairStrategy(
                strategy_type=data.get("strategy_type", "fix_algorithm"),
                description=data.get("description", ""),
                target_files=data.get("target_files", []),
                hints=hints,
            )
        except json.JSONDecodeError:
            return RepairStrategy(
                strategy_type="fix_algorithm",
                description="Failed to parse strategy. Raw output: " + text[:500],
                hints="Review the implementation against the specification.",
            )
    
    async def apply_repair(
        self,
        strategy: RepairStrategy,
        codebase: Codebase,
        spec: ProgramSpec,
    ) -> Codebase:
        """Apply a repair strategy by regenerating affected files."""
        
        # Read current content of target files
        file_context = {}
        for fname in strategy.target_files:
            if fname in codebase.files:
                file_context[fname] = codebase.files[fname]
        
        messages = [
            self.llm.system_prompt(
                "You are editing source code to fix a behavioral mismatch. "
                "Output the complete corrected files in the same format: --- FILE: path --- content --- END FILE ---"
            ),
            self.llm.user_prompt(
                f"Repair strategy: {strategy.description}\n\n"
                f"Hints: {strategy.hints}\n\n"
                f"Specification:\n{spec_prompt_json(spec)}\n\n"
                f"{behavior_contract_prompt(spec)}"
                f"Current files to modify:\n{json.dumps(file_context, indent=2)}\n\n"
                f"Apply the fix and output the corrected files."
            ),
        ]
        
        resp = await self.llm.chat(
            messages,
            temperature=0.2,
            max_tokens=configured_max_tokens(self.llm, 8192),
        )
        
        # Re-parse files from response
        from core.implementer_agent import ImplementerAgent
        parser = ImplementerAgent(self.llm)
        new_codebase = parser._parse_codebase(
            resp.content,
            ArchitectureBlueprint(language=codebase.language),  # type: ignore
            codebase.root_path,
        )
        
        # Merge: keep non-target files, update target files
        merged_files = dict(codebase.files)
        for fname, content in new_codebase.files.items():
            merged_files[fname] = content
        
        return Codebase(
            root_path=codebase.root_path,
            language=codebase.language,
            files=merged_files,
            build_script=new_codebase.build_script or codebase.build_script,
            executable_path=new_codebase.executable_path or codebase.executable_path,
            generation_metadata={**codebase.generation_metadata, "repair_applied": strategy.strategy_type},
        )
