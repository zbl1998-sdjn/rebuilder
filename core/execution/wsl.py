"""WSL execution backend for running generated replacements on Linux."""

from __future__ import annotations

import asyncio
import re
import shlex
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Protocol

from core.data_models import TestCase, TestResult

from .base import ExecutorBackend


class WSLRunner(Protocol):
    def run(
        self,
        command: list[str],
        input_bytes: bytes | None,
        timeout: float,
    ) -> subprocess.CompletedProcess[bytes]: ...


class SubprocessWSLRunner:
    """Thin subprocess wrapper for testable WSL CLI execution."""

    def run(
        self,
        command: list[str],
        input_bytes: bytes | None,
        timeout: float,
    ) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            command,
            input=input_bytes,
            capture_output=True,
            timeout=timeout,
            check=False,
        )


class WSLExecutorBackend(ExecutorBackend):
    """Execute a generated replacement in the default WSL distribution."""

    def __init__(self, runner: WSLRunner | None = None, timeout: float = 10.0):
        self.runner = runner or SubprocessWSLRunner()
        self.timeout = timeout

    async def run(self, executable: Path | str, test_case: TestCase) -> TestResult:
        with tempfile.TemporaryDirectory() as tmpdir:
            return await self.run_in_workdir(Path(executable), test_case, Path(tmpdir))

    async def run_in_workdir(
        self,
        executable: Path | str,
        test_case: TestCase,
        workdir: Path,
    ) -> TestResult:
        workdir.mkdir(parents=True, exist_ok=True)
        self._write_input_files(workdir, test_case)
        command = self._wsl_command(Path(executable), workdir, test_case)
        input_bytes = test_case.stdin.encode("utf-8") if test_case.stdin else None
        start = time.perf_counter()
        try:
            completed = await asyncio.to_thread(
                self.runner.run,
                command,
                input_bytes,
                self.timeout,
            )
            elapsed_ms = (time.perf_counter() - start) * 1000
            return TestResult(
                stdout=completed.stdout.decode("utf-8", errors="replace"),
                stderr=completed.stderr.decode("utf-8", errors="replace"),
                exit_code=completed.returncode,
                output_files=self._collect_output_files(workdir, test_case),
                execution_time_ms=elapsed_ms,
                timeout_triggered=False,
            )
        except subprocess.TimeoutExpired:
            return TestResult(stdout="", stderr="", exit_code=-1, timeout_triggered=True)
        except Exception as exc:
            return TestResult(stdout="", stderr=str(exc), exit_code=-1)

    def _wsl_command(
        self,
        executable: Path,
        workdir: Path,
        test_case: TestCase,
    ) -> list[str]:
        workdir_wsl = self._to_wsl_path(workdir)
        executable_wsl = self._to_wsl_path(executable)
        tokens = self._command_tokens(executable, executable_wsl, test_case)
        shell_script = f"cd {shlex.quote(workdir_wsl)} && {shlex.join(tokens)}"
        return ["wsl", "bash", "-lc", shell_script]

    def _command_tokens(
        self,
        executable: Path,
        executable_wsl: str,
        test_case: TestCase,
    ) -> list[str]:
        env_tokens = [
            f"{key}={self._map_env_value(value)}"
            for key, value in sorted(test_case.env_vars.items())
            if self._valid_env_name(key)
        ]
        executable_tokens = (
            ["python3", executable_wsl]
            if executable.suffix.lower() == ".py"
            else [executable_wsl]
        )
        if env_tokens:
            return ["env", *env_tokens, *executable_tokens, *test_case.args]
        return [*executable_tokens, *test_case.args]

    def _to_wsl_path(self, path: Path | str) -> str:
        raw = str(Path(path).expanduser().resolve(strict=False))
        normalized = raw.replace("\\", "/")
        if len(normalized) >= 3 and normalized[1:3] == ":/":
            drive = normalized[0].lower()
            return f"/mnt/{drive}{normalized[2:]}"
        return normalized

    def _map_env_value(self, value: str) -> str:
        if isinstance(value, str) and re.match(r"^[A-Za-z]:[\\/]", value):
            return self._to_wsl_path(value)
        return value

    def _valid_env_name(self, name: str) -> bool:
        return re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name) is not None

    def _write_input_files(self, workdir: Path, test_case: TestCase) -> None:
        for filename, content in test_case.input_files.items():
            target = workdir / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, str):
                target.write_text(content, encoding="utf-8")
            else:
                target.write_bytes(content)

    def _collect_output_files(self, workdir: Path, test_case: TestCase) -> dict[str, bytes]:
        input_paths = {Path(name).as_posix() for name in test_case.input_files}
        outputs: dict[str, bytes] = {}
        for path in workdir.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(workdir).as_posix()
            if relative not in input_paths:
                outputs[relative] = path.read_bytes()
        return outputs
