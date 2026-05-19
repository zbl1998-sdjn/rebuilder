"""Local subprocess execution backend."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict

from core.data_models import TestCase, TestResult

from .base import ExecutorBackend
from .files import safe_input_file_names, safe_input_file_path


logger = logging.getLogger(__name__)


class LocalExecutorBackend(ExecutorBackend):
    """Execute a program locally in a temporary working directory."""

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    async def run(self, executable: Path | str, test_case: TestCase) -> TestResult:
        executable_path = Path(executable).expanduser().resolve(strict=False)
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            return await self.run_in_workdir(executable_path, test_case, Path(tmpdir))

    async def run_in_workdir(
        self,
        executable: Path | str,
        test_case: TestCase,
        workdir: Path,
    ) -> TestResult:
        executable_path = Path(executable).expanduser().resolve(strict=False)
        workdir.mkdir(parents=True, exist_ok=True)
        self._write_input_files(workdir, test_case)
        cmd = self._command_for_executable(executable_path) + test_case.args
        env = self._environment_for_executable(executable_path)
        env.update(
            {
                key: value
                for key, value in test_case.env_vars.items()
                if self._valid_env_name(key)
            }
        )

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(workdir),
                env=env,
            )
            start = time.perf_counter()
            stdout_data, stderr_data = await asyncio.wait_for(
                proc.communicate(input=test_case.stdin.encode("utf-8")),
                timeout=self.timeout,
            )
            elapsed_ms = (time.perf_counter() - start) * 1000
            return TestResult(
                stdout=stdout_data.decode("utf-8", errors="replace"),
                stderr=stderr_data.decode("utf-8", errors="replace"),
                exit_code=proc.returncode or 0,
                output_files=self._collect_output_files(workdir, test_case),
                execution_time_ms=elapsed_ms,
                timeout_triggered=False,
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                logger.debug("Failed to clean up timed-out local process", exc_info=True)
            return TestResult(stdout="", stderr="", exit_code=-1, timeout_triggered=True)
        except Exception as e:
            return TestResult(stdout="", stderr=str(e), exit_code=-1)

    def _write_input_files(self, tmp_path: Path, test_case: TestCase) -> None:
        for filename, content in test_case.input_files.items():
            target = safe_input_file_path(tmp_path, filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, str):
                target.write_text(content, encoding="utf-8")
            else:
                target.write_bytes(content)

    def _collect_output_files(self, tmp_path: Path, test_case: TestCase) -> Dict[str, bytes]:
        input_paths = safe_input_file_names(test_case.input_files)
        output_files: Dict[str, bytes] = {}
        for path in tmp_path.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(tmp_path).as_posix()
            if relative not in input_paths:
                output_files[relative] = path.read_bytes()
        return output_files

    def _command_for_executable(self, executable: Path) -> list[str]:
        if executable.suffix.lower() == ".py":
            return [sys.executable, str(executable)]
        return [str(executable)]

    def _environment_for_executable(self, executable: Path) -> Dict[str, str]:
        env = dict(os.environ)
        if executable.suffix.lower() == ".py":
            # Keep Windows-local Python replacements on a UTF-8 pipe encoding so
            # help text and Unicode-rich outputs match Linux-like cleanroom runs.
            env.setdefault("PYTHONIOENCODING", "utf-8")
            env.setdefault("PYTHONUTF8", "1")
        return env

    def _valid_env_name(self, name: str) -> bool:
        return re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name) is not None
