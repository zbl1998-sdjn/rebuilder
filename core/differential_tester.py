"""
Differential Tester: Compare original and replacement executable behavior.
"""

from __future__ import annotations

import asyncio
import logging
import random
import tempfile
from collections import OrderedDict
from pathlib import Path
from typing import List, Optional

from core.data_models import (
    BehaviorSample,
    DiffReport,
    TestCase,
    TestResult,
)
from core.execution.files import UnsafeInputFilePathError, safe_input_file_names
from core.llm_output import parse_llm_test_cases
from llm_clients.base import BaseLLMClient, Message
from llm_clients.options import configured_max_tokens
from utils.executable import SandboxExecutor

log = logging.getLogger(__name__)


class DifferentialTester:
    """Test behavioral equivalence between original and replacement programs."""
    
    def __init__(
        self,
        original: Path,
        replacement: Path,
        llm_client: Optional[BaseLLMClient] = None,
        max_test_cases: int = 200,
        original_backend=None,
        replacement_backend=None,
        max_concurrency: int = 8,
    ):
        self.original = original
        self.replacement = replacement
        self.llm = llm_client
        self.max_test_cases = max_test_cases
        self.max_concurrency = max(1, int(max_concurrency))
        self.orig_executor = SandboxExecutor(original, backend=original_backend)
        self.repl_executor = SandboxExecutor(replacement, backend=replacement_backend)
    
    async def compare(self, test_case: TestCase) -> DiffReport:
        """Run both executables with the same input and compare results."""
        orig_result = await self.orig_executor.run(test_case)
        repl_result = await self.repl_executor.run(test_case)
        
        stdout_match = self._streams_equivalent(orig_result.stdout, repl_result.stdout)
        stderr_match = self._streams_equivalent(orig_result.stderr, repl_result.stderr)
        exit_code_match = (orig_result.exit_code == repl_result.exit_code)
        file_outputs_match = self._files_equivalent(
            orig_result.output_files, repl_result.output_files
        )
        
        return DiffReport(
            test_case=test_case,
            original_result=orig_result,
            replacement_result=repl_result,
            stdout_match=stdout_match,
            stderr_match=stderr_match,
            exit_code_match=exit_code_match,
            file_outputs_match=file_outputs_match,
            timing_similar=True,  # Could be stricter
        )
    
    async def run_full_suite(
        self,
        behavior_corpus: List[BehaviorSample],
    ) -> List[DiffReport]:
        """Run differential tests on all observed behaviors plus generated adversarial cases.

        Non-stateful samples run concurrently under `max_concurrency`. Stateful
        sequences keep step-order within a plan and a shared workdir, but
        distinct plans may run in parallel. Output order matches the historical
        contract: regular samples first, then stateful groups in insertion
        order, then adversarial cases.
        """
        semaphore = asyncio.Semaphore(self.max_concurrency)

        behavior_corpus = [
            sample
            for sample in behavior_corpus
            if not self._has_unsafe_input_files(sample.test_case)
        ]
        regular_samples, stateful_groups = self._split_stateful_samples(behavior_corpus)

        regular_reports = await asyncio.gather(*[
            self._compare_with_limit(sample.test_case, semaphore)
            for sample in regular_samples
        ])

        stateful_reports_per_group = await asyncio.gather(*[
            self._compare_stateful_sequence(group, semaphore=semaphore)
            for group in stateful_groups.values()
        ])

        reports: List[DiffReport] = list(regular_reports)
        for group_reports in stateful_reports_per_group:
            reports.extend(group_reports)

        if self.llm:
            try:
                adversarial = await self._generate_adversarial_tests(reports)
            except Exception as exc:
                log.warning("Skipping adversarial test generation after LLM failure: %s", exc)
                adversarial = []
            adversarial = [
                tc for tc in adversarial if not self._has_unsafe_input_files(tc)
            ]
            adversarial_reports = await asyncio.gather(*[
                self._compare_with_limit(tc, semaphore) for tc in adversarial
            ])
            reports.extend(adversarial_reports)

        return reports

    async def _compare_with_limit(
        self,
        test_case: TestCase,
        semaphore: asyncio.Semaphore,
    ) -> DiffReport:
        async with semaphore:
            return await self.compare(test_case)

    def _has_unsafe_input_files(self, test_case: TestCase) -> bool:
        try:
            safe_input_file_names(test_case.input_files)
        except UnsafeInputFilePathError as exc:
            log.warning("Skipping test case with unsafe input file path: %s", exc)
            return True
        return False

    def _split_stateful_samples(
        self,
        behavior_corpus: List[BehaviorSample],
    ) -> tuple[list[BehaviorSample], "OrderedDict[str, list[BehaviorSample]]"]:
        regular: list[BehaviorSample] = []
        groups: OrderedDict[str, list[BehaviorSample]] = OrderedDict()
        for sample in behavior_corpus:
            plan = self._stateful_plan_name(sample)
            if not plan:
                regular.append(sample)
                continue
            groups.setdefault(plan, []).append(sample)
        for samples in groups.values():
            samples.sort(key=self._stateful_step_index)
        return regular, groups

    def _stateful_plan_name(self, sample: BehaviorSample) -> str | None:
        for tag in sample.tags:
            if tag.startswith("stateful_plan:"):
                return tag.split(":", 1)[1]
        return None

    def _stateful_step_index(self, sample: BehaviorSample) -> int:
        for tag in sample.tags:
            if tag.startswith("stateful_step:"):
                try:
                    return int(tag.split(":", 1)[1])
                except ValueError:
                    return 0
        return 0

    async def _compare_stateful_sequence(
        self,
        samples: list[BehaviorSample],
        semaphore: asyncio.Semaphore | None = None,
    ) -> list[DiffReport]:
        reports: list[DiffReport] = []
        with tempfile.TemporaryDirectory() as orig_tmp, tempfile.TemporaryDirectory() as repl_tmp:
            orig_workdir = Path(orig_tmp)
            repl_workdir = Path(repl_tmp)
            for sample in samples:
                if semaphore is not None:
                    async with semaphore:
                        report = await self._compare_in_workdirs(
                            sample.test_case,
                            orig_workdir,
                            repl_workdir,
                        )
                else:
                    report = await self._compare_in_workdirs(
                        sample.test_case,
                        orig_workdir,
                        repl_workdir,
                    )
                reports.append(report)
        return reports

    async def _compare_in_workdirs(
        self,
        test_case: TestCase,
        orig_workdir: Path,
        repl_workdir: Path,
    ) -> DiffReport:
        orig_result = await self.orig_executor.run_in_workdir(test_case, orig_workdir)
        repl_result = await self.repl_executor.run_in_workdir(test_case, repl_workdir)

        return DiffReport(
            test_case=test_case,
            original_result=orig_result,
            replacement_result=repl_result,
            stdout_match=self._streams_equivalent(orig_result.stdout, repl_result.stdout),
            stderr_match=self._streams_equivalent(orig_result.stderr, repl_result.stderr),
            exit_code_match=orig_result.exit_code == repl_result.exit_code,
            file_outputs_match=self._files_equivalent(
                orig_result.output_files,
                repl_result.output_files,
            ),
            timing_similar=True,
        )
    
    async def find_discriminating_input(
        self,
        base_case: TestCase,
    ) -> Optional[TestCase]:
        """Try to find a minimal input that distinguishes original from replacement."""
        # Simplified delta-debugging: try removing args, truncating stdin
        # A full implementation would use more sophisticated shrinking
        
        candidates = [
            TestCase(name=f"shrunk_args", args=[], stdin=base_case.stdin),
            TestCase(name=f"shrunk_stdin", args=base_case.args, stdin=""),
            TestCase(name=f"minimal", args=[], stdin=""),
        ]
        
        for candidate in candidates:
            report = await self.compare(candidate)
            if not report.is_equivalent:
                return candidate
        
        return None
    
    def _streams_equivalent(self, a: str, b: str) -> bool:
        """Compare two output streams with some tolerance."""
        # Normalize whitespace and line endings
        a_norm = a.strip().replace("\r\n", "\n")
        b_norm = b.strip().replace("\r\n", "\n")
        return a_norm == b_norm
    
    def _files_equivalent(
        self,
        orig_files: dict,
        repl_files: dict,
    ) -> bool:
        if set(orig_files.keys()) != set(repl_files.keys()):
            return False
        for key in orig_files:
            if orig_files[key] != repl_files[key]:
                return False
        return True
    
    async def _generate_adversarial_tests(
        self,
        current_reports: List[DiffReport],
    ) -> List[TestCase]:
        """Use LLM to generate test cases specifically targeting observed differences."""
        if not self.llm:
            return []
        
        failures = [r for r in current_reports if not r.is_equivalent]
        summary = f"Tested {len(current_reports)} cases, {len(failures)} failures."
        
        messages = [
            self.llm.system_prompt(
                "You generate adversarial test cases to find behavioral differences "
                "between an original program and its replacement. Output JSON list of test cases."
            ),
            self.llm.user_prompt(
                f"{summary}\n\n"
                f"Generate 5 test cases targeting potential behavioral gaps. "
                f"Focus on: edge cases, error conditions, unusual input combinations."
            ),
        ]
        
        resp = await self.llm.chat(
            messages,
            temperature=0.8,
            max_tokens=min(configured_max_tokens(self.llm, 2048), 2048),
        )
        return self._parse_test_cases(resp.content)
    
    def _parse_test_cases(self, text: str) -> List[TestCase]:
        """Parse LLM-generated adversarial test cases from a chat response."""
        return parse_llm_test_cases(text)
