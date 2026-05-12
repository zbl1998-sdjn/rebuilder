"""Executor backend interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from core.data_models import TestCase, TestResult


class ExecutorBackend(ABC):
    """Run an executable through its normal interface."""

    @abstractmethod
    async def run(self, executable: Path | str, test_case: TestCase) -> TestResult:
        """Execute one test case and return observable behavior."""
        raise NotImplementedError
