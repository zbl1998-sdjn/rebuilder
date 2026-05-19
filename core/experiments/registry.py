"""Aggregate-only experiment registry for strategy evaluation."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

FORBIDDEN_AGGREGATE_KEYS = {
    "test_results",
    "stdout",
    "stderr",
    "args",
    "branch",
    "name",
    "expected",
    "actual",
    "diff",
}

ALLOWED_STRATEGY_PARAM_KEYS = {
    "adaptive_probe_budget",
    "implementation_mode",
    "max_iterations",
    "max_repair_attempts",
    "max_tokens",
    "min_coverage",
    "min_samples",
    "model",
    "planner",
    "probe_budget",
    "profile_domain",
    "repair_mode",
    "seed",
    "temperature",
    "timeout",
    "top_p",
    "use_adaptive_probes",
}

NON_NEGATIVE_NUMERIC_STRATEGY_PARAM_KEYS = {
    "adaptive_probe_budget",
    "max_iterations",
    "max_repair_attempts",
    "max_tokens",
    "min_samples",
    "probe_budget",
    "temperature",
    "timeout",
}

BOUNDED_RATE_STRATEGY_PARAM_KEYS = {
    "min_coverage",
    "top_p",
}

StrategyParamValue: TypeAlias = bool | int | float | str | None


def validate_strategy_params(value: Any) -> dict[str, StrategyParamValue]:
    """Validate selectable strategy knobs without accepting per-test details."""
    if not isinstance(value, dict):
        raise ValueError("strategy params must be a mapping")

    validated: dict[str, StrategyParamValue] = {}
    for key, param_value in value.items():
        if key not in ALLOWED_STRATEGY_PARAM_KEYS:
            raise ValueError(f"strategy params contain unsupported key: {key}")
        if param_value is None or isinstance(param_value, (bool, int, str)):
            validate_strategy_numeric_param(key, param_value)
            validated[key] = param_value
            continue
        if isinstance(param_value, float) and math.isfinite(param_value):
            validate_strategy_numeric_param(key, param_value)
            validated[key] = param_value
            continue
        raise ValueError(f"strategy params must use scalar values: {key}")
    return validated


def validate_strategy_numeric_param(key: str, value: StrategyParamValue) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return
    parsed = float(value)
    if key in BOUNDED_RATE_STRATEGY_PARAM_KEYS:
        if not 0 <= parsed <= 1:
            raise ValueError(f"{key} must be a finite rate between 0 and 1")
    elif key in NON_NEGATIVE_NUMERIC_STRATEGY_PARAM_KEYS and parsed < 0:
        raise ValueError(f"{key} must be non-negative")


def validate_aggregate_only(payload: Any) -> None:
    """Reject hidden per-test details anywhere in an experiment payload."""

    def visit(value: Any, path: str) -> None:
        if isinstance(value, dict):
            if path == "variant.params":
                validate_strategy_params(value)
            for key, child in value.items():
                if key in FORBIDDEN_AGGREGATE_KEYS:
                    location = f"{path}.{key}" if path else key
                    raise ValueError(f"aggregate-only payload contains forbidden key: {location}")
                visit(child, f"{path}.{key}" if path else str(key))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}[{index}]")

    visit(payload, "")


class StrategyVariant(BaseModel):
    """A selectable aggregate-learning strategy variant."""

    model_config = ConfigDict(extra="forbid")

    variant_id: str
    strategy: str
    params: dict[str, StrategyParamValue] = Field(default_factory=dict)

    @field_validator("params", mode="before")
    @classmethod
    def params_are_aggregate_safe(cls, value: Any) -> dict[str, StrategyParamValue]:
        return validate_strategy_params(value)


class AggregateFeedback(BaseModel):
    """Official aggregate feedback with no hidden per-test details."""

    model_config = ConfigDict(extra="forbid")

    score: float = 0.0
    passed_tests: int = 0
    total_tests: int = 0
    pass_rate: float = 0.0
    fully_resolved: bool = False
    almost_resolved: bool = False
    error_code: str | None = None
    warning_count: int = 0

    @field_validator("score")
    @classmethod
    def score_is_bounded_rate(cls, value: float) -> float:
        return validate_bounded_rate("score", value)

    @field_validator("pass_rate")
    @classmethod
    def pass_rate_is_bounded_rate(cls, value: float) -> float:
        return validate_bounded_rate("pass_rate", value)

    @field_validator("passed_tests", "total_tests", "warning_count")
    @classmethod
    def counts_are_non_negative(cls, value: int, info: ValidationInfo) -> int:
        if value < 0:
            raise ValueError(f"{info.field_name} must be non-negative")
        return value

    @model_validator(mode="after")
    def passed_tests_do_not_exceed_total(self) -> AggregateFeedback:
        if self.passed_tests > self.total_tests:
            raise ValueError("passed_tests cannot exceed total_tests")
        return self


def validate_bounded_rate(name: str, value: float) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0 or parsed > 1:
        raise ValueError(f"{name} must be a finite rate between 0 and 1")
    return parsed


class ExperimentRun(BaseModel):
    """One append-only aggregate result row."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    instance_id: str
    variant: StrategyVariant
    official: AggregateFeedback
    holdout_cases: int = 0
    created_at: str | None = None

    @field_validator("holdout_cases")
    @classmethod
    def holdout_cases_are_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("holdout_cases must be non-negative")
        return value


class ExperimentRegistry:
    """Append-only JSONL registry for aggregate experiment rows."""

    def __init__(self, path: Path | str):
        self.path = Path(path)

    def append(self, run: ExperimentRun) -> None:
        payload = run.model_dump(mode="json")
        validate_aggregate_only(payload)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    def load(self) -> list[ExperimentRun]:
        if not self.path.exists():
            return []
        rows: list[ExperimentRun] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    payload = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                if not isinstance(payload, dict):
                    continue
                try:
                    validate_aggregate_only(payload)
                    rows.append(ExperimentRun.model_validate(payload))
                except ValueError as exc:
                    raise ValueError(f"invalid aggregate registry row {line_number}: {exc}") from exc
        return rows
