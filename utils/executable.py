"""
Utilities for running executables safely and capturing their behavior.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.execution.local import LocalExecutorBackend
from core.data_models import TestCase, TestResult


class SandboxExecutor:
    """Execute binaries in a sandboxed environment with timeout and capture."""
    
    def __init__(self, executable: object, timeout: float = 10.0, backend: Any = None):
        self.timeout = timeout
        self.backend: Any = backend or LocalExecutorBackend(timeout=timeout)
        self.executable: object
        if backend is None:
            if not isinstance(executable, (str, Path)):
                raise TypeError("SandboxExecutor requires a path when no backend is injected")
            self.executable = Path(executable).expanduser().resolve(strict=False)
        else:
            self.executable = executable
    
    async def run(self, test_case: TestCase) -> TestResult:
        """Run the executable with the given test case."""
        return await self.backend.run(self.executable, test_case)

    async def run_in_workdir(self, test_case: TestCase, workdir: Path) -> TestResult:
        """Run the executable in a caller-managed working directory."""
        if not hasattr(self.backend, "run_in_workdir"):
            raise TypeError(f"Backend does not support shared workdirs: {type(self.backend).__name__}")
        return await self.backend.run_in_workdir(self.executable, test_case, workdir)
