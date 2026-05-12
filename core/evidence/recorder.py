"""Executor wrapper that records observable behavior as evidence."""

from __future__ import annotations

from pathlib import Path

from core.data_models import TestCase, TestResult
from utils.executable import SandboxExecutor

from .models import EvidenceRecord, EvidenceSource
from .store import EvidenceStore


class EvidenceRecorder:
    """Run executables through normal UI interactions and persist observations."""

    def __init__(
        self,
        executable: Path | str,
        store: EvidenceStore,
        source: EvidenceSource = EvidenceSource.REFERENCE_EXECUTABLE,
        timeout: float = 10.0,
        backend=None,
    ):
        self.executable = executable if backend else Path(executable)
        self.store = store
        self.source = source
        self.executor = SandboxExecutor(self.executable, timeout=timeout, backend=backend)

    async def run_and_record(
        self,
        test_case: TestCase,
        tags: list[str] | None = None,
    ) -> tuple[TestResult, EvidenceRecord]:
        result = await self.executor.run(test_case)
        record = EvidenceRecord.from_observation(
            source=self.source,
            executable_path=str(self.executable),
            test_case=test_case,
            result=result,
            tags=tags,
        )
        return result, self.store.append(record)
