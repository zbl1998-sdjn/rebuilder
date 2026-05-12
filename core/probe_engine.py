"""
Probe Engine: Systematically explore the behavior of a black-box executable.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional, Set

from core.data_models import (
    BehaviorSample,
    CLISurface,
    FlagSpec,
    ArgSpec,
    TestCase,
    TestResult,
)
from core.evidence import EvidenceRecorder, EvidenceStore
from core.evidence.models import test_case_fingerprint
from core.llm_output import extract_json_value
from core.probing.file_io import FileIOProbePlanner
from core.probing.shell_init import ShellInitProbePlanner
from core.probing.stateful import StatefulProbePlanner, StatefulProbeRunner
from llm_clients.base import BaseLLMClient, Message
from llm_clients.options import configured_max_tokens
from utils.executable import SandboxExecutor


class ProbeEngine:
    """Structured black-box exploration of an executable."""
    
    SYSTEM_PROMPT = """You are a security researcher performing structured black-box analysis of an executable.
Your goal is to generate diverse test inputs to understand the program's behavior.
You must output ONLY a JSON list of test cases. Each test case must have:
- "name": string description
- "args": list of command line arguments
- "stdin": string input to stdin (if applicable)
- "input_files": dict of filename -> file content
- "description": what behavior this aims to probe

