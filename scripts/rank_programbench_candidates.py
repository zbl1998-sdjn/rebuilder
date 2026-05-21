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
OfficialRank = tuple[int, int, int, int, float]


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
    embedded_official_rank: OfficialRank | None
    recorded_baseline_rank: OfficialRank | None
    official_eval_failure_reason: str | None
    official_eval_failure_report_path: Path | None
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
    max_local_holdout_gap: float | None = None,
) -> None:
    validate_rate_threshold("min_holdout_rate", min_holdout_rate)
    validate_non_negative_int_threshold("min_holdout_cases", min_holdout_cases)
    validate_non_negative_int_threshold("min_smoke_contract_axes", min_smoke_contract_axes)
    normalize_required_runtime_smoke_dimensions(required_runtime_smoke_dimensions)
    if not math.isfinite(min_holdout_improvement_delta) or min_holdout_improvement_delta < 0:
        raise ValueError("min_holdout_improvement_delta must be non-negative and finite")
    if max_local_holdout_gap is not None:
        validate_rate_threshold("max_local_holdout_gap", max_local_holdout_gap)


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
        "--max-local-holdout-gap",
        type=rate_float,
        default=None,
        help=(
            "Optional anti-overfit gate: maximum allowed aggregate gap between "
            "local resolved_rate and holdout_resolved_rate once holdout is otherwise gate-ready"
        ),
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
    max_local_holdout_gap: float | None = None,
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
        max_local_holdout_gap=max_local_holdout_gap,
    )
    baseline_root_path = Path(baseline_root)
    official_task_ids = discover_official_eval_task_ids(Path(official_eval_root))
    official_task_ids.update(discover_baseline_task_ids(baseline_root_path))
    baseline_ranks = discover_baseline_official_ranks(baseline_root_path)
    best_by_task: dict[str, CandidateRow] = {}
    for result_path in Path(runs_root).rglob("result.json"):
        row = read_candidate_row(
            result_path,
            official_task_ids,
            baseline_ranks,
            official_eval_root=official_eval_root,
        )
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
                max_local_holdout_gap=max_local_holdout_gap,
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
    max_local_holdout_gap: float | None = None,
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
        max_local_holdout_gap=max_local_holdout_gap,
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
    max_local_holdout_gap: float | None = None,
    allow_existing_official: bool = False,
) -> list[str]:
    validate_gate_thresholds(
        min_holdout_rate=min_holdout_rate,
        min_holdout_cases=min_holdout_cases,
        min_smoke_contract_axes=min_smoke_contract_axes,
        required_runtime_smoke_dimensions=required_runtime_smoke_dimensions,
        min_holdout_improvement_delta=min_holdout_improvement_delta,
        max_local_holdout_gap=max_local_holdout_gap,
    )
    blockers: list[str] = []
    if row.has_official_eval and not allow_existing_official:
        blockers.append("already_official")
    if row.has_official_eval and allow_existing_official:
        if row.embedded_official_rank is None:
            blockers.append(
                row.official_eval_failure_reason
                or "missing_official_candidate_summary"
            )
        elif (
            row.recorded_baseline_rank is not None
            and row.embedded_official_rank <= row.recorded_baseline_rank
        ):
            blockers.append("official_not_above_baseline")
    if row.holdout_resolved_rate is None:
        blockers.append("missing_holdout")
    if row.holdout_cases < min_holdout_cases:
        blockers.append("too_few_holdout_cases")
    if row.holdout_resolved_rate is not None and row.holdout_resolved_rate < min_holdout_rate:
        blockers.append("low_holdout_rate")
    gap = local_holdout_gap(row)
    if (
        max_local_holdout_gap is not None
        and gap is not None
        and row.holdout_resolved_rate is not None
        and row.holdout_resolved_rate >= min_holdout_rate
        and gap > max_local_holdout_gap
    ):
        blockers.append("local_holdout_gap_too_high")
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
    max_local_holdout_gap: float | None = None,
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
        max_local_holdout_gap=max_local_holdout_gap,
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


