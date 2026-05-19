"""
Implementer Agent: Generate actual source code based on architecture blueprint and spec.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Dict

from core.codebase.integrity import CodebaseIntegrityChecker, CodebaseIntegrityIssue
from core.codebase.runtime_smoke import PythonRuntimeSmokeChecker
from core.data_models import ProgramSpec, ArchitectureBlueprint, Codebase
from core.implementation.contract_assets import (
    PythonContractAssetInjector,
    STATIC_ASSET_POLICY_NAME,
)
from core.implementation.entrypoint import (
    determine_executable,
    expected_entry_point,
    normalize_output_path,
    python_entry_path,
)
from core.implementation.output_parser import parse_codebase
from core.implementation.output_writer import (
    clear_output_sources,
    write_files,
    write_unparseable_output,
)
from core.implementation.prompts import (
    IMPLEMENTER_SYSTEM_PROMPT,
    ENTRYPOINT_SYSTEM_PROMPT,
    SUPPORT_SYSTEM_PROMPT,
    static_asset_generation_guard,
    contract_prompt,
    build_entrypoint_messages,
    build_support_messages,
    build_retry_messages,
)
from core.prompting.behavior_contracts import spec_prompt_json
from llm_clients.base import BaseLLMClient
from llm_clients.options import configured_max_tokens


class ImplementerAgent:
    """Generate complete source code for each module in the architecture."""

    SYSTEM_PROMPT = IMPLEMENTER_SYSTEM_PROMPT
    ENTRYPOINT_SYSTEM_PROMPT = ENTRYPOINT_SYSTEM_PROMPT
    SUPPORT_SYSTEM_PROMPT = SUPPORT_SYSTEM_PROMPT

    def __init__(
        self,
        llm_client: BaseLLMClient,
        enable_static_output_assets: bool = True,
    ):
        self.llm = llm_client
        self.enable_static_output_assets = enable_static_output_assets

    async def implement(
        self,
        spec: ProgramSpec,
        blueprint: ArchitectureBlueprint,
        output_dir: Path,
    ) -> Codebase:
        """Generate the complete codebase."""
        if self._should_use_python_staging(blueprint):
            return await self._implement_python_staged(spec, blueprint, output_dir)
        return await self._implement_single_pass(spec, blueprint, output_dir)

    def _should_use_python_staging(self, blueprint: ArchitectureBlueprint) -> bool:
        return blueprint.language.lower() == "python" and bool(blueprint.modules)

    async def _implement_single_pass(
        self,
        spec: ProgramSpec,
        blueprint: ArchitectureBlueprint,
        output_dir: Path,
    ) -> Codebase:
        messages = [
            self.llm.system_prompt(self.SYSTEM_PROMPT + static_asset_generation_guard(spec, self.enable_static_output_assets)),
            self.llm.user_prompt(
                f"Specification:\n{spec_prompt_json(spec)}\n\n"
                f"{contract_prompt(spec, self.enable_static_output_assets)}"
                f"Architecture Blueprint:\n{blueprint.model_dump_json(indent=2)}\n\n"
                f"Generate all source files and the build script. "
                f"Use language: {blueprint.language}."
            ),
        ]
        resp = await self.llm.chat(
            messages,
            temperature=0.2,
            max_tokens=configured_max_tokens(self.llm, 8192),
        )
        codebase = self._parse_codebase(resp.content, blueprint, output_dir)
        integrity_issues = await self._find_generation_issues(codebase, blueprint, spec)
        if not codebase.files or integrity_issues:
            retry_reason = "unparseable_initial_output" if not codebase.files else "integrity_issues"
            retry = await self._retry_implementation(
                spec=spec,
                blueprint=blueprint,
                initial_output=resp.content,
                integrity_issues=integrity_issues,
            )
            self._clear_output_sources(output_dir)
            codebase = self._parse_codebase(retry.content, blueprint, output_dir)
            codebase.generation_metadata = {
                **codebase.generation_metadata,
                "implementation_retry": retry_reason,
                "initial_output_chars": len(resp.content),
            }
        else:
            codebase.generation_metadata["integrity_issues"] = []
        return self._apply_contract_assets(spec, blueprint, codebase)

    async def _implement_python_staged(
        self,
        spec: ProgramSpec,
        blueprint: ArchitectureBlueprint,
        output_dir: Path,
    ) -> Codebase:
        entry_resp = await self.llm.chat(
            self._entrypoint_messages(spec, blueprint),
            temperature=0.2,
            max_tokens=configured_max_tokens(self.llm, 8192),
        )
        entry_codebase = self._parse_codebase(entry_resp.content, blueprint, output_dir)
        entry_issues = await self._find_generation_issues(entry_codebase, blueprint, spec)
        if not entry_codebase.files or entry_issues:
            retry = await self._retry_implementation(
                spec=spec,
                blueprint=blueprint,
                initial_output=entry_resp.content,
                integrity_issues=entry_issues,
            )
            self._clear_output_sources(output_dir)
            entry_codebase = self._parse_codebase(retry.content, blueprint, output_dir)
            entry_codebase.generation_metadata = {
                **entry_codebase.generation_metadata,
                "implementation_strategy": "python_staged",
                "entrypoint_stage_retry": True,
                "initial_output_chars": len(entry_resp.content),
            }
            entry_issues = await self._find_generation_issues(entry_codebase, blueprint, spec)
            if entry_issues:
                fallback = await self._implement_single_pass(spec, blueprint, output_dir)
                fallback.generation_metadata = {
                    **fallback.generation_metadata,
                    "implementation_strategy": "python_staged_fallback_single_pass",
                    "entrypoint_stage_retry_failed_issues": [
                        issue.message for issue in entry_issues
                    ],
                }
                return fallback

        entry_codebase.generation_metadata = {
            **entry_codebase.generation_metadata,
            "implementation_strategy": "python_staged",
            "entrypoint_stage_files": sorted(entry_codebase.files),
        }
        if not entry_codebase.files:
            entry_codebase.generation_metadata["module_stage_status"] = "skipped_no_entrypoint"
            return entry_codebase

        module_resp = await self.llm.chat(
            self._support_messages(spec, blueprint, entry_codebase),
            temperature=0.2,
            max_tokens=configured_max_tokens(self.llm, 8192),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            module_codebase = self._parse_codebase(
                module_resp.content,
                blueprint,
                Path(tmpdir),
            )

        if not module_codebase.files:
            write_unparseable_output(output_dir, module_resp.content)
            entry_codebase.generation_metadata["module_stage_status"] = "rejected_no_files"
            return self._apply_contract_assets(spec, blueprint, entry_codebase)

        merged_files = dict(entry_codebase.files)
        merged_files.update(module_codebase.files)
        merged = Codebase(
            root_path=output_dir,
            language=blueprint.language,
            files=merged_files,
            build_script=module_codebase.build_script or entry_codebase.build_script,
            generation_metadata={
                **entry_codebase.generation_metadata,
                "module_stage_files": sorted(module_codebase.files),
                "module_stage_status": "accepted",
            },
        )
        merged.executable_path = determine_executable(output_dir, blueprint, merged.build_script)
        module_issues = await self._find_generation_issues(merged, blueprint, spec)
        if module_issues:
            entry_codebase.generation_metadata["module_stage_status"] = "rejected_integrity"
            entry_codebase.generation_metadata["module_stage_issues"] = [
                issue.message for issue in module_issues
            ]
            self._clear_output_sources(output_dir)
            write_files(output_dir, entry_codebase.files)
            return self._apply_contract_assets(spec, blueprint, entry_codebase)

        self._clear_output_sources(output_dir)
        write_files(output_dir, merged.files)
        merged.executable_path = determine_executable(output_dir, blueprint, merged.build_script)
        return self._apply_contract_assets(spec, blueprint, merged)

    def _apply_contract_assets(
        self,
        spec: ProgramSpec,
        blueprint: ArchitectureBlueprint,
        codebase: Codebase,
    ) -> Codebase:
        if blueprint.language.lower() != "python":
            return codebase
        if not self.enable_static_output_assets:
            codebase.generation_metadata.update(
                {
                    "static_output_assets_enabled": False,
                    "contract_asset_policy": STATIC_ASSET_POLICY_NAME,
                    "contract_asset_status": "disabled",
                    "contract_asset_count": 0,
                }
            )
            return codebase
        return PythonContractAssetInjector().apply(
            spec=spec,
            codebase=codebase,
            entry_point=self._expected_entry_point(blueprint),
        )

    def _entrypoint_messages(self, spec: ProgramSpec, blueprint: ArchitectureBlueprint):
        return build_entrypoint_messages(self.llm, spec, blueprint, self.enable_static_output_assets)

    def _support_messages(self, spec: ProgramSpec, blueprint: ArchitectureBlueprint, entry_codebase: Codebase):
        return build_support_messages(self.llm, spec, blueprint, entry_codebase, self.enable_static_output_assets)

    async def _find_generation_issues(
        self,
        codebase: Codebase,
        blueprint: ArchitectureBlueprint,
        spec: ProgramSpec,
    ) -> list[CodebaseIntegrityIssue]:
        entry_point = self._expected_entry_point(blueprint)
        issues = CodebaseIntegrityChecker().find_issues(codebase, entry_point=entry_point)
        if issues:
            return issues
        smoke_report = await PythonRuntimeSmokeChecker().check(
            codebase,
            entry_point=entry_point,
            behavior_contracts=spec.behavior_contracts,
        )
        codebase.generation_metadata["runtime_smoke"] = smoke_report.metadata
        return smoke_report.issues

    async def _retry_implementation(self, spec, blueprint, initial_output, integrity_issues):
        msgs = build_retry_messages(
            self.llm, spec, blueprint, initial_output, integrity_issues,
            self.enable_static_output_assets,
        )
        return await self.llm.chat(msgs, temperature=0.0, max_tokens=configured_max_tokens(self.llm, 8192))

    # ------------------------------------------------------------------
    # Delegate wrappers — keep private API for backward-compat with tests
    # ------------------------------------------------------------------

    def _parse_codebase(
        self, text: str, blueprint: ArchitectureBlueprint, output_dir: Path
    ) -> Codebase:
        return parse_codebase(text, blueprint, output_dir)

    def _clear_output_sources(self, output_dir: Path) -> None:
        clear_output_sources(output_dir)

    def _write_unparseable_output(self, output_dir: Path, text: str) -> None:
        write_unparseable_output(output_dir, text)

    def _write_files(self, output_dir: Path, files: Dict[str, str]) -> None:
        write_files(output_dir, files)

    def _determine_executable(
        self, output_dir: Path, blueprint: ArchitectureBlueprint, build_script: str | None
    ) -> Path | None:
        return determine_executable(output_dir, blueprint, build_script)

    def _expected_entry_point(self, blueprint: ArchitectureBlueprint) -> str | None:
        return expected_entry_point(blueprint)

    def _python_entry_path(self, blueprint: ArchitectureBlueprint) -> str:
        return python_entry_path(blueprint)

    def _normalize_output_path(self, raw_path: str) -> str | None:
        return normalize_output_path(raw_path)