Be creative: test happy paths, edge cases, invalid inputs, boundary conditions, and error modes."""
    
    def __init__(
        self,
        executable: Path,
        documentation: str,
        llm_client: BaseLLMClient,
        max_iterations: int = 50,
        min_samples: int = 0,
        timeout: float = 10.0,
        evidence_store: EvidenceStore | None = None,
        executor_backend=None,
    ):
        self.executable = executable if executor_backend else Path(executable)
        self.documentation = documentation
        self.llm = llm_client
        self.max_iterations = max_iterations
        self.min_samples = max(0, int(min_samples))
        self.timeout = timeout
        self.executor = SandboxExecutor(executable, timeout, backend=executor_backend)
        self.evidence_recorder = (
            EvidenceRecorder(executable, evidence_store, timeout=timeout, backend=executor_backend)
            if evidence_store
            else None
        )
        self.corpus: List[BehaviorSample] = []
        self.cli_surface = CLISurface()
        self.seen_tests: Set[str] = set()
    
    async def probe(self) -> List[BehaviorSample]:
        """Run the full probing pipeline."""
        # Phase 1: Discover CLI surface from --help and docs
        await self._probe_cli_surface()
        await self._probe_shell_init_outputs()
        await self._probe_file_io_side_effects()
        await self._probe_stateful_plans()
        
        # Phase 2: Generate and run behavioral tests via LLM-guided fuzzing
        for iteration in range(self.max_iterations):
            if self.min_samples and len(self.corpus) >= self.min_samples:
                break
            test_cases = await self._generate_test_cases(iteration)
            if not test_cases:
                break
            for tc in test_cases:
                await self._run_test(tc)
        
        # Phase 3: Systematic edge case probing
        await self._probe_edge_cases()

        # Phase 4: Deterministic supplemental probes for official-gated runs.
        await self._probe_minimum_corpus()
         
        return self.corpus

    async def _probe_stateful_plans(self):
        """Run documented multi-step probes in a shared state directory."""
        plans = StatefulProbePlanner().plan(self.documentation)
        if not plans:
            return
        runner = StatefulProbeRunner(
            executable=self.executable,
            backend=self.executor.backend,
            timeout=self.timeout,
        )
        for plan in plans:
            self.corpus.extend(await runner.run_plan(plan))

    async def _probe_shell_init_outputs(self):
        """Capture full documented shell initialization scripts."""
        for tc in ShellInitProbePlanner().plan(self.documentation):
            tags = ["shell_init", "full_output"]
            if len(tc.args) >= 2:
                tags.append(f"shell:{tc.args[1]}")
            result = await self._execute_test(tc, tags=tags)
            sample_tags = list(tags)
            if result.exit_code != 0:
                sample_tags.append("error_mode")
            self.corpus.append(
                BehaviorSample(
                    test_case=tc,
                    observed_result=result,
                    tags=sample_tags,
                )
            )

    async def _probe_file_io_side_effects(self):
        """Capture documented file input/output behavior and side effects."""
        for tc in FileIOProbePlanner().plan(self.documentation, self.cli_surface):
            result = await self._execute_test(tc, tags=["file_io", "side_effect"])
            tags = ["file_io", "side_effect"]
            if result.exit_code != 0:
                tags.append("error_mode")
            if result.output_files:
                tags.append("file_output")
            self.corpus.append(
                BehaviorSample(
                    test_case=tc,
                    observed_result=result,
                    tags=tags,
                )
            )
    
    async def _probe_cli_surface(self):
        """Try common CLI discovery commands."""
        discovery_commands = [
            TestCase(name="help_long", args=["--help"], description="Discover CLI via --help"),
            TestCase(name="help_short", args=["-h"], description="Discover CLI via -h"),
            TestCase(name="version", args=["--version"], description="Check version flag"),
            TestCase(name="no_args", args=[], description="Run with no arguments"),
        ]
        for tc in discovery_commands:
            result = await self._execute_test(tc, tags=["cli_discovery"])
            self.corpus.append(BehaviorSample(test_case=tc, observed_result=result, tags=["cli_discovery"]))
            
            # Simple parsing of --help output
            help_text = "\n".join(part for part in [result.stdout, result.stderr] if part)
            if "--" in help_text:
                self._parse_help_output(help_text)
    
    def _parse_help_output(self, text: str):
        """Naive parser to extract flags from help text."""
        import re
        for line in text.splitlines():
            for m in re.finditer(r"(--[\w-]+)(?:\s+([A-Z_]+))?", line):
                flag_name = m.group(1)
                type_hint = m.group(2) or "bool"
                if not any(f.name == flag_name for f in self.cli_surface.flags):
                    self.cli_surface.flags.append(
                        FlagSpec(name=flag_name, type_hint=type_hint.lower(), description=line.strip())
                    )
    
    async def _generate_test_cases(self, iteration: int) -> List[TestCase]:
        """Use LLM to generate the next batch of test cases based on observed behavior so far."""
        # Build a summary of what we've learned so far
        observation_summary = self._build_observation_summary()
        
        messages = [
            self.llm.system_prompt(self.SYSTEM_PROMPT),
            self.llm.user_prompt(
                f"Program documentation:\n{self.documentation}\n\n"
                f"CLI surface discovered so far:\n{self.cli_surface.model_dump_json(indent=2)}\n\n"
                f"Observations so far ({len(self.corpus)} samples):\n{observation_summary}\n\n"
                f"Iteration {iteration + 1}/{self.max_iterations}. "
                f"Generate 5-10 new test cases that probe UNCOVERED behavior. "
                f"Output ONLY a JSON array of test cases."
            ),
        ]
        
        resp = await self.llm.chat(
            messages,
            temperature=0.7,
            max_tokens=min(configured_max_tokens(self.llm, 4096), 4096),
        )
        return self._parse_test_cases(resp.content)
    
    def _parse_test_cases(self, text: str) -> List[TestCase]:
        """Parse LLM output into TestCase objects."""
        try:
            data = extract_json_value(text.strip())
            if isinstance(data, dict) and "test_cases" in data:
                data = data["test_cases"]
            if not isinstance(data, list):
                return []

            cases = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                tc = TestCase(
                    name=item.get("name", "unnamed"),
                    args=item.get("args", []),
                    stdin=item.get("stdin", ""),
                    input_files=item.get("input_files", {}),
                    description=item.get("description", ""),
                )
                # Deduplicate by hash
                fingerprint = test_case_fingerprint(tc)
                if fingerprint not in self.seen_tests:
                    self.seen_tests.add(fingerprint)
                    cases.append(tc)
            return cases
        except ValueError:
            return []
    
    async def _run_test(self, tc: TestCase):
        """Execute a test case and store the result."""
        result = await self._execute_test(tc, tags=["generated"])
        tags = ["generated"]
        if result.exit_code != 0:
            tags.append("error_mode")
        if result.timeout_triggered:
            tags.append("timeout")
        self.corpus.append(BehaviorSample(test_case=tc, observed_result=result, tags=tags))

    async def _execute_test(self, tc: TestCase, tags: List[str]) -> TestResult:
        """Run a test case and optionally persist its reference-executable evidence."""
        if self.evidence_recorder:
            result, _record = await self.evidence_recorder.run_and_record(tc, tags=tags)
            return result
        return await self.executor.run(tc)
    
    async def _probe_edge_cases(self):
        """Systematically probe known edge case categories."""
        edge_cases = [
            TestCase(name="empty_stdin", args=[], stdin="", description="Empty stdin handling"),
            TestCase(name="large_input", args=[], stdin="x" * 10000, description="Large input handling"),
            TestCase(name="unicode_input", args=[], stdin="你好世界 🌍 émoji", description="Unicode handling"),
            TestCase(name="binary_garbage", args=[], stdin="\x00\x01\x02\xff", description="Binary input handling"),
            TestCase(name="special_chars", args=[], stdin="'; DROP TABLE -- \"\\n", description="Special character injection"),
        ]
        for tc in edge_cases:
            await self._run_test(tc)

    async def _probe_minimum_corpus(self):
        """Add deterministic, cleanroom-safe probes until the corpus reaches min_samples."""
        if len(self.corpus) >= self.min_samples:
            return
        for tc in self._supplemental_test_cases():
            if len(self.corpus) >= self.min_samples:
                break
            fingerprint = test_case_fingerprint(tc)
            if fingerprint in self.seen_tests:
                continue
            self.seen_tests.add(fingerprint)
            result = await self._execute_test(tc, tags=["supplemental"])
            tags = ["supplemental"]
            if result.exit_code != 0:
                tags.append("error_mode")
            if result.output_files:
                tags.append("file_output")
            self.corpus.append(BehaviorSample(test_case=tc, observed_result=result, tags=tags))

    def _supplemental_test_cases(self) -> list[TestCase]:
        json_text = '{"name":"alice","nums":[1,2],"nested":{"ok":true}}\n'
        cases = [
            TestCase(name="supplemental_stdin_object", args=[], stdin=json_text, description="Valid JSON object on stdin"),
            TestCase(name="supplemental_stdin_array", args=[], stdin='[{"a":1},{"b":2}]\n', description="Valid JSON array on stdin"),
            TestCase(name="supplemental_stdin_scalar", args=[], stdin='"value"\n', description="Valid JSON scalar on stdin"),
            TestCase(name="supplemental_stdin_null", args=[], stdin="null\n", description="JSON null on stdin"),
            TestCase(name="supplemental_stdin_malformed", args=[], stdin="{not-json}\n", description="Malformed stdin"),
            TestCase(name="supplemental_dash_stdin", args=["-"], stdin=json_text, description="Explicit stdin marker"),
            TestCase(
                name="supplemental_file_json",
                args=["input.json"],
                input_files={"input.json": json_text.encode("utf-8")},
                description="Read JSON-like input from a file",
            ),
        ]
        for flag in sorted(self.cli_surface.flags, key=lambda item: item.name):
            value = self._sample_flag_value(flag.name, flag.type_hint, flag.description)
            flag_args = [flag.name] if value is None else [flag.name, value]
            cases.append(
                TestCase(
                    name=f"supplemental_flag_{flag.name.lstrip('-').replace('-', '_')}",
                    args=flag_args,
                    stdin=json_text,
                    description=f"Probe discovered flag {flag.name}",
                )
            )
            cases.append(
                TestCase(
                    name=f"supplemental_flag_{flag.name.lstrip('-').replace('-', '_')}_dash",
                    args=[*flag_args, "-"],
                    stdin=json_text,
                    description=f"Probe discovered flag {flag.name} with explicit stdin",
                )
            )
        return cases

    def _sample_flag_value(self, flag_name: str, type_hint: str, description: str) -> str | None:
        text = f"{flag_name} {type_hint} {description}".lower()
        if type_hint not in {"bool", ""}:
            return "1"
        if any(token in text for token in ["proxy", "noproxy"]):
            return "http://127.0.0.1:9"
        if any(token in text for token in ["file", "path", "output", "input"]):
            return "input.json"
        if any(token in text for token in ["count", "length", "skip", "size", "width", "number"]):
            return "1"
        return None
    
    def _build_observation_summary(self) -> str:
        """Create a concise summary of observed behaviors for the LLM."""
        lines = []
        for i, sample in enumerate(self.corpus[-20:]):  # Last 20 observations
            tc = sample.test_case
            res = sample.observed_result
            lines.append(
                f"[{i}] args={tc.args} -> exit={res.exit_code}, "
                f"stdout_len={len(res.stdout)}, stderr_len={len(res.stderr)}, "
                f"tags={sample.tags}"
            )
        return "\n".join(lines)
