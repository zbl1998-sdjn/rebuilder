"""Docker execution backend for ProgramBench cleanroom images."""

from __future__ import annotations

import asyncio
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from core.data_models import TestCase, TestResult

from .base import ExecutorBackend


@dataclass(frozen=True)
class DockerExecutable:
    """Reference to an executable inside a cleanroom Docker image."""

    image: str
    executable_path: str = "/workspace/executable"


class DockerRunner(Protocol):
    def run(
        self,
        command: list[str],
        input_bytes: bytes | None,
        timeout: float,
    ) -> subprocess.CompletedProcess[bytes]: ...


class SubprocessDockerRunner:
    """Thin subprocess wrapper for testable Docker CLI execution."""

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


class DockerExecutorBackend(ExecutorBackend):
    """Run a cleanroom image executable through Docker with networking disabled."""

    def __init__(self, runner: DockerRunner | None = None, timeout: float = 10.0):
        self.runner = runner or SubprocessDockerRunner()
        self.timeout = timeout

    async def run(self, executable: DockerExecutable, test_case: TestCase) -> TestResult:
        if not isinstance(executable, DockerExecutable):
            raise TypeError("DockerExecutorBackend requires DockerExecutable")
        if not executable.image.endswith(":task_cleanroom"):
            raise ValueError(f"Docker execution is limited to task_cleanroom images: {executable.image}")

        with tempfile.TemporaryDirectory() as tmpdir:
            return await self.run_in_workdir(executable, test_case, Path(tmpdir))

    async def run_in_workdir(
        self,
        executable: DockerExecutable,
        test_case: TestCase,
        workdir: Path,
    ) -> TestResult:
        if not isinstance(executable, DockerExecutable):
            raise TypeError("DockerExecutorBackend requires DockerExecutable")
        if not executable.image.endswith(":task_cleanroom"):
            raise ValueError(f"Docker execution is limited to task_cleanroom images: {executable.image}")

        workdir.mkdir(parents=True, exist_ok=True)
        self._write_input_files(workdir, test_case)
        command = self._docker_command(executable, workdir, test_case)
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
        except Exception as e:
            return TestResult(stdout="", stderr=str(e), exit_code=-1)

    def _docker_command(
        self,
        executable: DockerExecutable,
        workdir: Path,
        test_case: TestCase,
    ) -> list[str]:
        mount = f"{workdir.resolve()}:/rebuilder-work"
        env_args = [
            item
            for key, value in sorted(test_case.env_vars.items())
            if self._valid_env_name(key)
            for item in ["-e", f"{key}={value}"]
        ]
        return [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "-v",
            mount,
            "-w",
            "/rebuilder-work",
            *env_args,
            executable.image,
            executable.executable_path,
            *test_case.args,
        ]

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