def discover_baseline_official_ranks(root: Path) -> dict[str, OfficialRank]:
    ranks: dict[str, OfficialRank] = {}
    if not root.exists():
        return ranks
    for path in root.glob("*.baseline.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        instance_id = payload.get("instance_id")
        if not instance_id:
            continue
        rank = official_rank_from_summary(payload.get("official"))
        if rank is not None:
            ranks[str(instance_id)] = rank
    return ranks


def read_candidate_row(
    result_path: Path,
    official_task_ids: set[str],
    baseline_ranks: dict[str, OfficialRank] | None = None,
    *,
    official_eval_root: Path | str | None = None,
) -> CandidateRow | None:
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
    embedded_official_rank = official_rank_from_result_payload(payload)
    embedded_failure_reason = official_eval_failure_reason_from_result_payload(payload)
    failure_report_path = find_official_eval_failure_report(
        result_path,
        str(task_id),
        official_eval_root=official_eval_root,
    )
    failure_reason = read_official_eval_failure_reason(failure_report_path, str(task_id))
    if failure_reason is None:
        failure_reason = embedded_failure_reason
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
        has_official_eval=(
            task_id in official_task_ids
            or failure_report_path is not None
            or embedded_failure_reason is not None
        ),
        embedded_official_rank=embedded_official_rank,
        recorded_baseline_rank=(baseline_ranks or {}).get(str(task_id)),
        official_eval_failure_reason=failure_reason,
        official_eval_failure_report_path=failure_report_path,
        result_path=result_path,
        modified_at=result_path.stat().st_mtime,
    )


def find_official_eval_failure_report(
    result_path: Path,
    task_id: str,
    *,
    official_eval_root: Path | str | None = None,
) -> Path | None:
    candidates: list[Path] = []
    session_root = infer_session_root(result_path)
    submission_root: Path | None = None
    if session_root is not None:
        submission_root = session_root.parent / f"{session_root.name}_submission"
        candidates.extend(find_failure_reports_under(submission_root))
    if official_eval_root is not None:
        candidates.extend(find_failure_reports_under(Path(official_eval_root)))

    seen: set[Path] = set()
    for report_path in candidates:
        resolved = report_path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if official_eval_failure_matches(
            report_path,
            task_id,
            candidate_submission_root=submission_root,
        ):
            return report_path
    return None


def infer_session_root(result_path: Path) -> Path | None:
    parts = result_path.parts
    if "generated" not in parts:
        return None
    generated_index = parts.index("generated")
    if generated_index < 2:
        return None
    return Path(*parts[: generated_index - 1])


def find_failure_reports_under(root: Path) -> list[Path]:
    if not root.exists():
        return []
    if root.is_file():
        return [root] if root.name == "official_eval_failure_report.json" else []
    return sorted(root.rglob("official_eval_failure_report.json"))


def official_eval_failure_matches(
    report_path: Path,
    task_id: str,
    *,
    candidate_submission_root: Path | None = None,
) -> bool:
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    instance_id = payload.get("instance_id")
    if instance_id is not None and str(instance_id) != task_id:
        return False
    if candidate_submission_root is None:
        return True
    return report_belongs_to_submission(report_path, payload, candidate_submission_root)


def report_belongs_to_submission(
    report_path: Path,
    payload: dict[str, object],
    candidate_submission_root: Path,
) -> bool:
    if path_is_within(report_path, candidate_submission_root):
        return True
    artifacts = payload.get("artifacts")
    if isinstance(artifacts, dict):
        submission_root = artifacts.get("submission_root")
        if isinstance(submission_root, dict):
            reported_path = submission_root.get("path")
            if isinstance(reported_path, str) and reported_path:
                return path_is_within(normalize_report_path(reported_path), candidate_submission_root)
    return False


def normalize_report_path(path_text: str) -> Path:
    path = Path(path_text)
    return path if path.is_absolute() else ROOT / path


def path_is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except (OSError, ValueError):
        return False
    return True


def read_official_eval_failure_reason(
    report_path: Path | None,
    task_id: str,
) -> str | None:
    if report_path is None:
        return None
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "official_eval_failed_without_eval_json"
    if not isinstance(payload, dict):
        return "official_eval_failed_without_eval_json"
    instance_id = payload.get("instance_id")
    if instance_id is not None and str(instance_id) != task_id:
        return None
    reason = payload.get("reason")
    if isinstance(reason, str) and reason:
        return reason
    return "official_eval_failed_without_eval_json"


def official_rank_from_result_payload(payload: dict[str, object]) -> OfficialRank | None:
    summary = payload.get("official_eval_summary")
    if not isinstance(summary, dict):
        return None
    counted = summary.get("counted")
    return official_rank_from_summary(counted if isinstance(counted, dict) else summary)


def official_eval_failure_reason_from_result_payload(payload: dict[str, object]) -> str | None:
    summary = payload.get("official_eval_summary")
    if not isinstance(summary, dict):
        return None
    counted = summary.get("counted")
    sections = [counted if isinstance(counted, dict) else summary]
    raw = summary.get("raw")
    if isinstance(raw, dict):
        sections.append(raw)
    for section in sections:
        if section_has_invalid_official_eval_payload(section):
            return "official_eval_failed_without_eval_json"
    return None


def section_has_invalid_official_eval_payload(summary: dict[str, object]) -> bool:
    error_code = summary.get("error_code")
    if isinstance(error_code, str) and error_code:
        return True
    has_eval_fields = any(
        key in summary
        for key in (
            "score",
            "passed_tests",
            "total_tests",
            "pass_rate",
            "fully_resolved",
            "almost_resolved",
        )
    )
    return has_eval_fields and as_int(summary.get("total_tests")) <= 0


