"""Audit whether one local result.json is eligible for official evaluation."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.rank_programbench_candidates import (  # noqa: E402
    discover_baseline_official_ranks,
    discover_baseline_task_ids,
    discover_official_eval_task_ids,
    normalize_required_runtime_smoke_dimensions,
    official_gate_reason,
    read_candidate_row,
    runtime_smoke_dimensions,
)
from scripts.audit_holdout_improvement import audit_holdout_improvement  # noqa: E402


def non_negative_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative and finite")
    return parsed


def rate_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0 or parsed > 1:
        raise argparse.ArgumentTypeError("must be a finite rate between 0 and 1")
    return parsed


def non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


def validate_thresholds(
    *,
    min_holdout_rate: float,
    min_holdout_cases: int,
    min_smoke_contract_axes: int,
    required_runtime_smoke_dimensions: tuple[str, ...] | list[str] | str | None = (),
    min_holdout_improvement_delta: float,
) -> None:
    validate_rate_threshold("min_holdout_rate", min_holdout_rate)
    validate_non_negative_int_threshold("min_holdout_cases", min_holdout_cases)
    validate_non_negative_int_threshold("min_smoke_contract_axes", min_smoke_contract_axes)
    normalize_required_runtime_smoke_dimensions(required_runtime_smoke_dimensions)
    if not math.isfinite(min_holdout_improvement_delta) or min_holdout_improvement_delta < 0:
        raise ValueError("min_holdout_improvement_delta must be non-negative and finite")


def validate_rate_threshold(name: str, value: float) -> None:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite rate between 0 and 1") from exc
    if not math.isfinite(parsed) or parsed < 0 or parsed > 1:
        raise ValueError(f"{name} must be a finite rate between 0 and 1")


def validate_non_negative_int_threshold(name: str, value: int) -> None:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a non-negative integer") from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise ValueError(f"{name} must be non-negative")
    if not parsed.is_integer():
        raise ValueError(f"{name} must be a non-negative integer")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit aggregate official-eval readiness for one result.json")
    parser.add_argument("result", help="Path to a ReBuilder result.json")
    parser.add_argument(
        "--official-eval-root",
        default="runs/programbench_official_eval",
        help="Root directory containing official *.eval.json files",
    )
    parser.add_argument(
        "--baseline-root",
        default="baselines/programbench",
        help="Root directory containing recorded *.baseline.json files",
    )
    parser.add_argument("--min-holdout-rate", type=rate_float, default=0.8)
    parser.add_argument("--min-holdout-cases", type=non_negative_int, default=10)
    parser.add_argument("--min-smoke-contract-axes", type=non_negative_int, default=0)
    parser.add_argument(
        "--require-runtime-smoke-dimensions",
        type=runtime_smoke_dimensions,
        default=(),
        help="Comma-separated implementation runtime-smoke input dimensions required for official-eval eligibility",
    )
    parser.add_argument("--require-holdout-improvement", action="store_true")
    parser.add_argument("--holdout-history-root", default="runs")
    parser.add_argument("--min-holdout-improvement-delta", type=non_negative_float, default=0.0)
    parser.add_argument(
        "--allow-existing-official",
        action="store_true",
        help="Allow existing official/baseline tasks to pass local gates as baseline-upgrade candidates",
    )
    return parser.parse_args(argv)


def audit_result(
    result_path: Path | str,
    *,
    official_eval_root: Path | str,
    baseline_root: Path | str,
    min_holdout_rate: float = 0.8,
    min_holdout_cases: int = 10,
    min_smoke_contract_axes: int = 0,
    required_runtime_smoke_dimensions: tuple[str, ...] | list[str] | str | None = (),
    require_holdout_improvement: bool = False,
    holdout_history_root: Path | str = "runs",
    min_holdout_improvement_delta: float = 0.0,
    allow_existing_official: bool = False,
) -> dict[str, Any]:
    validate_thresholds(
        min_holdout_rate=min_holdout_rate,
        min_holdout_cases=min_holdout_cases,
        min_smoke_contract_axes=min_smoke_contract_axes,
        required_runtime_smoke_dimensions=required_runtime_smoke_dimensions,
        min_holdout_improvement_delta=min_holdout_improvement_delta,
    )
    required_runtime_smoke_dimensions = normalize_required_runtime_smoke_dimensions(
        required_runtime_smoke_dimensions
    )
    official_task_ids = discover_official_eval_task_ids(Path(official_eval_root))
    baseline_root_path = Path(baseline_root)
    official_task_ids.update(discover_baseline_task_ids(baseline_root_path))
    baseline_ranks = discover_baseline_official_ranks(baseline_root_path)
    row = read_candidate_row(Path(result_path), official_task_ids, baseline_ranks)
    if row is None:
        return invalid_result_audit(
            Path(result_path),
            min_holdout_rate=min_holdout_rate,
            min_holdout_cases=min_holdout_cases,
            min_smoke_contract_axes=min_smoke_contract_axes,
            required_runtime_smoke_dimensions=required_runtime_smoke_dimensions,
            require_holdout_improvement=require_holdout_improvement,
            min_holdout_improvement_delta=min_holdout_improvement_delta,
            allow_existing_official=allow_existing_official,
        )
    reason = official_gate_reason(
        row,
        min_holdout_rate=min_holdout_rate,
        min_holdout_cases=min_holdout_cases,
        min_smoke_contract_axes=min_smoke_contract_axes,
        required_runtime_smoke_dimensions=required_runtime_smoke_dimensions,
        allow_existing_official=allow_existing_official,
    )
    improvement_audit = None
    if reason in {"eligible", "eligible_baseline_upgrade"} and require_holdout_improvement:
        improvement_audit = audit_holdout_improvement(
            row.result_path,
            runs_root=holdout_history_root,
            min_holdout_cases=min_holdout_cases,
            min_delta=min_holdout_improvement_delta,
        )
        if not improvement_audit["improved"]:
            reason = f"holdout_{improvement_audit['reason']}"
    return {
        "eligible": reason in {"eligible", "eligible_baseline_upgrade"},
        "reason": reason,
        "task_id": row.task_id,
        "holdout_cases": row.holdout_cases,
        "holdout_resolved_rate": row.holdout_resolved_rate,
        "min_holdout_cases": min_holdout_cases,
        "min_holdout_rate": min_holdout_rate,
        "smoke_contract_axis_count": row.smoke_contract_axis_count,
        "adaptive_axis_count": row.adaptive_axis_count,
        "min_smoke_contract_axes": min_smoke_contract_axes,
        "runtime_smoke_status": row.runtime_smoke_status,
        "runtime_smoke_input_dimensions": list(row.runtime_smoke_input_dimensions),
        "required_runtime_smoke_dimensions": list(required_runtime_smoke_dimensions),
        "require_holdout_improvement": require_holdout_improvement,
        "min_holdout_improvement_delta": min_holdout_improvement_delta,
        "allow_existing_official": allow_existing_official,
        "holdout_improvement_reason": improvement_audit["reason"] if improvement_audit else None,
        "holdout_delta_from_best_previous": improvement_audit["delta_from_best_previous"] if improvement_audit else None,
        "holdout_best_previous_resolved_rate": (
            improvement_audit["best_previous_holdout_resolved_rate"] if improvement_audit else None
        ),
        "holdout_best_previous_cases": improvement_audit["best_previous_holdout_cases"] if improvement_audit else None,
        "holdout_best_previous_result_path": improvement_audit["best_previous_result_path"] if improvement_audit else None,
        "has_official_eval": row.has_official_eval,
        "result_path": str(row.result_path),
    }


def invalid_result_audit(
    result_path: Path,
    *,
    min_holdout_rate: float,
    min_holdout_cases: int,
    min_smoke_contract_axes: int,
    required_runtime_smoke_dimensions: tuple[str, ...] | list[str] | str | None,
    require_holdout_improvement: bool,
    min_holdout_improvement_delta: float,
    allow_existing_official: bool,
) -> dict[str, Any]:
    required_runtime_smoke_dimensions = normalize_required_runtime_smoke_dimensions(
        required_runtime_smoke_dimensions
    )
    return {
        "eligible": False,
        "reason": "invalid_result",
        "task_id": None,
        "holdout_cases": 0,
        "holdout_resolved_rate": None,
        "min_holdout_cases": min_holdout_cases,
        "min_holdout_rate": min_holdout_rate,
        "smoke_contract_axis_count": 0,
        "adaptive_axis_count": 0,
        "min_smoke_contract_axes": min_smoke_contract_axes,
        "runtime_smoke_status": "missing",
        "runtime_smoke_input_dimensions": [],
        "required_runtime_smoke_dimensions": list(required_runtime_smoke_dimensions),
        "require_holdout_improvement": require_holdout_improvement,
        "min_holdout_improvement_delta": min_holdout_improvement_delta,
        "allow_existing_official": allow_existing_official,
        "holdout_improvement_reason": None,
        "holdout_delta_from_best_previous": None,
        "holdout_best_previous_resolved_rate": None,
        "holdout_best_previous_cases": None,
        "holdout_best_previous_result_path": None,
        "has_official_eval": False,
        "result_path": str(result_path),
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    audit = audit_result(
        args.result,
        official_eval_root=args.official_eval_root,
        baseline_root=args.baseline_root,
        min_holdout_rate=args.min_holdout_rate,
        min_holdout_cases=args.min_holdout_cases,
        min_smoke_contract_axes=args.min_smoke_contract_axes,
        required_runtime_smoke_dimensions=args.require_runtime_smoke_dimensions,
        require_holdout_improvement=args.require_holdout_improvement,
        holdout_history_root=args.holdout_history_root,
        min_holdout_improvement_delta=args.min_holdout_improvement_delta,
        allow_existing_official=args.allow_existing_official,
    )
    print(json.dumps(audit, indent=2, sort_keys=True))
    return 0 if audit["eligible"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
