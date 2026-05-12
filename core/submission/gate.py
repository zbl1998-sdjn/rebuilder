"""Aggregate-only gates for packaging ProgramBench submissions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class HoldoutGateError(ValueError):
    """Raised when a generated candidate is not ready for packaging."""


@dataclass(frozen=True)
class HoldoutGateSummary:
    result_path: Path
    holdout_cases: int
    holdout_resolved_rate: float
    min_rate: float
    min_cases: int


class SubmissionHoldoutGate:
    """Require an aggregate internal holdout result before packaging."""

    def __init__(self, min_rate: float = 0.8, min_cases: int = 1):
        self.min_rate = max(0.0, min(float(min_rate), 1.0))
        self.min_cases = max(1, int(min_cases))

    def verify(self, result_path: Path | str) -> HoldoutGateSummary:
        path = Path(result_path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        holdout_cases = int(payload.get("holdout_cases") or 0)
        raw_rate = payload.get("holdout_resolved_rate")
        if holdout_cases <= 0 or raw_rate is None:
            raise HoldoutGateError(
                "Internal aggregate holdout is required before packaging."
            )
        if holdout_cases < self.min_cases:
            raise HoldoutGateError(
                f"Internal aggregate holdout has {holdout_cases} cases, "
                f"below required {self.min_cases}."
            )

        holdout_resolved_rate = float(raw_rate)
        if holdout_resolved_rate < self.min_rate:
            raise HoldoutGateError(
                f"Internal aggregate holdout rate {holdout_resolved_rate:.1%} "
                f"is below required {self.min_rate:.1%}."
            )
        return HoldoutGateSummary(
            result_path=path,
            holdout_cases=holdout_cases,
            holdout_resolved_rate=holdout_resolved_rate,
            min_rate=self.min_rate,
            min_cases=self.min_cases,
        )