def official_rank_from_summary(summary: object) -> OfficialRank | None:
    if not isinstance(summary, dict):
        return None
    if section_has_invalid_official_eval_payload(summary):
        return None
    score = as_int(summary.get("score"))
    passed_tests = as_int(summary.get("passed_tests"))
    total_tests = as_int(summary.get("total_tests"))
    pass_rate = as_optional_float(summary.get("pass_rate"))
    if pass_rate is None and total_tests:
        pass_rate = passed_tests / total_tests
    return (
        1 if summary.get("fully_resolved") is True else 0,
        1 if summary.get("almost_resolved") is True else 0,
        score,
        passed_tests,
        pass_rate or 0.0,
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
) -> tuple[int, int, float, int, int, int, int, float, float, float]:
    holdout = row.holdout_resolved_rate if row.holdout_resolved_rate is not None else -1.0
    enough_holdout = row.holdout_cases >= min_holdout_cases
    gap = local_holdout_gap(row)
    return (
        0 if row.has_official_eval else 1,
        1 if enough_holdout else 0,
        holdout,
        row.smoke_contract_axis_count,
        row.adaptive_axis_count,
        len(row.runtime_smoke_input_dimensions),
        row.runtime_smoke_contract_case_count,
        -(gap if gap is not None else 1.0),
        row.resolved_rate,
        row.modified_at,
    )


def local_holdout_gap(row: CandidateRow) -> float | None:
    if row.holdout_resolved_rate is None:
        return None
    return max(0.0, row.resolved_rate - row.holdout_resolved_rate)


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
    max_local_holdout_gap: float | None = None,
    allow_existing_official: bool = False,
) -> None:
    selected = rows[: max(0, limit)]
    print(
        "| rank | task | local | holdout | local-holdout gap | holdout cases | smoke axes | adaptive axes | runtime smoke | "
        "runtime dims | official gate | status | probes | repairs | assets | official eval | result |"
    )
    print(
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | --- | "
        "---: | ---: | --- | --- | --- |"
    )
    for index, row in enumerate(selected, start=1):
        runtime_dims = ",".join(row.runtime_smoke_input_dimensions) or "-"
        print(
            f"| {index} | {row.task_id} | {format_rate(row.resolved_rate)} | "
            f"{format_rate(row.holdout_resolved_rate)} | {format_rate(local_holdout_gap(row))} | "
            f"{row.holdout_cases} | "
            f"{row.smoke_contract_axis_count} | {row.adaptive_axis_count} | "
            f"{row.runtime_smoke_status} | {runtime_dims} | "
            f"{official_gate_reason(row, min_holdout_rate=min_holdout_rate, min_holdout_cases=min_holdout_cases, min_smoke_contract_axes=min_smoke_contract_axes, required_runtime_smoke_dimensions=required_runtime_smoke_dimensions, require_holdout_improvement=require_holdout_improvement, holdout_history_root=holdout_history_root, min_holdout_improvement_delta=min_holdout_improvement_delta, max_local_holdout_gap=max_local_holdout_gap, allow_existing_official=allow_existing_official)} | "
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
    max_local_holdout_gap: float | None = None,
    allow_existing_official: bool = False,
) -> dict[str, object]:
    gap = local_holdout_gap(row)
    return {
        "rank": rank,
        "task_id": row.task_id,
        "local_resolved_rate": row.resolved_rate,
        "holdout_resolved_rate": row.holdout_resolved_rate,
        "local_holdout_gap": gap,
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
            max_local_holdout_gap=max_local_holdout_gap,
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
            max_local_holdout_gap=max_local_holdout_gap,
            allow_existing_official=allow_existing_official,
        ),
        "status": row.status,
        "probes_conducted": row.probes_conducted,
        "iterations_used": row.iterations_used,
        "static_output_assets_enabled": row.static_output_assets_enabled,
        "has_official_eval": row.has_official_eval,
        "official_eval_failure_reason": row.official_eval_failure_reason,
        "official_eval_failure_report_path": (
            None
            if row.official_eval_failure_report_path is None
            else str(row.official_eval_failure_report_path)
        ),
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
    max_local_holdout_gap: float | None = None,
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
                max_local_holdout_gap=max_local_holdout_gap,
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
    max_local_holdout_gap: float | None = None,
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
                max_local_holdout_gap=max_local_holdout_gap,
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
        max_local_holdout_gap=args.max_local_holdout_gap,
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
        max_local_holdout_gap=args.max_local_holdout_gap,
        allow_existing_official=args.allow_existing_official,
    )


if __name__ == "__main__":
    main()
