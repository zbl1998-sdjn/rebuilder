"""Runtime smoke checks for generated codebases."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import hashlib
import tempfile
from pathlib import Path
from typing import Sequence

from core.codebase.integrity import CodebaseIntegrityIssue, python_syntax_error_message
from core.data_models import BehaviorContract, Codebase, TestCase, TestResult
from core.execution.env import safe_env_vars
from core.execution.files import UnsafeInputFilePathError, safe_input_file_relative_path
from core.implementation.output_writer import write_files
from utils.executable import SandboxExecutor


@dataclass(frozen=True)
class RuntimeSmokeReport:
    issues: list[CodebaseIntegrityIssue]
    metadata: dict[str, object]


class PythonRuntimeSmokeChecker:
    """Run minimal Python CLI invocations to catch generated entrypoint crashes."""

    def __init__(
        self,
        timeout: float = 2.0,
        max_contract_cases: int = 6,
        max_input_files: int = 8,
        max_input_file_bytes: int = 64 * 1024,
    ):
        self.timeout = timeout
        self.max_contract_cases = max(0, int(max_contract_cases))
        self.max_input_files = max(0, int(max_input_files))
        self.max_input_file_bytes = max(0, int(max_input_file_bytes))

    async def find_issues(
        self,
        codebase: Codebase,
        entry_point: str | None = None,
        behavior_contracts: Sequence[BehaviorContract] | None = None,
    ) -> list[CodebaseIntegrityIssue]:
        return (
            await self.check(
                codebase,
                entry_point=entry_point,
                behavior_contracts=behavior_contracts,
            )
        ).issues

    async def check(
        self,
        codebase: Codebase,
        entry_point: str | None = None,
        behavior_contracts: Sequence[BehaviorContract] | None = None,
    ) -> RuntimeSmokeReport:
        if codebase.language.lower() != "python":
            return RuntimeSmokeReport([], self._smoke_metadata([], "skipped_non_python"))
        normalized = self._normalize_python_entrypoint(entry_point)
        if not normalized or normalized not in codebase.files:
            return RuntimeSmokeReport([], self._smoke_metadata([], "skipped_missing_entrypoint"))

        smoke_cases = self._smoke_cases(behavior_contracts or [])
        syntax_issue = self._first_syntax_issue(codebase)
        if syntax_issue is not None:
            metadata = self._smoke_metadata(
                smoke_cases,
                "failed",
                failed_issue_kind=syntax_issue.kind,
            )
            return RuntimeSmokeReport([syntax_issue], metadata)

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            root = Path(tmpdir)
            write_files(root, codebase.files)
            executable = root / normalized
            executor = SandboxExecutor(executable, timeout=self.timeout)
            for test_case in smoke_cases:
                result = await executor.run(test_case)
                issue = self._issue_from_result(normalized, test_case, result)
                if issue is not None:
                    metadata = self._smoke_metadata(
                        smoke_cases,
                        "failed",
                        failed_issue_kind=issue.kind,
                    )
                    return RuntimeSmokeReport([issue], metadata)
        return RuntimeSmokeReport([], self._smoke_metadata(smoke_cases, "passed"))

    def plan_metadata(
        self,
        behavior_contracts: Sequence[BehaviorContract] | None = None,
    ) -> dict[str, object]:
        """Return aggregate metadata for the smoke cases that would be executed."""

        return self._smoke_metadata(
            self._smoke_cases(behavior_contracts or []),
            "planned",
        )

    def _normalize_python_entrypoint(self, entry_point: str | None) -> str | None:
        if not entry_point:
            return None
        normalized = entry_point.replace("\\", "/")
        if not normalized.endswith(".py"):
            normalized += ".py"
        return normalized

    def _smoke_cases(
        self,
        behavior_contracts: Sequence[BehaviorContract],
    ) -> list[TestCase]:
        cases = [
            TestCase(name="implementation_smoke_no_args", args=[], stdin=""),
            TestCase(name="implementation_smoke_help", args=["--help"], stdin=""),
        ]
        seen = {self._smoke_case_key(case) for case in cases}
        selected = 0
        for contract in sorted(behavior_contracts, key=self._contract_priority):
            if selected >= self.max_contract_cases:
                break
            case = self._case_from_contract(contract)
            if case is None:
                continue
            key = self._smoke_case_key(case)
            if key in seen:
                continue
            seen.add(key)
            cases.append(case)
            selected += 1
        return cases

    def _smoke_case_key(self, case: TestCase) -> tuple:
        input_files = tuple(
            (name, self._content_fingerprint(content))
            for name, content in sorted(case.input_files.items())
        )
        env_vars = tuple(sorted(case.env_vars.items()))
        return (tuple(case.args), case.stdin, input_files, env_vars)

    def _smoke_metadata(
        self,
        cases: Sequence[TestCase],
        status: str,
        *,
        failed_issue_kind: str | None = None,
    ) -> dict[str, object]:
        dimensions = set()
        for case in cases:
            if case.args:
                dimensions.add("args")
            if case.stdin:
                dimensions.add("stdin")
            if case.input_files:
                dimensions.add("input_files")
            if case.env_vars:
                dimensions.add("env_vars")
            if not case.args and not case.stdin and not case.input_files and not case.env_vars:
                dimensions.add("default")

        metadata: dict[str, object] = {
            "status": status,
            "case_count": len(cases),
            "contract_case_count": sum(
                1
                for case in cases
                if case.name.startswith("implementation_smoke_contract_")
            ),
            "arg_case_count": sum(1 for case in cases if case.args),
            "stdin_case_count": sum(1 for case in cases if case.stdin),
            "input_file_case_count": sum(1 for case in cases if case.input_files),
            "env_var_case_count": sum(1 for case in cases if case.env_vars),
            "input_dimensions": sorted(dimensions),
        }
        if failed_issue_kind:
            metadata["failed_issue_kind"] = failed_issue_kind
        return metadata

    def _content_fingerprint(self, content: bytes | str) -> str:
        data = content if isinstance(content, bytes) else content.encode("utf-8")
        return hashlib.sha256(data).hexdigest()

    def _contract_priority(self, contract: BehaviorContract) -> tuple[int, str]:
        tags = set(contract.tags)
        name = contract.test_name.lower()
        if "error_mode" in tags:
            return (0, name)
        if "smoke_contract" in " ".join(tags):
            return (1, name)
        if any(arg in {"--help", "-h", "--version", "-V"} for arg in contract.args):
            return (2, name)
        if contract.input_files and not contract.output_files and not contract.output_file_previews:
            return (3, name)
        if contract.stdin and not self._has_probable_file_arg(contract.args):
            return (4, name)
        return (5, name)

    def _case_from_contract(self, contract: BehaviorContract) -> TestCase | None:
        if not self._is_safe_contract_smoke(contract):
            return None
        input_files = self._safe_contract_input_files(contract)
        if input_files is None:
            return None
        return TestCase(
            name=f"implementation_smoke_contract_{contract.test_name}",
            args=list(contract.args),
            stdin=contract.stdin,
            input_files=input_files,
            env_vars=safe_env_vars(contract.env_vars),
            description="runtime smoke from behavior contract",
        )

    def _is_safe_contract_smoke(self, contract: BehaviorContract) -> bool:
        if contract.output_files or contract.output_file_previews:
            return False
        if len(contract.stdin) > 4096:
            return False
        if "shell_init" in contract.tags and len(contract.stdout) >= 1000:
            return False
        if self._has_unsafe_file_arg(contract.args):
            return False
        if self._safe_contract_input_files(contract) is None:
            return False
        if (
            self._has_probable_file_arg(contract.args)
            and not contract.input_files
            and "error_mode" not in contract.tags
        ):
            return False
        return True

    def _safe_contract_input_files(
        self,
        contract: BehaviorContract,
    ) -> dict[str, bytes] | None:
        if not contract.input_files:
            return {}
        if len(contract.input_files) > self.max_input_files:
            return None

        safe: dict[str, bytes] = {}
        total_bytes = 0
        for name, content in sorted(contract.input_files.items()):
            try:
                normalized = safe_input_file_relative_path(name).as_posix()
            except UnsafeInputFilePathError:
                return None
            data = content if isinstance(content, bytes) else str(content).encode("utf-8")
            total_bytes += len(data)
            if len(data) > self.max_input_file_bytes or total_bytes > self.max_input_file_bytes:
                return None
            safe[normalized] = data
        return safe

    def _has_probable_file_arg(self, args: Sequence[str]) -> bool:
        file_suffixes = {
            ".csv",
            ".json",
            ".jsonl",
            ".html",
            ".htm",
            ".xml",
            ".txt",
            ".md",
            ".mkd",
            ".zip",
            ".tar",
            ".gz",
            ".tgz",
            ".xz",
        }
        for arg in args:
            if arg.startswith("-"):
                continue
            normalized = arg.replace("\\", "/")
            if "/" in normalized:
                return True
            lowered = normalized.lower()
            if any(lowered.endswith(suffix) for suffix in file_suffixes):
                return True
        return False

    def _has_unsafe_file_arg(self, args: Sequence[str]) -> bool:
        for arg in args:
            if arg.startswith("-") or not self._has_probable_file_arg([arg]):
                continue
            try:
                safe_input_file_relative_path(arg)
            except UnsafeInputFilePathError:
                return True
        return False

    def _issue_from_result(
        self,
        path: str,
        test_case: TestCase,
        result: TestResult,
    ) -> CodebaseIntegrityIssue | None:
        argv = " ".join(test_case.args) if test_case.args else "<no args>"
        if result.timeout_triggered:
            return CodebaseIntegrityIssue(
                kind="runtime_smoke_timeout",
                path=path,
                module=path,
                message=f"Python entry point {path!r} timed out during smoke run {argv}",
            )
        if self._looks_like_python_traceback(result.stderr):
            return CodebaseIntegrityIssue(
                kind="runtime_smoke_traceback",
                path=path,
                module=path,
                message=(
                    f"Python entry point {path!r} raised a traceback during smoke run "
                    f"{argv}: {self._snippet(result.stderr)}"
                ),
            )
        if self._looks_like_python_syntax_error(result.stderr):
            return CodebaseIntegrityIssue(
                kind="runtime_smoke_syntax_error",
                path=path,
                module=path,
                message=(
                    f"Python entry point {path!r} has syntax error during smoke run "
                    f"{argv}: {self._snippet(result.stderr)}"
                ),
            )
        if result.exit_code == -1 and result.stderr:
            if self._looks_like_executor_permission_error(result.stderr):
                return CodebaseIntegrityIssue(
                    kind="runtime_smoke_executor_permission_denied",
                    path=path,
                    module=path,
                    message=(
                        f"Runtime smoke executor could not start Python entry point "
                        f"{path!r} during smoke run {argv}: permission denied"
                    ),
                )
            return CodebaseIntegrityIssue(
                kind="runtime_smoke_error",
                path=path,
                module=path,
                message=(
                    f"Python entry point {path!r} failed during smoke run "
                    f"{argv}: {self._snippet(result.stderr)}"
                ),
            )
        return None

    def _first_syntax_issue(self, codebase: Codebase) -> CodebaseIntegrityIssue | None:
        for path, content in sorted(codebase.files.items()):
            if not path.endswith(".py"):
                continue
            try:
                ast.parse(content, filename=path)
            except SyntaxError as exc:
                return CodebaseIntegrityIssue(
                    kind="runtime_smoke_syntax_error",
                    path=path,
                    module=path,
                    message=python_syntax_error_message(path, exc, content),
                )
        return None

    def _looks_like_python_traceback(self, stderr: str) -> bool:
        return "Traceback (most recent call last):" in stderr

    def _looks_like_python_syntax_error(self, stderr: str) -> bool:
        return "SyntaxError:" in stderr and 'File "' in stderr

    def _looks_like_executor_permission_error(self, stderr: str) -> bool:
        lowered = stderr.lower()
        return (
            "[winerror 5]" in lowered
            or "permission denied" in lowered
            or "access is denied" in lowered
        )

    def _snippet(self, text: str, limit: int = 400) -> str:
        collapsed = " ".join(text.strip().split())
        if len(collapsed) <= limit:
            return collapsed
        head_limit = max(1, (limit - 5) // 2)
        tail_limit = max(1, limit - 5 - head_limit)
        return collapsed[:head_limit] + " ... " + collapsed[-tail_limit:]
