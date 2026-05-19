"""Aggregate-only gates for packaging ProgramBench submissions."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


RUNTIME_SMOKE_DIMENSIONS = ("args", "stdin", "input_files", "env_vars", "default")


class HoldoutGateError(ValueError):
    """Raised when a generated candidate is not ready for packaging."""


@dataclass(frozen=True)
class HoldoutGateSummary:
    result_path: Path
    holdout_cases: int
    holdout_resolved_rate: float
    min_rate: float
    min_cases: int
    smoke_contract_axis_count: int = 0
    min_smoke_contract_axes: int = 0
    runtime_smoke_status: str = ""
    runtime_smoke_input_dimensions: tuple[str, ...] = ()
    required_runtime_smoke_dimensions: tuple[str, ...] = ()


class SubmissionHoldoutGate:
    """Require an aggregate internal holdout result before packaging."""

    def __init__(
        self,
        min_rate: float = 0.8,
        min_cases: int = 1,
        min_smoke_contract_axes: int = 0,
        required_runtime_smoke_dimensions: str | Iterable[str] = (),
    ):
        parsed_min_rate = self._parse_rate_threshold("min_rate", min_rate)
        parsed_min_cases = self._parse_non_negative_int_threshold("min_cases", min_cases)
        parsed_min_smoke_contract_axes = self._parse_non_negative_int_threshold(
            "min_smoke_contract_axes",
            min_smoke_contract_axes,
        )
        self.min_rate = parsed_min_rate
        self.min_cases = max(1, parsed_min_cases)
        self.min_smoke_contract_axes = parsed_min_smoke_contract_axes
        self.required_runtime_smoke_dimensions = parse_runtime_smoke_dimensions(
            required_runtime_smoke_dimensions
        )

    def verify(self, result_path: Path | str) -> HoldoutGateSummary:
        path = Path(result_path)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HoldoutGateError(
                "Internal aggregate holdout is required before packaging."
            ) from exc
        if not isinstance(payload, dict):
            raise HoldoutGateError(
                "Internal aggregate holdout is required before packaging."
            )
        holdout_cases = self._as_int(payload.get("holdout_cases"))
        smoke_contract_axis_count = self._smoke_contract_axis_count(payload)
        holdout_resolved_rate = self._as_optional_float(payload.get("holdout_resolved_rate"))
        if holdout_cases <= 0 or holdout_resolved_rate is None:
            raise HoldoutGateError(
                "Internal aggregate holdout is required before packaging."
            )
        if holdout_cases < self.min_cases:
            raise HoldoutGateError(
                f"Internal aggregate holdout has {holdout_cases} cases, "
                f"below required {self.min_cases}."
            )

        if holdout_resolved_rate < self.min_rate:
            raise HoldoutGateError(
                f"Internal aggregate holdout rate {holdout_resolved_rate:.1%} "
                f"is below required {self.min_rate:.1%}."
            )
        if smoke_contract_axis_count < self.min_smoke_contract_axes:
            raise HoldoutGateError(
                f"Local smoke-contract axes {smoke_contract_axis_count} "
                f"below required {self.min_smoke_contract_axes}."
            )
        runtime_smoke_status, runtime_smoke_input_dimensions = runtime_smoke_metadata(payload)
        if self.required_runtime_smoke_dimensions:
            if runtime_smoke_status != "passed":
                raise HoldoutGateError(
                    "Local runtime-smoke dimensions require passed runtime smoke."
                )
            missing_dimensions = tuple(
                dimension
                for dimension in self.required_runtime_smoke_dimensions
                if dimension not in runtime_smoke_input_dimensions
            )
            if missing_dimensions:
                raise HoldoutGateError(
                    "Local runtime-smoke dimensions missing required "
                    f"{','.join(missing_dimensions)}."
                )
        return HoldoutGateSummary(
            result_path=path,
            holdout_cases=holdout_cases,
            holdout_resolved_rate=holdout_resolved_rate,
            min_rate=self.min_rate,
            min_cases=self.min_cases,
            smoke_contract_axis_count=smoke_contract_axis_count,
            min_smoke_contract_axes=self.min_smoke_contract_axes,
            runtime_smoke_status=runtime_smoke_status,
            runtime_smoke_input_dimensions=runtime_smoke_input_dimensions,
            required_runtime_smoke_dimensions=self.required_runtime_smoke_dimensions,
        )

    @staticmethod
    def _smoke_contract_axis_count(payload: dict) -> int:
        metadata = payload.get("implementation_metadata")
        if not isinstance(metadata, dict):
            return 0
        coverage = metadata.get("probe_axis_coverage")
        if not isinstance(coverage, dict):
            return 0
        return SubmissionHoldoutGate._as_int(coverage.get("smoke_contract_axis_count"))

    @staticmethod
    def _as_int(value) -> int:
        if isinstance(value, bool):
            return 0
        try:
            parsed = float(value or 0)
        except (TypeError, ValueError):
            return 0
        if not math.isfinite(parsed) or parsed < 0 or not parsed.is_integer():
            return 0
        return int(parsed)

    @staticmethod
    def _parse_rate_threshold(name: str, value) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be non-negative and finite") from exc
        if not math.isfinite(parsed) or parsed < 0:
            raise ValueError(f"{name} must be non-negative and finite")
        if parsed > 1:
            raise ValueError(f"{name} must be between 0 and 1")
        return parsed

    @staticmethod
    def _parse_non_negative_int_threshold(name: str, value) -> int:
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be a non-negative integer") from exc
        if not math.isfinite(parsed) or parsed < 0:
            raise ValueError(f"{name} must be non-negative")
        if not parsed.is_integer():
            raise ValueError(f"{name} must be a non-negative integer")
        return int(parsed)

    @staticmethod
    def _as_optional_float(value) -> float | None:
        if value is None:
            return None
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if math.isfinite(parsed) and 0.0 <= parsed <= 1.0 else None


def parse_runtime_smoke_dimensions(value: str | Iterable[str] | None) -> tuple[str, ...]:
    """Parse a comma-separated runtime-smoke dimension gate value."""

    return _normalize_runtime_smoke_dimensions(value, strict=True)


def runtime_smoke_metadata(payload: dict) -> tuple[str, tuple[str, ...]]:
    """Return aggregate-only runtime-smoke status and executed input dimensions."""

    metadata = payload.get("implementation_metadata")
    if not isinstance(metadata, dict):
        return "", ()
    runtime_smoke = metadata.get("runtime_smoke")
    if not isinstance(runtime_smoke, dict):
        return "", ()
    status = runtime_smoke.get("status")
    if not isinstance(status, str):
        status = ""
    return status, _normalize_runtime_smoke_dimensions(
        runtime_smoke.get("input_dimensions"),
        strict=False,
    )


def _normalize_runtime_smoke_dimensions(
    value: str | Iterable[str] | None,
    *,
    strict: bool,
) -> tuple[str, ...]:
    raw_dimensions: list[str] = []
    if value is None:
        return ()
    if isinstance(value, str):
        raw_dimensions.extend(part.strip() for part in value.split(","))
    else:
        for item in value:
            if isinstance(item, str):
                raw_dimensions.extend(part.strip() for part in item.split(","))
            elif strict:
                raise ValueError(
                    "runtime-smoke dimensions must be comma-separated strings"
                )
    requested = set()
    for dimension in raw_dimensions:
        if not dimension:
            continue
        if dimension not in RUNTIME_SMOKE_DIMENSIONS:
            if strict:
                allowed = ",".join(RUNTIME_SMOKE_DIMENSIONS)
                raise ValueError(
                    f"runtime-smoke dimension must be one of: {allowed}"
                )
            continue
        requested.add(dimension)
    return tuple(dimension for dimension in RUNTIME_SMOKE_DIMENSIONS if dimension in requested)
