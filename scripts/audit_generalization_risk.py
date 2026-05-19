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
from scripts.summarize_holdout_trends import (  # noqa: E402
    format_rate,
    non_negative_int,
    positive_int,
    rate_float,
)

RISK_ORDER = {"low": 0, "medium": 1, "high": 2}


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
    parser.add_argument("--min-holdout-cases", type=non_negative_int, default=10)
    parser.add_argument("--min-holdout-rate", type=rate_float, default=0.8)
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
) -> list[GeneralizationRisk]:
    targets = collect_official_breakthrough_targets(
        runs_root,
        baseline_root,
        min_holdout_cases=min_holdout_cases,
        min_holdout_rate=min_holdout_rate,
    )
    restore_audits = {
        row.task_id: row
        for row in collect_restore_target_audits(
            runs_root,
            baseline_root,
            official_eval_root=official_eval_root,
            min_holdout_cases=min_holdout_cases,
            min_holdout_rate=min_holdout_rate,
        )
    }
    risks = [build_generalization_risk(target, restore_audits.get(target.task_id)) for target in targets]
    return sorted(risks, key=risk_sort_key)


def build_generalization_risk(
    target: BreakthroughTarget,
    restore_audit: RestoreTargetAudit | None,
) -> GeneralizationRisk:
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
            latest_result_path=target.latest_result_path,
            best_result_path=target.best_result_path,
            source_target=target,
        )
    if target.target_class == "ready_baseline_gate":
        return base_risk(
            target,
            risk_level="low",
            risk_reason="latest_reliable_gate_pass",
            block=False,
            action="candidate_can_enter_baseline_upgrade_audit",
        )
    if target.target_class == "weak_cleanroom_rerun":
        return base_risk(
            target,
            risk_level="high",
            risk_reason="historical_best_below_gate",
            block=True,
            action="run_guarded_local_rerun_before_official_eval",
        )
    if target.target_class == "missing_reliable_holdout":
        return base_risk(
            target,
            risk_level="high",
            risk_reason="missing_reliable_holdout",
            block=True,
            action="build_reliable_holdout_signal_before_official_eval",
        )
    return base_risk(
        target,
        risk_level="medium",
        risk_reason="unknown_target_class",
        block=True,
        action="manual_aggregate_audit_required",
    )


def base_risk(
    target: BreakthroughTarget,
    *,
    risk_level: str,
    risk_reason: str,
    block: bool,
    action: str,
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
        latest_result_path=target.latest_result_path,
        best_result_path=target.best_result_path,
        source_target=target,
    )


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
        "block_official_eval | reason | latest holdout | best holdout | required next action | latest result |"
    )
    print("| ---: | --- | ---: | --- | --- | --- | --- | ---: | ---: | --- | --- |")
    for index, row in enumerate(selected, start=1):
        print(
            f"| {index} | {row.task_id} | {format_official(row.source_target)} | "
            f"{row.target_class} | {row.risk_level} | {format_bool(row.block_official_eval)} | "
            f"{row.risk_reason} | "
            f"{format_optional_holdout(row.latest_holdout_resolved_rate, row.latest_holdout_cases)} | "
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
    )
    write = write_json if args.format == "json" else write_markdown
    write(rows, args.limit)
    return 2 if should_fail(rows[: max(0, args.limit)], args.fail_on_risk) else 0


if __name__ == "__main__":
    raise SystemExit(main())
