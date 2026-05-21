"""Audit aggregate-only restore targets for ProgramBench baseline upgrades."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit_official_eval_gate import audit_result  # noqa: E402
from scripts.plan_official_breakthrough_targets import (  # noqa: E402
    BreakthroughTarget,
    collect_official_breakthrough_targets,
    format_official,
)
from scripts.summarize_holdout_trends import (  # noqa: E402
    format_rate,
    non_negative_int,
    positive_int,
    rate_float,
)

AXIS_NAME_PATTERN = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")
AXIS_SUMMARY_LIMIT = 5


@dataclass(frozen=True)
class RestoreTargetAudit:
    task_id: str
    official_score: int
    latest_holdout_resolved_rate: float
    latest_holdout_cases: int
    best_holdout_resolved_rate: float
    best_holdout_cases: int
    regression_delta: float
    best_gate_reason: str
    latest_gate_reason: str
    latest_smoke_contract_axis_count: int
    latest_adaptive_axis_count: int
    best_smoke_contract_axis_count: int
    best_adaptive_axis_count: int
    added_smoke_contract_axes: tuple[str, ...]
    added_adaptive_axes: tuple[str, ...]
    removed_smoke_contract_axes: tuple[str, ...]
    removed_adaptive_axes: tuple[str, ...]
    added_axis_summary: str
    removed_axis_summary: str
    axis_delta_action: str
    regression_signal: str
    next_action: str
    latest_result_path: Path
    best_result_path: Path
    source_target: BreakthroughTarget


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit restore_historical_gate targets using aggregate local gate metadata"
    )
    parser.add_argument("--runs", default="runs", help="Root directory containing result.json files")
    parser.add_argument(
        "--baseline-root",
        default="baselines/programbench",
        help="Root directory containing recorded *.baseline.json files",
    )
    parser.add_argument(
        "--official-eval-root",
        default="runs/programbench_official_eval",
        help="Root directory containing official *.eval.json files",
    )
    parser.add_argument(
        "--task",
        dest="task_ids",
        action="append",
        default=None,
        help="Limit output to a specific task_id; may be repeated",
    )
    parser.add_argument("--limit", type=positive_int, default=20, help="Maximum rows to print")
    parser.add_argument("--min-holdout-cases", type=non_negative_int, default=10)
    parser.add_argument("--min-holdout-rate", type=rate_float, default=0.8)
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown", help="Output format")
    return parser.parse_args(argv)


def collect_restore_target_audits(
    runs_root: Path | str,
    baseline_root: Path | str,
    *,
    official_eval_root: Path | str = "runs/programbench_official_eval",
    min_holdout_cases: int = 10,
    min_holdout_rate: float = 0.8,
    task_ids: tuple[str, ...] | list[str] | None = None,
) -> list[RestoreTargetAudit]:
    selected_tasks = set(task_ids or ())
    targets = collect_official_breakthrough_targets(
        runs_root,
        baseline_root,
        min_holdout_cases=min_holdout_cases,
        min_holdout_rate=min_holdout_rate,
    )
    audits = [
        build_restore_audit(
            target,
            official_eval_root=official_eval_root,
            baseline_root=baseline_root,
            min_holdout_cases=min_holdout_cases,
            min_holdout_rate=min_holdout_rate,
        )
        for target in targets
        if target.target_class == "restore_historical_gate"
        and (not selected_tasks or target.task_id in selected_tasks)
    ]
    return sorted(audits, key=restore_sort_key)


def build_restore_audit(
    target: BreakthroughTarget,
    *,
    official_eval_root: Path | str,
    baseline_root: Path | str,
    min_holdout_cases: int,
    min_holdout_rate: float,
) -> RestoreTargetAudit:
    if (
        target.latest_holdout_resolved_rate is None
        or target.latest_holdout_cases is None
        or target.best_holdout_resolved_rate is None
        or target.best_holdout_cases is None
        or target.latest_result_path is None
        or target.best_result_path is None
    ):
        raise ValueError(f"{target.task_id} is missing restore audit aggregate fields")
    best_gate = audit_result(
        target.best_result_path,
        official_eval_root=official_eval_root,
        baseline_root=baseline_root,
        min_holdout_rate=min_holdout_rate,
        min_holdout_cases=min_holdout_cases,
        allow_existing_official=True,
    )
    latest_gate = audit_result(
        target.latest_result_path,
        official_eval_root=official_eval_root,
        baseline_root=baseline_root,
        min_holdout_rate=min_holdout_rate,
        min_holdout_cases=min_holdout_cases,
        allow_existing_official=True,
    )
    regression_delta = target.latest_holdout_resolved_rate - target.best_holdout_resolved_rate
    latest_smoke_axes = as_int(latest_gate.get("smoke_contract_axis_count"))
    latest_adaptive_axes = as_int(latest_gate.get("adaptive_axis_count"))
    best_smoke_axes = as_int(best_gate.get("smoke_contract_axis_count"))
    best_adaptive_axes = as_int(best_gate.get("adaptive_axis_count"))
    best_gate_reason = restore_gate_reason(best_gate)
    latest_gate_reason = restore_gate_reason(latest_gate)
    best_smoke_axis_names, best_adaptive_axis_names = result_axis_sets(target.best_result_path)
    latest_smoke_axis_names, latest_adaptive_axis_names = result_axis_sets(target.latest_result_path)
    added_smoke_axis_names = tuple(sorted(latest_smoke_axis_names - best_smoke_axis_names))
    added_adaptive_axis_names = tuple(sorted(latest_adaptive_axis_names - best_adaptive_axis_names))
    removed_smoke_axis_names = tuple(sorted(best_smoke_axis_names - latest_smoke_axis_names))
    removed_adaptive_axis_names = tuple(sorted(best_adaptive_axis_names - latest_adaptive_axis_names))
    regression_signal = classify_regression_signal(
        latest_gate_reason=latest_gate_reason,
        regression_delta=regression_delta,
        latest_axis_count=latest_smoke_axes + latest_adaptive_axes,
        best_axis_count=best_smoke_axes + best_adaptive_axes,
    )
    return RestoreTargetAudit(
        task_id=target.task_id,
        official_score=target.official_score,
        latest_holdout_resolved_rate=target.latest_holdout_resolved_rate,
        latest_holdout_cases=target.latest_holdout_cases,
        best_holdout_resolved_rate=target.best_holdout_resolved_rate,
        best_holdout_cases=target.best_holdout_cases,
        regression_delta=regression_delta,
        best_gate_reason=best_gate_reason,
        latest_gate_reason=latest_gate_reason,
        latest_smoke_contract_axis_count=latest_smoke_axes,
        latest_adaptive_axis_count=latest_adaptive_axes,
        best_smoke_contract_axis_count=best_smoke_axes,
        best_adaptive_axis_count=best_adaptive_axes,
        added_smoke_contract_axes=added_smoke_axis_names,
        added_adaptive_axes=added_adaptive_axis_names,
        removed_smoke_contract_axes=removed_smoke_axis_names,
        removed_adaptive_axes=removed_adaptive_axis_names,
        added_axis_summary=format_axis_delta(
            smoke_axes=added_smoke_axis_names,
            adaptive_axes=added_adaptive_axis_names,
            smoke_prefix="+smoke",
            adaptive_prefix="+adaptive",
        ),
        removed_axis_summary=format_axis_delta(
            smoke_axes=removed_smoke_axis_names,
            adaptive_axes=removed_adaptive_axis_names,
            smoke_prefix="-smoke",
            adaptive_prefix="-adaptive",
        ),
        axis_delta_action=axis_delta_action(
            added_smoke_axes=added_smoke_axis_names,
            added_adaptive_axes=added_adaptive_axis_names,
            removed_smoke_axes=removed_smoke_axis_names,
            removed_adaptive_axes=removed_adaptive_axis_names,
            regression_signal=regression_signal,
        ),
        regression_signal=regression_signal,
        next_action=restore_next_action(best_gate_reason, latest_gate_reason),
        latest_result_path=target.latest_result_path,
        best_result_path=target.best_result_path,
        source_target=target,
    )


def restore_next_action(best_gate_reason: str, latest_gate_reason: str) -> str:
    if best_gate_reason == "eligible_baseline_upgrade" and latest_gate_reason != "eligible_baseline_upgrade":
        return "restore_historical_best_then_ablate_latest_changes"
    if best_gate_reason != "eligible_baseline_upgrade":
        return "refresh_or_rebuild_historical_best_signal"
    return "compare_latest_against_best_before_rerun"


def restore_gate_reason(gate: dict[str, Any]) -> str:
    """Classify restore rows by local aggregate blockers before official-summary blockers."""
    reason = str(gate.get("reason", ""))
    if reason != "missing_official_candidate_summary":
        return reason
    holdout_cases = as_int(gate.get("holdout_cases"))
    min_holdout_cases = as_int(gate.get("min_holdout_cases"))
    if holdout_cases < min_holdout_cases:
        return "too_few_holdout_cases"
    holdout_rate = gate.get("holdout_resolved_rate")
    min_holdout_rate = gate.get("min_holdout_rate")
    if holdout_rate is None:
        return "missing_holdout"
    try:
        parsed_rate = float(cast(Any, holdout_rate))
        parsed_min_rate = float(cast(Any, min_holdout_rate))
    except (TypeError, ValueError):
        return "missing_holdout"
    if parsed_rate < parsed_min_rate:
        return "low_holdout_rate"
    return "eligible_baseline_upgrade"


def classify_regression_signal(
    *,
    latest_gate_reason: str,
    regression_delta: float,
    latest_axis_count: int,
    best_axis_count: int,
) -> str:
    if (
        regression_delta < 0
        and latest_gate_reason == "low_holdout_rate"
        and latest_axis_count > best_axis_count
    ):
        return "new_axis_expansion_regression"
    if regression_delta < 0 and latest_gate_reason == "low_holdout_rate":
        return "same_axis_holdout_regression"
    if regression_delta < 0:
        return "non_holdout_gate_regression"
    return "no_restore_regression"


def restore_sort_key(row: RestoreTargetAudit) -> tuple[int, float, str]:
    return (row.official_score, row.regression_delta, row.task_id)


def as_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if value is None:
        value = 0
    try:
        return int(cast(Any, value))
    except (TypeError, ValueError):
        return 0


def result_axis_sets(result_path: Path) -> tuple[set[str], set[str]]:
    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set(), set()
    if not isinstance(payload, dict):
        return set(), set()
    metadata = payload.get("implementation_metadata")
    if not isinstance(metadata, dict):
        return set(), set()
    coverage = metadata.get("probe_axis_coverage")
    if not isinstance(coverage, dict):
        return set(), set()
    return (
        normalized_axis_names(coverage.get("smoke_contract_axes")),
        normalized_axis_names(coverage.get("adaptive_axes")),
    )


def normalized_axis_names(value: object) -> set[str]:
    if not isinstance(value, list):
        return set()
    axes: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        axis = item.strip()
        if AXIS_NAME_PATTERN.fullmatch(axis):
            axes.add(axis)
    return axes


def format_axis_delta(
    *,
    smoke_axes: tuple[str, ...],
    adaptive_axes: tuple[str, ...],
    smoke_prefix: str,
    adaptive_prefix: str,
) -> str:
    parts = []
    if smoke_axes:
        parts.append(f"{smoke_prefix}:{format_axis_names(smoke_axes)}")
    if adaptive_axes:
        parts.append(f"{adaptive_prefix}:{format_axis_names(adaptive_axes)}")
    return "; ".join(parts) if parts else "none"


def format_axis_names(axes: tuple[str, ...]) -> str:
    selected = axes[:AXIS_SUMMARY_LIMIT]
    suffix = "" if len(axes) <= AXIS_SUMMARY_LIMIT else f",+{len(axes) - AXIS_SUMMARY_LIMIT} more"
    return ",".join(selected) + suffix


def axis_delta_action(
    *,
    added_smoke_axes: tuple[str, ...],
    added_adaptive_axes: tuple[str, ...],
    removed_smoke_axes: tuple[str, ...],
    removed_adaptive_axes: tuple[str, ...],
    regression_signal: str,
) -> str:
    added_domains = axis_domains(added_smoke_axes, added_adaptive_axes)
    if added_domains:
        return f"ablate_added_axis_domains:{','.join(added_domains)}"
    removed_domains = axis_domains(removed_smoke_axes, removed_adaptive_axes)
    if removed_domains:
        return f"compare_removed_axis_domains:{','.join(removed_domains)}"
    if regression_signal == "same_axis_holdout_regression":
        return "inspect_same_axis_strategy_regression"
    return "no_axis_delta"


def axis_domains(*axis_groups: tuple[str, ...]) -> tuple[str, ...]:
    domains = {
        axis.split(".", 1)[0]
        for axes in axis_groups
        for axis in axes
        if "." in axis
    }
    return tuple(sorted(domains))


def restore_audit_json_payload(rows: list[RestoreTargetAudit], limit: int) -> dict[str, object]:
    selected = rows[: max(0, limit)]
    return {
        "schema_version": 1,
        "row_count": len(selected),
        "total_row_count": len(rows),
        "limit": max(0, limit),
        "regression_signal_counts": count_values(row.regression_signal for row in rows),
        "axis_delta_action_counts": count_values(row.axis_delta_action for row in rows),
        "rows": [
            restore_audit_json_row(row, rank=index)
            for index, row in enumerate(selected, start=1)
        ],
    }


def count_values(values) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def restore_audit_json_row(row: RestoreTargetAudit, *, rank: int) -> dict[str, object]:
    return {
        "rank": rank,
        "task_id": row.task_id,
        "official_score": row.official_score,
        "official_summary": format_official(row.source_target),
        "regression_delta": row.regression_delta,
        "latest_gate_reason": row.latest_gate_reason,
        "best_gate_reason": row.best_gate_reason,
        "latest_holdout_resolved_rate": row.latest_holdout_resolved_rate,
        "latest_holdout_cases": row.latest_holdout_cases,
        "best_holdout_resolved_rate": row.best_holdout_resolved_rate,
        "best_holdout_cases": row.best_holdout_cases,
        "latest_smoke_contract_axis_count": row.latest_smoke_contract_axis_count,
        "latest_adaptive_axis_count": row.latest_adaptive_axis_count,
        "best_smoke_contract_axis_count": row.best_smoke_contract_axis_count,
        "best_adaptive_axis_count": row.best_adaptive_axis_count,
        "added_smoke_contract_axes": list(row.added_smoke_contract_axes),
        "added_adaptive_axes": list(row.added_adaptive_axes),
        "removed_smoke_contract_axes": list(row.removed_smoke_contract_axes),
        "removed_adaptive_axes": list(row.removed_adaptive_axes),
        "added_axis_summary": row.added_axis_summary,
        "removed_axis_summary": row.removed_axis_summary,
        "axis_delta_action": row.axis_delta_action,
        "regression_signal": row.regression_signal,
        "next_action": row.next_action,
        "latest_result_path": str(row.latest_result_path),
        "best_result_path": str(row.best_result_path),
    }


def write_json(rows: list[RestoreTargetAudit], limit: int) -> None:
    print(json.dumps(restore_audit_json_payload(rows, limit), indent=2, ensure_ascii=False))


def write_markdown(rows: list[RestoreTargetAudit], limit: int) -> None:
    selected = rows[: max(0, limit)]
    print(
        "| rank | task | official score | restore regression | latest gate | best gate | "
        "latest holdout | best holdout | latest axes | best axes | added axes | removed axes | axis action | regression signal | "
        "next action | latest result | best result |"
    )
    print("| ---: | --- | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- | --- | --- | --- | --- |")
    for index, row in enumerate(selected, start=1):
        print(
            f"| {index} | {row.task_id} | {format_official(row.source_target)} | "
            f"{format_rate(row.regression_delta)} | {row.latest_gate_reason} | {row.best_gate_reason} | "
            f"{format_rate(row.latest_holdout_resolved_rate)} ({row.latest_holdout_cases}) | "
            f"{format_rate(row.best_holdout_resolved_rate)} ({row.best_holdout_cases}) | "
            f"{row.latest_smoke_contract_axis_count}/{row.latest_adaptive_axis_count} | "
            f"{row.best_smoke_contract_axis_count}/{row.best_adaptive_axis_count} | "
            f"{row.added_axis_summary} | {row.removed_axis_summary} | "
            f"{row.axis_delta_action} | "
            f"{row.regression_signal} | {row.next_action} | {row.latest_result_path} | {row.best_result_path} |"
        )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    rows = collect_restore_target_audits(
        args.runs,
        args.baseline_root,
        official_eval_root=args.official_eval_root,
        min_holdout_cases=args.min_holdout_cases,
        min_holdout_rate=args.min_holdout_rate,
        task_ids=args.task_ids,
    )
    if args.format == "json":
        write_json(rows, args.limit)
    else:
        write_markdown(rows, args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
