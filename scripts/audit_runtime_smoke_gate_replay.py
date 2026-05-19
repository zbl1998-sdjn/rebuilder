"""Cross-audit official gate blockers against local runtime-smoke replay."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit_runtime_smoke_replay import audit_result_for_runtime_smoke_replay  # noqa: E402
from scripts.rank_programbench_candidates import (  # noqa: E402
    CandidateRow,
    collect_candidates,
    non_negative_float,
    non_negative_int,
    normalize_required_runtime_smoke_dimensions,
    official_gate_blockers,
    positive_int,
    rate_float,
    runtime_smoke_dimensions,
)


RUNTIME_GATE_BLOCKERS = {
    "runtime_smoke_not_passed",
    "insufficient_runtime_smoke_dimensions",
}


@dataclass(frozen=True)
class RuntimeSmokeGateReplayRow:
    task_id: str
    status: str
    holdout_resolved_rate: float | None
    holdout_cases: int
    has_official_eval: bool
    original_blockers: tuple[str, ...]
    replay_status: str
    replay_runtime_smoke_status: str
    replay_input_dimensions: tuple[str, ...]
    replay_failed_issue_kind: str | None
    missing_required_dimensions: tuple[str, ...]
    runtime_blockers_resolved: bool
    remaining_blockers_after_replay: tuple[str, ...]
    result_path: Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audit whether local runtime-smoke replay would remove strict "
            "official-gate runtime blockers without mutating result.json."
        )
    )
    parser.add_argument("--runs", default="runs", help="Root directory containing run result.json files")
    parser.add_argument(
        "--task",
        dest="task_ids",
        action="append",
        default=None,
        help="Limit output to a specific task_id; may be repeated",
    )
    parser.add_argument(
        "--status",
        dest="statuses",
        action="append",
        default=None,
        help="Limit output to a replay gate status; may be repeated",
    )
    parser.add_argument(
        "--replay-failed-issue-kind",
        dest="replay_failed_issue_kinds",
        action="append",
        default=None,
        help="Limit output to a runtime-smoke replay failure issue kind; may be repeated",
    )
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
    parser.add_argument("--limit", type=positive_int, default=50, help="Maximum rows to print")
    parser.add_argument(
        "--min-holdout-cases",
        type=non_negative_int,
        default=10,
        help="Minimum holdout cases required for official-eval eligibility",
    )
    parser.add_argument(
        "--min-holdout-rate",
        type=rate_float,
        default=0.8,
        help="Minimum holdout resolved rate required for official-eval eligibility",
    )
    parser.add_argument(
        "--min-smoke-contract-axes",
        type=non_negative_int,
        default=0,
        help="Optional minimum local smoke-contract axes required for eligibility",
    )
    parser.add_argument(
        "--require-runtime-smoke-dimensions",
        type=runtime_smoke_dimensions,
        default=(),
        help="Comma-separated runtime-smoke input dimensions required for eligibility",
    )
    parser.add_argument(
        "--require-holdout-improvement",
        action="store_true",
        help="Require candidates to beat the previous reliable local holdout best",
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
        "--allow-existing-official",
        action="store_true",
        help="Allow existing official/baseline tasks to pass local gates as baseline-upgrade candidates",
    )
    parser.add_argument(
        "--only-unofficial",
        action="store_true",
        help="Only audit tasks without an existing official eval artifact",
    )
    parser.add_argument(
        "--latest-per-task",
        action="store_true",
        help="Audit each task by its newest result.json instead of its best historical score",
    )
    parser.add_argument(
        "--execute-replay",
        action="store_true",
        help="Actually execute local runtime-smoke replay checks before resolving runtime blockers",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format. JSON emits aggregate-only rows.",
    )
    return parser.parse_args(argv)


def audit_runtime_smoke_gate_replay(
    *,
    runs_root: Path | str,
    official_eval_root: Path | str,
    baseline_root: Path | str = "baselines/programbench",
    only_unofficial: bool = False,
    min_holdout_cases: int = 10,
    min_holdout_rate: float = 0.8,
    min_smoke_contract_axes: int = 0,
    required_runtime_smoke_dimensions: tuple[str, ...] | list[str] | str | None = (),
    require_holdout_improvement: bool = False,
    holdout_history_root: Path | str | None = None,
    min_holdout_improvement_delta: float = 0.0,
    allow_existing_official: bool = False,
    latest_per_task: bool = False,
    execute_replay: bool = False,
    task_ids: tuple[str, ...] | list[str] | None = None,
    statuses: tuple[str, ...] | list[str] | None = None,
    replay_failed_issue_kinds: tuple[str, ...] | list[str] | None = None,
) -> list[RuntimeSmokeGateReplayRow]:
    required_dimensions = normalize_required_runtime_smoke_dimensions(
        required_runtime_smoke_dimensions
    )
    rows = collect_candidates(
        runs_root,
        official_eval_root,
        baseline_root=baseline_root,
        only_unofficial=only_unofficial,
        min_holdout_cases=min_holdout_cases,
        min_holdout_rate=min_holdout_rate,
        min_smoke_contract_axes=min_smoke_contract_axes,
        required_runtime_smoke_dimensions=required_dimensions,
        require_holdout_improvement=require_holdout_improvement,
        holdout_history_root=holdout_history_root or runs_root,
        min_holdout_improvement_delta=min_holdout_improvement_delta,
        official_eligible_only=False,
        allow_existing_official=allow_existing_official,
        latest_per_task=latest_per_task,
    )
    selected_tasks = set(task_ids or ())
    if selected_tasks:
        rows = [row for row in rows if row.task_id in selected_tasks]
    audited = [
        audit_candidate_gate_replay(
            row,
            min_holdout_cases=min_holdout_cases,
            min_holdout_rate=min_holdout_rate,
            min_smoke_contract_axes=min_smoke_contract_axes,
            required_runtime_smoke_dimensions=required_dimensions,
            require_holdout_improvement=require_holdout_improvement,
            holdout_history_root=holdout_history_root or runs_root,
            min_holdout_improvement_delta=min_holdout_improvement_delta,
            allow_existing_official=allow_existing_official,
            execute_replay=execute_replay,
        )
        for row in rows
    ]
    selected_statuses = set(statuses or ())
    if selected_statuses:
        audited = [row for row in audited if row.status in selected_statuses]
    selected_issue_kinds = set(replay_failed_issue_kinds or ())
    if selected_issue_kinds:
        audited = [
            row
            for row in audited
            if row.replay_failed_issue_kind in selected_issue_kinds
        ]
    return audited


def audit_candidate_gate_replay(
    row: CandidateRow,
    *,
    min_holdout_cases: int,
    min_holdout_rate: float,
    min_smoke_contract_axes: int,
    required_runtime_smoke_dimensions: tuple[str, ...] | list[str] | str | None,
    require_holdout_improvement: bool,
    holdout_history_root: Path | str,
    min_holdout_improvement_delta: float,
    allow_existing_official: bool,
    execute_replay: bool,
) -> RuntimeSmokeGateReplayRow:
    original_blockers = tuple(
        official_gate_blockers(
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
    )
    has_runtime_blocker = bool(RUNTIME_GATE_BLOCKERS.intersection(original_blockers))
    if not has_runtime_blocker:
        return RuntimeSmokeGateReplayRow(
            task_id=row.task_id,
            status="metadata_already_sufficient",
            holdout_resolved_rate=row.holdout_resolved_rate,
            holdout_cases=row.holdout_cases,
            has_official_eval=row.has_official_eval,
            original_blockers=original_blockers,
            replay_status="not_needed",
            replay_runtime_smoke_status=row.runtime_smoke_status,
            replay_input_dimensions=row.runtime_smoke_input_dimensions,
            replay_failed_issue_kind=None,
            missing_required_dimensions=(),
            runtime_blockers_resolved=False,
            remaining_blockers_after_replay=original_blockers,
            result_path=row.result_path,
        )

    replay = audit_result_for_runtime_smoke_replay(
        row.result_path,
        required_runtime_smoke_dimensions=normalize_required_runtime_smoke_dimensions(
            required_runtime_smoke_dimensions
        ),
        execute=execute_replay,
    )
    replay_resolved = replay.status == "replay_passed"
    remaining_blockers = original_blockers
    if replay_resolved:
        remaining_blockers = tuple(
            blocker for blocker in original_blockers if blocker not in RUNTIME_GATE_BLOCKERS
        )
    status = replay_gate_status(
        replay_status=replay.status,
        replay_resolved=replay_resolved,
        remaining_blockers=remaining_blockers,
        replay_failed_issue_kind=replay.failed_issue_kind,
    )
    return RuntimeSmokeGateReplayRow(
        task_id=row.task_id,
        status=status,
        holdout_resolved_rate=row.holdout_resolved_rate,
        holdout_cases=row.holdout_cases,
        has_official_eval=row.has_official_eval,
        original_blockers=original_blockers,
        replay_status=replay.status,
        replay_runtime_smoke_status=replay.replay_runtime_smoke_status,
        replay_input_dimensions=replay.replay_runtime_smoke_input_dimensions,
        replay_failed_issue_kind=replay.failed_issue_kind,
        missing_required_dimensions=replay.missing_required_dimensions,
        runtime_blockers_resolved=replay_resolved,
        remaining_blockers_after_replay=remaining_blockers,
        result_path=row.result_path,
    )


def replay_gate_status(
    *,
    replay_status: str,
    replay_resolved: bool,
    remaining_blockers: tuple[str, ...],
    replay_failed_issue_kind: str | None = None,
) -> str:
    if replay_resolved and not remaining_blockers:
        return "metadata_only_runtime_smoke_blocker"
    if replay_resolved:
        return "replay_resolved_but_other_blockers_remain"
    if replay_status == "ready_for_replay":
        return "ready_for_replay_not_executed"
    if replay_failed_issue_kind == "runtime_smoke_executor_permission_denied":
        return "replay_environment_blocked"
    return "replay_failed_or_incomplete"


def gate_replay_json_row(row: RuntimeSmokeGateReplayRow, rank: int) -> dict[str, object]:
    return {
        "rank": rank,
        "task_id": row.task_id,
        "status": row.status,
        "holdout_resolved_rate": row.holdout_resolved_rate,
        "holdout_cases": row.holdout_cases,
        "has_official_eval": row.has_official_eval,
        "original_blockers": list(row.original_blockers),
        "replay_status": row.replay_status,
        "replay_runtime_smoke_status": row.replay_runtime_smoke_status,
        "replay_input_dimensions": list(row.replay_input_dimensions),
        "replay_failed_issue_kind": row.replay_failed_issue_kind,
        "missing_required_dimensions": list(row.missing_required_dimensions),
        "runtime_blockers_resolved": row.runtime_blockers_resolved,
        "remaining_blockers_after_replay": list(row.remaining_blockers_after_replay),
        "result_path": str(row.result_path),
    }


def gate_replay_json_payload(
    rows: list[RuntimeSmokeGateReplayRow],
    limit: int,
) -> dict[str, object]:
    selected = rows[: max(0, limit)]
    return {
        "schema_version": 1,
        "row_count": len(selected),
        "total_row_count": len(rows),
        "limit": limit,
        "status_counts": count_values(row.status for row in rows),
        "replay_failed_issue_kind_counts": count_values(
            row.replay_failed_issue_kind
            for row in rows
            if row.replay_failed_issue_kind
        ),
        "rows": [
            gate_replay_json_row(row, rank)
            for rank, row in enumerate(selected, start=1)
        ],
    }


def count_values(values) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def write_json(rows: list[RuntimeSmokeGateReplayRow], limit: int) -> None:
    print(json.dumps(gate_replay_json_payload(rows, limit), indent=2, ensure_ascii=False))


def write_markdown(rows: list[RuntimeSmokeGateReplayRow], limit: int) -> None:
    selected = rows[: max(0, limit)]
    print(
        "| rank | task | status | holdout | cases | original blockers | "
        "replay | replay dims | replay failed issue | remaining blockers | result |"
    )
    print("| ---: | --- | --- | ---: | ---: | --- | --- | --- | --- | --- | --- |")
    for rank, row in enumerate(selected, start=1):
        print(
            f"| {rank} | {row.task_id} | {row.status} | "
            f"{format_rate(row.holdout_resolved_rate)} | {row.holdout_cases} | "
            f"{format_list(row.original_blockers)} | {row.replay_status} | "
            f"{format_list(row.replay_input_dimensions)} | "
            f"{row.replay_failed_issue_kind or '-'} | "
            f"{format_list(row.remaining_blockers_after_replay)} | {row.result_path} |"
        )


def format_rate(value: float | None) -> str:
    return "-" if value is None else f"{value:.1%}"


def format_list(values: tuple[str, ...]) -> str:
    return ",".join(values) if values else "-"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    rows = audit_runtime_smoke_gate_replay(
        runs_root=args.runs,
        official_eval_root=args.official_eval_root,
        baseline_root=args.baseline_root,
        only_unofficial=args.only_unofficial,
        min_holdout_cases=args.min_holdout_cases,
        min_holdout_rate=args.min_holdout_rate,
        min_smoke_contract_axes=args.min_smoke_contract_axes,
        required_runtime_smoke_dimensions=args.require_runtime_smoke_dimensions,
        require_holdout_improvement=args.require_holdout_improvement,
        holdout_history_root=args.holdout_history_root or args.runs,
        min_holdout_improvement_delta=args.min_holdout_improvement_delta,
        allow_existing_official=args.allow_existing_official,
        latest_per_task=args.latest_per_task,
        execute_replay=args.execute_replay,
        task_ids=args.task_ids,
        statuses=args.statuses,
        replay_failed_issue_kinds=args.replay_failed_issue_kinds,
    )
    write = write_json if args.format == "json" else write_markdown
    write(rows, args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
