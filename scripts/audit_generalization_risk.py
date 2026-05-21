"""Audit aggregate-only generalization risk before ProgramBench official eval."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit_restore_targets import (  # noqa: E402
    RestoreTargetAudit,
    collect_restore_target_audits,
)
from scripts.plan_official_breakthrough_targets import (  # noqa: E402
    BreakthroughTarget,
    collect_official_breakthrough_targets,
    format_official,
)
from scripts.rank_programbench_candidates import (  # noqa: E402
    OfficialRank,
    discover_baseline_official_ranks,
    discover_baseline_task_ids,
    discover_official_eval_task_ids,
    official_gate_reason,
    read_candidate_row,
)
from scripts.summarize_holdout_trends import (  # noqa: E402
    as_optional_float,
    format_rate,
    non_negative_int,
    positive_int,
    rate_float,
)

RISK_ORDER = {"low": 0, "medium": 1, "high": 2}
DEFAULT_MAX_LOCAL_HOLDOUT_GAP = 0.15


@dataclass(frozen=True)
class GeneralizationRisk:
    task_id: str
    official_score: int
    target_class: str
    risk_level: str
    risk_reason: str
    block_official_eval: bool
    required_next_action: str
    latest_holdout_resolved_rate: float | None
    latest_holdout_cases: int | None
    best_holdout_resolved_rate: float | None
    best_holdout_cases: int | None
    latest_local_resolved_rate: float | None
    latest_local_holdout_gap: float | None
    latest_result_path: Path | None
    best_result_path: Path | None
    source_target: BreakthroughTarget


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit aggregate-only generalization risk before official eval"
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
    parser.add_argument("--limit", type=positive_int, default=20, help="Maximum rows to print")
    parser.add_argument(
        "--task",
        action="append",
        default=[],
        help="Restrict output to one task id; may be repeated",
    )
    parser.add_argument("--min-holdout-cases", type=non_negative_int, default=10)
    parser.add_argument("--min-holdout-rate", type=rate_float, default=0.8)
    parser.add_argument(
        "--max-local-holdout-gap",
        type=rate_float,
        default=DEFAULT_MAX_LOCAL_HOLDOUT_GAP,
        help=(
            "Maximum allowed aggregate gap between local resolved_rate and "
            "holdout_resolved_rate before a gate-ready row is treated as overfit risk"
        ),
    )
    parser.add_argument(
        "--fail-on-risk",
        choices=["medium", "high"],
        default=None,
        help="Exit non-zero when any printed row is at or above this risk level",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format. JSON emits aggregate-only risk rows for automation.",
    )
    return parser.parse_args(argv)


def collect_generalization_risks(
    runs_root: Path | str,
    baseline_root: Path | str,
    *,
    official_eval_root: Path | str = "runs/programbench_official_eval",
    min_holdout_cases: int = 10,
    min_holdout_rate: float = 0.8,
    max_local_holdout_gap: float = DEFAULT_MAX_LOCAL_HOLDOUT_GAP,
) -> list[GeneralizationRisk]:
    baseline_root_path = Path(baseline_root)
    official_eval_root_path = Path(official_eval_root)
    targets = collect_official_breakthrough_targets(
        runs_root,
        baseline_root_path,
        min_holdout_cases=min_holdout_cases,
        min_holdout_rate=min_holdout_rate,
    )
    official_task_ids = discover_official_eval_task_ids(official_eval_root_path)
    official_task_ids.update(discover_baseline_task_ids(baseline_root_path))
    baseline_ranks = discover_baseline_official_ranks(baseline_root_path)
    restore_audits = {
        row.task_id: row
        for row in collect_restore_target_audits(
            runs_root,
            baseline_root_path,
            official_eval_root=official_eval_root_path,
            min_holdout_cases=min_holdout_cases,
            min_holdout_rate=min_holdout_rate,
        )
    }
    risks = [
        build_generalization_risk(
            target,
            restore_audits.get(target.task_id),
            max_local_holdout_gap=max_local_holdout_gap,
            official_task_ids=official_task_ids,
            baseline_ranks=baseline_ranks,
        )
        for target in targets
    ]
    return sorted(risks, key=risk_sort_key)


def build_generalization_risk(
    target: BreakthroughTarget,
    restore_audit: RestoreTargetAudit | None,
    *,
    max_local_holdout_gap: float = DEFAULT_MAX_LOCAL_HOLDOUT_GAP,
    official_task_ids: set[str] | None = None,
    baseline_ranks: dict[str, OfficialRank] | None = None,
) -> GeneralizationRisk:
    latest_local = read_latest_local_resolved_rate(target.latest_result_path)
    latest_gap = local_holdout_gap(latest_local, target.latest_holdout_resolved_rate)
    if restore_audit is not None:
        return GeneralizationRisk(
            task_id=target.task_id,
            official_score=target.official_score,
            target_class=target.target_class,
            risk_level="high",
            risk_reason=restore_audit.regression_signal,
            block_official_eval=True,
            required_next_action=restore_required_action(restore_audit.regression_signal),
            latest_holdout_resolved_rate=target.latest_holdout_resolved_rate,
            latest_holdout_cases=target.latest_holdout_cases,
            best_holdout_resolved_rate=target.best_holdout_resolved_rate,
            best_holdout_cases=target.best_holdout_cases,
            latest_local_resolved_rate=latest_local,
            latest_local_holdout_gap=latest_gap,
            latest_result_path=target.latest_result_path,
            best_result_path=target.best_result_path,
            source_target=target,
        )
    if target.target_class == "ready_baseline_gate":
        baseline_gate_reason = ready_baseline_upgrade_gate_reason(
            target,
            official_task_ids=official_task_ids or set(),
            baseline_ranks=baseline_ranks or {},
        )
        if baseline_gate_reason == "official_not_above_baseline":
            return base_risk(
                target,
                risk_level="high",
                risk_reason=baseline_gate_reason,
                block=True,
                action="improve_candidate_above_baseline_before_official_eval",
                latest_local_resolved_rate=latest_local,
                latest_local_holdout_gap=latest_gap,
            )
        if latest_gap is not None and latest_gap > max_local_holdout_gap:
            return base_risk(
                target,
                risk_level="high",
                risk_reason="local_holdout_gap_too_high",
                block=True,
                action="expand_unseen_holdout_before_official_eval",
                latest_local_resolved_rate=latest_local,
                latest_local_holdout_gap=latest_gap,
            )
        return base_risk(
            target,
            risk_level="low",
            risk_reason="latest_reliable_gate_pass",
            block=False,
            action="candidate_can_enter_baseline_upgrade_audit",
            latest_local_resolved_rate=latest_local,
            latest_local_holdout_gap=latest_gap,
        )
    if target.target_class == "weak_cleanroom_rerun":
        return base_risk(
            target,
            risk_level="high",
            risk_reason="historical_best_below_gate",
            block=True,
            action="run_guarded_local_rerun_before_official_eval",
            latest_local_resolved_rate=latest_local,
            latest_local_holdout_gap=latest_gap,
        )
    if target.target_class == "missing_reliable_holdout":
        return base_risk(
            target,
            risk_level="high",
            risk_reason="missing_reliable_holdout",
            block=True,
            action="build_reliable_holdout_signal_before_official_eval",
            latest_local_resolved_rate=latest_local,
            latest_local_holdout_gap=latest_gap,
        )
    return base_risk(
        target,
        risk_level="medium",
        risk_reason="unknown_target_class",
        block=True,
        action="manual_aggregate_audit_required",
        latest_local_resolved_rate=latest_local,
        latest_local_holdout_gap=latest_gap,
    )


def ready_baseline_upgrade_gate_reason(
    target: BreakthroughTarget,
    *,
    official_task_ids: set[str],
    baseline_ranks: dict[str, OfficialRank],
) -> str | None:
    if target.latest_result_path is None:
        return None
    row = read_candidate_row(target.latest_result_path, official_task_ids, baseline_ranks)
    if row is None:
        return None
    return official_gate_reason(row, allow_existing_official=True)


def base_risk(
    target: BreakthroughTarget,
    *,
    risk_level: str,
    risk_reason: str,
    block: bool,
    action: str,
    latest_local_resolved_rate: float | None,
    latest_local_holdout_gap: float | None,
) -> GeneralizationRisk:
    return GeneralizationRisk(
        task_id=target.task_id,
        official_score=target.official_score,
        target_class=target.target_class,
        risk_level=risk_level,
        risk_reason=risk_reason,
        block_official_eval=block,
        required_next_action=action,
        latest_holdout_resolved_rate=target.latest_holdout_resolved_rate,
        latest_holdout_cases=target.latest_holdout_cases,
        best_holdout_resolved_rate=target.best_holdout_resolved_rate,
        best_holdout_cases=target.best_holdout_cases,
        latest_local_resolved_rate=latest_local_resolved_rate,
        latest_local_holdout_gap=latest_local_holdout_gap,
        latest_result_path=target.latest_result_path,
        best_result_path=target.best_result_path,
        source_target=target,
    )


def read_latest_local_resolved_rate(path: Path | None) -> float | None:
    if path is None:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return as_optional_float(payload.get("resolved_rate"))


def local_holdout_gap(
    local_resolved_rate: float | None,
    holdout_resolved_rate: float | None,
) -> float | None:
    if local_resolved_rate is None or holdout_resolved_rate is None:
        return None
    return max(0.0, local_resolved_rate - holdout_resolved_rate)


def restore_required_action(regression_signal: str) -> str:
    if regression_signal == "new_axis_expansion_regression":
        return "ablate_axis_expansion_before_official_eval"
    return "restore_historical_best_before_official_eval"


def risk_sort_key(row: GeneralizationRisk) -> tuple[int, int, str]:
    return (-RISK_ORDER.get(row.risk_level, 99), row.official_score, row.task_id)


def format_optional_holdout(rate: float | None, cases: int | None) -> str:
    if rate is None:
        return "-"
    if cases is None:
        return format_rate(rate)
    return f"{format_rate(rate)} ({cases})"


def write_markdown(rows: list[GeneralizationRisk], limit: int) -> None:
    selected = rows[: max(0, limit)]
    print(
        "| rank | task | official score | target class | generalization risk | "
        "block_official_eval | reason | latest local | latest holdout | local-holdout gap | best holdout | required next action | latest result |"
    )
    print("| ---: | --- | ---: | --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- |")
    for index, row in enumerate(selected, start=1):
        print(
            f"| {index} | {row.task_id} | {format_official(row.source_target)} | "
            f"{row.target_class} | {row.risk_level} | {format_bool(row.block_official_eval)} | "
            f"{row.risk_reason} | "
            f"{format_optional_rate(row.latest_local_resolved_rate)} | "
            f"{format_optional_holdout(row.latest_holdout_resolved_rate, row.latest_holdout_cases)} | "
            f"{format_optional_rate(row.latest_local_holdout_gap)} | "
            f"{format_optional_holdout(row.best_holdout_resolved_rate, row.best_holdout_cases)} | "
            f"{row.required_next_action} | {format_path(row.latest_result_path)} |"
        )


def optional_holdout_json(resolved_rate: float | None, cases: int | None) -> dict[str, object] | None:
    if resolved_rate is None:
        return None
    return {
        "resolved_rate": resolved_rate,
        "cases": cases,
    }


def format_optional_rate(rate: float | None) -> str:
    if rate is None:
        return "-"
    return format_rate(rate)


def format_json_path(path: Path | None) -> str | None:
    if path is None:
        return None
    return str(path)


def generalization_risk_json_row(row: GeneralizationRisk, rank: int) -> dict[str, object]:
    source = row.source_target
    return {
        "rank": rank,
        "task_id": row.task_id,
        "official": {
            "score": source.official_score,
            "pass_rate": source.official_pass_rate,
            "passed_tests": source.passed_tests,
            "total_tests": source.total_tests,
        },
        "target_class": row.target_class,
        "risk_level": row.risk_level,
        "risk_reason": row.risk_reason,
        "block_official_eval": row.block_official_eval,
        "required_next_action": row.required_next_action,
        "latest_local_resolved_rate": row.latest_local_resolved_rate,
        "latest_local_holdout_gap": row.latest_local_holdout_gap,
        "latest_holdout": optional_holdout_json(row.latest_holdout_resolved_rate, row.latest_holdout_cases),
        "best_holdout": optional_holdout_json(row.best_holdout_resolved_rate, row.best_holdout_cases),
        "latest_result_path": format_json_path(row.latest_result_path),
        "best_result_path": format_json_path(row.best_result_path),
        "baseline_path": format_json_path(source.baseline_path),
    }


def generalization_risk_json_payload(rows: list[GeneralizationRisk], limit: int) -> dict[str, object]:
    selected = rows[: max(0, limit)]
    return {
        "schema_version": 1,
        "row_count": len(selected),
        "total_row_count": len(rows),
        "limit": limit,
        "rows": [generalization_risk_json_row(row, rank) for rank, row in enumerate(selected, start=1)],
    }


def write_json(rows: list[GeneralizationRisk], limit: int) -> None:
    print(json.dumps(generalization_risk_json_payload(rows, limit), indent=2, ensure_ascii=False))


def format_bool(value: bool) -> str:
    return "yes" if value else "no"


def format_path(path: Path | None) -> str:
    return str(path) if path is not None else "-"


def should_fail(rows: list[GeneralizationRisk], fail_on_risk: str | None) -> bool:
    if fail_on_risk is None:
        return False
    threshold = RISK_ORDER[fail_on_risk]
    return any(RISK_ORDER.get(row.risk_level, 99) >= threshold for row in rows)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    rows = collect_generalization_risks(
        args.runs,
        args.baseline_root,
        official_eval_root=args.official_eval_root,
        min_holdout_cases=args.min_holdout_cases,
        min_holdout_rate=args.min_holdout_rate,
        max_local_holdout_gap=args.max_local_holdout_gap,
    )
    if args.task:
        selected_tasks = set(args.task)
        rows = [row for row in rows if row.task_id in selected_tasks]
    write = write_json if args.format == "json" else write_markdown
    write(rows, args.limit)
    return 2 if should_fail(rows[: max(0, args.limit)], args.fail_on_risk) else 0


if __name__ == "__main__":
    raise SystemExit(main())
