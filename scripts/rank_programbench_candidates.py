"""Rank completed ProgramBench runs for the next official-eval candidates."""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit_holdout_improvement import audit_holdout_improvement  # noqa: E402


RUNTIME_SMOKE_DIMENSIONS = ("args", "stdin", "input_files", "env_vars", "default")


@dataclass(frozen=True)
class CandidateRow:
    task_id: str
    status: str
    resolved_rate: float
    holdout_resolved_rate: float | None
    holdout_cases: int
    probes_conducted: int
    iterations_used: int
    smoke_contract_axis_count: int
    adaptive_axis_count: int
    runtime_smoke_status: str
    runtime_smoke_case_count: int
    runtime_smoke_contract_case_count: int
    runtime_smoke_input_dimensions: tuple[str, ...]
    static_output_assets_enabled: bool | None
    has_official_eval: bool
    result_path: Path
    modified_at: float


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


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def runtime_smoke_dimensions(value: str) -> tuple[str, ...]:
    try:
        return normalize_required_runtime_smoke_dimensions(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def validate_gate_thresholds(
    *,
    min_holdout_rate: float,
    min_holdout_cases: int,
    min_smoke_contract_axes: int,
    min_holdout_improvement_delta: float,
    required_runtime_smoke_dimensions: tuple[str, ...] | list[str] | str | None = (),
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


def normalize_required_runtime_smoke_dimensions(
    value: tuple[str, ...] | list[str] | str | None,
) -> tuple[str, ...]:
    if value is None or value == "":
        return ()
    raw_dimensions = value.split(",") if isinstance(value, str) else value
    allowed = set(RUNTIME_SMOKE_DIMENSIONS)
    selected: set[str] = set()
    for item in raw_dimensions:
        if not isinstance(item, str):
            raise ValueError(runtime_smoke_dimension_error())
        dimension = item.strip()
        if not dimension:
            continue
        if dimension not in allowed:
            raise ValueError(runtime_smoke_dimension_error())
        selected.add(dimension)
    return tuple(
        dimension for dimension in RUNTIME_SMOKE_DIMENSIONS if dimension in selected
    )


def normalize_runtime_smoke_dimensions(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple, set)):
        return ()
    return normalize_required_runtime_smoke_dimensions(
        [item for item in value if isinstance(item, str)]
    )


def runtime_smoke_dimension_error() -> str:
    return (
        "required_runtime_smoke_dimensions must contain only: "
        + ", ".join(RUNTIME_SMOKE_DIMENSIONS)
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rank ProgramBench candidate runs")
    parser.add_argument("--runs", default="runs", help="Root directory containing run result.json files")
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
    parser.add_argument("--limit", type=positive_int, default=20, help="Maximum rows to print")
    parser.add_argument(
        "--min-holdout-cases",
        type=non_negative_int,
        default=10,
        help="Minimum holdout cases required for a reliable candidate ranking",
    )
    parser.add_argument(
        "--min-holdout-rate",
        type=rate_float,
        default=0.8,
        help="Minimum holdout resolved rate required for an official-eval eligible candidate",
    )
    parser.add_argument(
        "--min-smoke-contract-axes",
        type=non_negative_int,
        default=0,
        help="Optional minimum local smoke-contract axes required for official-eval eligibility",
    )
    parser.add_argument(
        "--require-runtime-smoke-dimensions",
        type=runtime_smoke_dimensions,
        default=(),
        help=(
            "Comma-separated implementation runtime-smoke input dimensions required "
            "for official-eval eligibility. Valid values: "
            + ", ".join(RUNTIME_SMOKE_DIMENSIONS)
        ),
    )
    parser.add_argument(
        "--require-holdout-improvement",
        action="store_true",
        help="Require official-eval eligible candidates to beat the previous reliable local holdout best",
    )
    parser.add_argument(
        "--holdout-history-root",
        default=None,
        help="Root containing historical result.json files for improvement checks; defaults to --runs",
    )
    parser.add_argument(
        "--min-holdout-improvement-delta",
        type=non_negative_float,
        default=0.0,
        help="Minimum positive holdout-rate delta over the previous reliable best",
    )
    parser.add_argument(
        "--official-eligible-only",
        action="store_true",
        help=(
            "Only show candidates that pass the aggregate local holdout gate; "
            "existing official tasks remain hidden unless --allow-existing-official is set"
        ),
    )
    parser.add_argument(
        "--allow-existing-official",
        action="store_true",
        help="Allow existing official/baseline tasks to pass local gates as baseline-upgrade candidates",
    )
    parser.add_argument(
        "--only-unofficial",
        action="store_true",
        help="Only show tasks without an existing official eval artifact",
    )
    parser.add_argument(
        "--latest-per-task",
        action="store_true",
        help="Rank each task by its newest result.json instead of its best historical score",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format. JSON emits aggregate-only candidate rows for automation.",
    )
    return parser.parse_args(argv)


def collect_candidates(
    runs_root: Path | str,
    official_eval_root: Path | str,
    *,
    baseline_root: Path | str = "baselines/programbench",
    only_unofficial: bool = False,
    min_holdout_cases: int = 10,
    min_holdout_rate: float = 0.8,
    min_smoke_contract_axes: int = 0,
    required_runtime_smoke_dimensions: tuple[str, ...] | list[str] | str | None = (),
    require_holdout_improvement: bool = False,
    holdout_history_root: Path | str | None = None,
    min_holdout_improvement_delta: float = 0.0,
    official_eligible_only: bool = False,
    allow_existing_official: bool = False,
    latest_per_task: bool = False,
) -> list[CandidateRow]:
    validate_gate_thresholds(
        min_holdout_rate=min_holdout_rate,
        min_holdout_cases=min_holdout_cases,
        min_smoke_contract_axes=min_smoke_contract_axes,
        required_runtime_smoke_dimensions=required_runtime_smoke_dimensions,
        min_holdout_improvement_delta=min_holdout_improvement_delta,
    )
    official_task_ids = discover_official_eval_task_ids(Path(official_eval_root))
    official_task_ids.update(discover_baseline_task_ids(Path(baseline_root)))
    best_by_task: dict[str, CandidateRow] = {}
    for result_path in Path(runs_root).rglob("result.json"):
        row = read_candidate_row(result_path, official_task_ids)
        if row is None:
            continue
        current = best_by_task.get(row.task_id)
        if current is None or is_preferred_candidate(
            row,
            current,
            min_holdout_cases=min_holdout_cases,
            latest_per_task=latest_per_task,
        ):
            best_by_task[row.task_id] = row
    rows = list(best_by_task.values())
    if only_unofficial:
        rows = [row for row in rows if not row.has_official_eval]
    if official_eligible_only:
        rows = [
            row
            for row in rows
            if is_official_eligible(
                row,
                min_holdout_rate=min_holdout_rate,
                min_holdout_cases=min_holdout_cases,
                min_smoke_contract_axes=min_smoke_contract_axes,
                required_runtime_smoke_dimensions=required_runtime_smoke_dimensions,
                require_holdout_improvement=require_holdout_improvement,
                holdout_history_root=holdout_history_root or runs_root,
                min_holdout_improvement_delta=min_holdout_improvement_delta,
                allow_existing_official=allow_existing_official,
            )
        ]
    rows = sorted(rows, key=lambda row: row.task_id)
    return sorted(rows, key=lambda row: candidate_sort_key(row, min_holdout_cases), reverse=True)


def is_official_eligible(
    row: CandidateRow,
    *,
    min_holdout_rate: float = 0.8,
    min_holdout_cases: int = 10,
    min_smoke_contract_axes: int = 0,
    required_runtime_smoke_dimensions: tuple[str, ...] | list[str] | str | None = (),
    require_holdout_improvement: bool = False,
    holdout_history_root: Path | str = "runs",
    min_holdout_improvement_delta: float = 0.0,
    allow_existing_official: bool = False,
) -> bool:
    reason = official_gate_reason(
        row,
        min_holdout_rate=min_holdout_rate,
        min_holdout_cases=min_holdout_cases,
        min_smoke_contract_axes=min_smoke_contract_axes,
        required_runtime_smoke_dimensions=required_runtime_smoke_dimensions,
        require_holdout_improvement=require_holdout_improvement,
        holdout_history_root=holdout_history_root,
        min_holdout_improvement_delta=min_holdout_improvement_delta,
        allow_existing_official=allow_existing_official,
    )
    return reason in {"eligible", "eligible_baseline_upgrade"}


def official_gate_blockers(
    row: CandidateRow,
    *,
    min_holdout_rate: float = 0.8,
    min_holdout_cases: int = 10,
    min_smoke_contract_axes: int = 0,
    required_runtime_smoke_dimensions: tuple[str, ...] | list[str] | str | None = (),
    require_holdout_improvement: bool = False,
    holdout_history_root: Path | str = "runs",
    min_holdout_improvement_delta: float = 0.0,
    allow_existing_official: bool = False,
) -> str:
    validate_gate_thresholds(
        min_holdout_rate=min_holdout_rate,
        min_holdout_cases=min_holdout_cases,
        min_smoke_contract_axes=min_smoke_contract_axes,
        required_runtime_smoke_dimensions=required_runtime_smoke_dimensions,
        min_holdout_improvement_delta=min_holdout_improvement_delta,
    )
    blockers: list[str] = []
    if row.has_official_eval and not allow_existing_official:
        blockers.append("already_official")
    if row.holdout_resolved_rate is None:
        blockers.append("missing_holdout")
    if row.holdout_cases < min_holdout_cases:
        blockers.append("too_few_holdout_cases")
    if row.holdout_resolved_rate is not None and row.holdout_resolved_rate < min_holdout_rate:
        blockers.append("low_holdout_rate")
    if row.smoke_contract_axis_count < min_smoke_contract_axes:
        blockers.append("insufficient_smoke_contract_axes")
    required_runtime_smoke_dimensions = normalize_required_runtime_smoke_dimensions(
        required_runtime_smoke_dimensions
    )
    if required_runtime_smoke_dimensions:
        if row.runtime_smoke_status != "passed":
            blockers.append("runtime_smoke_not_passed")
        elif not set(required_runtime_smoke_dimensions).issubset(
            set(row.runtime_smoke_input_dimensions)
        ):
            blockers.append("insufficient_runtime_smoke_dimensions")
    if require_holdout_improvement:
        improvement = audit_holdout_improvement(
            row.result_path,
            runs_root=holdout_history_root,
            min_holdout_cases=min_holdout_cases,
            min_delta=min_holdout_improvement_delta,
        )
        if not improvement["improved"]:
            blockers.append(f"holdout_{improvement['reason']}")
    return blockers


def official_gate_reason(
    row: CandidateRow,
    *,
    min_holdout_rate: float = 0.8,
    min_holdout_cases: int = 10,
    min_smoke_contract_axes: int = 0,
    required_runtime_smoke_dimensions: tuple[str, ...] | list[str] | str | None = (),
    require_holdout_improvement: bool = False,
    holdout_history_root: Path | str = "runs",
    min_holdout_improvement_delta: float = 0.0,
    allow_existing_official: bool = False,
) -> str:
    blockers = official_gate_blockers(
        row,
        min_holdout_rate=min_holdout_rate,
        min_holdout_cases=min_holdout_cases,
        min_smoke_contract_axes=min_smoke_contract_axes,
        required_runtime_smoke_dimensions=required_runtime_smoke_dimensions,
        require_holdout_improvement=require_holdout_improvement,
        holdout_history_root=holdout_history_root,
        min_holdout_improvement_delta=min_holdout_improvement_delta,
        allow_existing_official=allow_existing_official,
    )
    if blockers:
        return blockers[0]
    return "eligible_baseline_upgrade" if row.has_official_eval else "eligible"


def discover_official_eval_task_ids(root: Path) -> set[str]:
    if not root.exists():
        return set()
    task_ids: set[str] = set()
    for path in root.rglob("*.eval.json"):
        task_ids.add(path.name.removesuffix(".eval.json"))
        if path.parent.name:
            task_ids.add(path.parent.name)
    return task_ids


def discover_baseline_task_ids(root: Path) -> set[str]:
    if not root.exists():
        return set()
    task_ids: set[str] = set()
    for path in root.glob("*.baseline.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        instance_id = payload.get("instance_id")
        if instance_id:
            task_ids.add(str(instance_id))
    return task_ids


def read_candidate_row(result_path: Path, official_task_ids: set[str]) -> CandidateRow | None:
    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    task_id = payload.get("task_id") or infer_task_id(result_path)
    if not task_id:
        return None
    metadata = payload.get("implementation_metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    probe_axis_coverage = metadata.get("probe_axis_coverage") or {}
    if not isinstance(probe_axis_coverage, dict):
        probe_axis_coverage = {}
    runtime_smoke = metadata.get("runtime_smoke") or {}
    if not isinstance(runtime_smoke, dict):
        runtime_smoke = {}
    return CandidateRow(
        task_id=task_id,
        status=str(payload.get("status", "unknown")),
        resolved_rate=as_float(payload.get("resolved_rate")),
        holdout_resolved_rate=as_optional_float(payload.get("holdout_resolved_rate")),
        holdout_cases=as_int(payload.get("holdout_cases")),
        probes_conducted=as_int(payload.get("probes_conducted")),
        iterations_used=as_int(payload.get("iterations_used")),
        smoke_contract_axis_count=as_int(probe_axis_coverage.get("smoke_contract_axis_count")),
        adaptive_axis_count=as_int(probe_axis_coverage.get("adaptive_axis_count")),
        runtime_smoke_status=str(runtime_smoke.get("status", "missing")),
        runtime_smoke_case_count=as_int(runtime_smoke.get("case_count")),
        runtime_smoke_contract_case_count=as_int(runtime_smoke.get("contract_case_count")),
        runtime_smoke_input_dimensions=normalize_runtime_smoke_dimensions(
            runtime_smoke.get("input_dimensions")
        ),
        static_output_assets_enabled=as_optional_bool(metadata.get("static_output_assets_enabled")),
        has_official_eval=task_id in official_task_ids,
        result_path=result_path,
        modified_at=result_path.stat().st_mtime,
    )


def infer_task_id(result_path: Path) -> str | None:
    parts = result_path.parts
    if "generated" in parts:
        generated_index = parts.index("generated")
        if generated_index + 1 < len(parts):
            return parts[generated_index + 1]
    return result_path.parent.name or None


def candidate_sort_key(
    row: CandidateRow,
    min_holdout_cases: int = 10,
) -> tuple[int, int, float, int, int, int, int, float, float]:
    holdout = row.holdout_resolved_rate if row.holdout_resolved_rate is not None else -1.0
    enough_holdout = row.holdout_cases >= min_holdout_cases
    return (
        0 if row.has_official_eval else 1,
        1 if enough_holdout else 0,
        holdout,
        row.smoke_contract_axis_count,
        row.adaptive_axis_count,
        len(row.runtime_smoke_input_dimensions),
        row.runtime_smoke_contract_case_count,
        row.resolved_rate,
        row.modified_at,
    )


def is_preferred_candidate(
    row: CandidateRow,
    current: CandidateRow,
    *,
    min_holdout_cases: int,
    latest_per_task: bool,
) -> bool:
    if latest_per_task:
        return (row.modified_at, str(row.result_path)) > (
            current.modified_at,
            str(current.result_path),
        )
    return (
        candidate_sort_key(row, min_holdout_cases),
        str(row.result_path),
    ) > (
        candidate_sort_key(current, min_holdout_cases),
        str(current.result_path),
    )


def as_float(value: Any) -> float:
    try:
        parsed = float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return parsed if math.isfinite(parsed) and 0.0 <= parsed <= 1.0 else 0.0


def as_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        parsed = float(value or 0)
    except (TypeError, ValueError):
        return 0
    if not math.isfinite(parsed) or parsed < 0 or not parsed.is_integer():
        return 0
    return int(parsed)


def as_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and 0.0 <= parsed <= 1.0 else None


def as_optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def format_rate(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.1%}"


def format_bool(value: bool | None) -> str:
    if value is None:
        return "-"
    return "yes" if value else "no"


def write_markdown(
    rows: list[CandidateRow],
    limit: int,
    *,
    min_holdout_rate: float = 0.8,
    min_holdout_cases: int = 10,
    min_smoke_contract_axes: int = 0,
    required_runtime_smoke_dimensions: tuple[str, ...] | list[str] | str | None = (),
    require_holdout_improvement: bool = False,
    holdout_history_root: Path | str = "runs",
    min_holdout_improvement_delta: float = 0.0,
    allow_existing_official: bool = False,
) -> None:
    selected = rows[: max(0, limit)]
    print(
        "| rank | task | local | holdout | holdout cases | smoke axes | adaptive axes | runtime smoke | "
        "runtime dims | official gate | status | probes | repairs | assets | official eval | result |"
    )
    print(
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | --- | "
        "---: | ---: | --- | --- | --- |"
    )
    for index, row in enumerate(selected, start=1):
        runtime_dims = ",".join(row.runtime_smoke_input_dimensions) or "-"
        print(
            f"| {index} | {row.task_id} | {format_rate(row.resolved_rate)} | "
            f"{format_rate(row.holdout_resolved_rate)} | {row.holdout_cases} | "
            f"{row.smoke_contract_axis_count} | {row.adaptive_axis_count} | "
            f"{row.runtime_smoke_status} | {runtime_dims} | "
            f"{official_gate_reason(row, min_holdout_rate=min_holdout_rate, min_holdout_cases=min_holdout_cases, min_smoke_contract_axes=min_smoke_contract_axes, required_runtime_smoke_dimensions=required_runtime_smoke_dimensions, require_holdout_improvement=require_holdout_improvement, holdout_history_root=holdout_history_root, min_holdout_improvement_delta=min_holdout_improvement_delta, allow_existing_official=allow_existing_official)} | "
            f"{row.status} | "
            f"{row.probes_conducted} | {row.iterations_used} | "
            f"{format_bool(row.static_output_assets_enabled)} | "
            f"{format_bool(row.has_official_eval)} | {row.result_path} |"
        )


def candidate_json_row(
    row: CandidateRow,
    rank: int,
    *,
    min_holdout_rate: float = 0.8,
    min_holdout_cases: int = 10,
    min_smoke_contract_axes: int = 0,
    required_runtime_smoke_dimensions: tuple[str, ...] | list[str] | str | None = (),
    require_holdout_improvement: bool = False,
    holdout_history_root: Path | str = "runs",
    min_holdout_improvement_delta: float = 0.0,
    allow_existing_official: bool = False,
) -> dict[str, object]:
    return {
        "rank": rank,
        "task_id": row.task_id,
        "local_resolved_rate": row.resolved_rate,
        "holdout_resolved_rate": row.holdout_resolved_rate,
        "holdout_cases": row.holdout_cases,
        "smoke_contract_axis_count": row.smoke_contract_axis_count,
        "adaptive_axis_count": row.adaptive_axis_count,
        "runtime_smoke_status": row.runtime_smoke_status,
        "runtime_smoke_case_count": row.runtime_smoke_case_count,
        "runtime_smoke_contract_case_count": row.runtime_smoke_contract_case_count,
        "runtime_smoke_input_dimensions": list(row.runtime_smoke_input_dimensions),
        "official_gate": official_gate_reason(
            row,
            min_holdout_rate=min_holdout_rate,
            min_holdout_cases=min_holdout_cases,
            min_smoke_contract_axes=min_smoke_contract_axes,
            required_runtime_smoke_dimensions=required_runtime_smoke_dimensions,
            require_holdout_improvement=require_holdout_improvement,
            holdout_history_root=holdout_history_root,
            min_holdout_improvement_delta=min_holdout_improvement_delta,
            allow_existing_official=allow_existing_official,
        ),
        "official_gate_blockers": official_gate_blockers(
            row,
            min_holdout_rate=min_holdout_rate,
            min_holdout_cases=min_holdout_cases,
            min_smoke_contract_axes=min_smoke_contract_axes,
            required_runtime_smoke_dimensions=required_runtime_smoke_dimensions,
            require_holdout_improvement=require_holdout_improvement,
            holdout_history_root=holdout_history_root,
            min_holdout_improvement_delta=min_holdout_improvement_delta,
            allow_existing_official=allow_existing_official,
        ),
        "status": row.status,
        "probes_conducted": row.probes_conducted,
        "iterations_used": row.iterations_used,
        "static_output_assets_enabled": row.static_output_assets_enabled,
        "has_official_eval": row.has_official_eval,
        "result_path": str(row.result_path),
    }


def candidate_json_payload(
    rows: list[CandidateRow],
    limit: int,
    *,
    min_holdout_rate: float = 0.8,
    min_holdout_cases: int = 10,
    min_smoke_contract_axes: int = 0,
    required_runtime_smoke_dimensions: tuple[str, ...] | list[str] | str | None = (),
    require_holdout_improvement: bool = False,
    holdout_history_root: Path | str = "runs",
    min_holdout_improvement_delta: float = 0.0,
    allow_existing_official: bool = False,
) -> dict[str, object]:
    selected = rows[: max(0, limit)]
    return {
        "schema_version": 1,
        "row_count": len(selected),
        "total_row_count": len(rows),
        "limit": limit,
        "rows": [
            candidate_json_row(
                row,
                rank,
                min_holdout_rate=min_holdout_rate,
                min_holdout_cases=min_holdout_cases,
                min_smoke_contract_axes=min_smoke_contract_axes,
                required_runtime_smoke_dimensions=required_runtime_smoke_dimensions,
                require_holdout_improvement=require_holdout_improvement,
                holdout_history_root=holdout_history_root,
                min_holdout_improvement_delta=min_holdout_improvement_delta,
                allow_existing_official=allow_existing_official,
            )
            for rank, row in enumerate(selected, start=1)
        ],
    }


def write_json(
    rows: list[CandidateRow],
    limit: int,
    *,
    min_holdout_rate: float = 0.8,
    min_holdout_cases: int = 10,
    min_smoke_contract_axes: int = 0,
    required_runtime_smoke_dimensions: tuple[str, ...] | list[str] | str | None = (),
    require_holdout_improvement: bool = False,
    holdout_history_root: Path | str = "runs",
    min_holdout_improvement_delta: float = 0.0,
    allow_existing_official: bool = False,
) -> None:
    print(
        json.dumps(
            candidate_json_payload(
                rows,
                limit,
                min_holdout_rate=min_holdout_rate,
                min_holdout_cases=min_holdout_cases,
                min_smoke_contract_axes=min_smoke_contract_axes,
                required_runtime_smoke_dimensions=required_runtime_smoke_dimensions,
                require_holdout_improvement=require_holdout_improvement,
                holdout_history_root=holdout_history_root,
                min_holdout_improvement_delta=min_holdout_improvement_delta,
                allow_existing_official=allow_existing_official,
            ),
            indent=2,
            ensure_ascii=False,
        )
    )


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    rows = collect_candidates(
        args.runs,
        args.official_eval_root,
        baseline_root=args.baseline_root,
        only_unofficial=args.only_unofficial,
        min_holdout_cases=args.min_holdout_cases,
        min_holdout_rate=args.min_holdout_rate,
        min_smoke_contract_axes=args.min_smoke_contract_axes,
        required_runtime_smoke_dimensions=args.require_runtime_smoke_dimensions,
        require_holdout_improvement=args.require_holdout_improvement,
        holdout_history_root=args.holdout_history_root or args.runs,
        min_holdout_improvement_delta=args.min_holdout_improvement_delta,
        official_eligible_only=args.official_eligible_only,
        allow_existing_official=args.allow_existing_official,
        latest_per_task=args.latest_per_task,
    )
    write = write_json if args.format == "json" else write_markdown
    write(
        rows,
        args.limit,
        min_holdout_rate=args.min_holdout_rate,
        min_holdout_cases=args.min_holdout_cases,
        min_smoke_contract_axes=args.min_smoke_contract_axes,
        required_runtime_smoke_dimensions=args.require_runtime_smoke_dimensions,
        require_holdout_improvement=args.require_holdout_improvement,
        holdout_history_root=args.holdout_history_root or args.runs,
        min_holdout_improvement_delta=args.min_holdout_improvement_delta,
        allow_existing_official=args.allow_existing_official,
    )


if __name__ == "__main__":
    main()
