"""Audit local-green ProgramBench candidates that fail aggregate official uplift."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.evaluation import ProgramBenchEvalParser  # noqa: E402
from scripts.rank_programbench_candidates import (  # noqa: E402
    CandidateRow,
    OfficialRank,
    collect_candidates,
    format_rate,
    local_holdout_gap as candidate_local_holdout_gap,
    non_negative_int,
    normalize_required_runtime_smoke_dimensions,
    positive_int,
    rate_float,
    runtime_smoke_dimensions,
    validate_gate_thresholds,
)


PROBE_DOMAIN_SPRAWL_THRESHOLD = 4


@dataclass(frozen=True)
class OfficialGeneralizationGapRow:
    task_id: str
    gap_kind: str
    local_resolved_rate: float
    holdout_resolved_rate: float | None
    local_holdout_gap: float | None
    holdout_cases: int
    smoke_contract_axis_count: int
    adaptive_axis_count: int
    runtime_smoke_status: str
    runtime_smoke_input_dimensions: tuple[str, ...]
    candidate_official_rank: OfficialRank
    recorded_baseline_rank: OfficialRank
    candidate_official_counted: dict[str, Any] | None
    candidate_official_raw: dict[str, Any] | None
    recorded_baseline_counted: dict[str, Any] | None
    recorded_baseline_raw: dict[str, Any] | None
    probe_domains: tuple[str, ...]
    probe_domain_count: int
    probe_domain_sprawl: bool
    official_score_delta: int
    official_passed_delta: int
    result_path: Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Find aggregate-only official generalization gaps: candidates that pass "
            "local holdout/runtime-smoke gates but whose embedded official aggregate "
            "does not beat the recorded baseline."
        )
    )
    parser.add_argument("--runs", default="runs", help="Root directory containing result.json files")
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
        "--task",
        action="append",
        default=[],
        help="Limit the audit to a specific ProgramBench instance id. May be repeated.",
    )
    parser.add_argument(
        "--min-holdout-cases",
        type=non_negative_int,
        default=10,
        help="Minimum local holdout cases required before classifying a gap",
    )
    parser.add_argument(
        "--min-holdout-rate",
        type=rate_float,
        default=0.8,
        help="Minimum local holdout rate required before classifying a gap",
    )
    parser.add_argument(
        "--require-runtime-smoke-dimensions",
        type=runtime_smoke_dimensions,
        default=(),
        help="Comma-separated runtime-smoke dimensions required before classifying a gap",
    )
    parser.add_argument(
        "--latest-per-task",
        action="store_true",
        help="Audit each task by newest result.json instead of best historical local score",
    )
    parser.add_argument(
        "--max-local-holdout-gap",
        type=rate_float,
        default=None,
        help="Exclude candidates whose local minus holdout pass-rate gap exceeds this threshold",
    )
    parser.add_argument(
        "--include-next-command",
        action="store_true",
        help="Include a task-scoped aggregate-only recheck command for each gap row",
    )
    parser.add_argument(
        "--fail-on-gap",
        action="store_true",
        help="Exit with status 1 after printing output when any aggregate gap is found",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format. JSON emits aggregate-only gap rows.",
    )
    parser.add_argument(
        "--sort-by",
        choices=("official-delta", "diagnostic-priority"),
        default="official-delta",
        help=(
            "Sort gap rows by official regression severity or by local-to-official "
            "diagnostic priority."
        ),
    )
    return parser.parse_args(argv)


def collect_generalization_gaps(
    *,
    runs_root: Path | str,
    official_eval_root: Path | str,
    baseline_root: Path | str = "baselines/programbench",
    min_holdout_cases: int = 10,
    min_holdout_rate: float = 0.8,
    required_runtime_smoke_dimensions: tuple[str, ...] | list[str] | str | None = (),
    latest_per_task: bool = False,
    task_ids: set[str] | list[str] | tuple[str, ...] | None = None,
    max_local_holdout_gap: float | None = None,
    sort_by: str = "official-delta",
) -> list[OfficialGeneralizationGapRow]:
    required_dimensions = normalize_required_runtime_smoke_dimensions(
        required_runtime_smoke_dimensions
    )
    validate_gate_thresholds(
        min_holdout_rate=min_holdout_rate,
        min_holdout_cases=min_holdout_cases,
        min_smoke_contract_axes=0,
        min_holdout_improvement_delta=0.0,
        required_runtime_smoke_dimensions=required_dimensions,
        max_local_holdout_gap=max_local_holdout_gap,
    )
    selected_task_ids = set(task_ids or ())
    candidates = collect_candidates(
        runs_root,
        official_eval_root,
        baseline_root=baseline_root,
        min_holdout_cases=min_holdout_cases,
        min_holdout_rate=min_holdout_rate,
        required_runtime_smoke_dimensions=required_dimensions,
        allow_existing_official=True,
        latest_per_task=latest_per_task,
    )
    rows = [
        gap_row_from_candidate(candidate, baseline_root=Path(baseline_root))
        for candidate in candidates
        if not selected_task_ids or candidate.task_id in selected_task_ids
        if is_local_green_official_gap(
            candidate,
            min_holdout_cases=min_holdout_cases,
            min_holdout_rate=min_holdout_rate,
            required_runtime_smoke_dimensions=required_dimensions,
            max_local_holdout_gap=max_local_holdout_gap,
        )
    ]
    if sort_by == "diagnostic-priority":
        return sorted(rows, key=diagnostic_sort_key)
    return sorted(rows, key=gap_sort_key)


def is_local_green_official_gap(
    candidate: CandidateRow,
    *,
    min_holdout_cases: int,
    min_holdout_rate: float,
    required_runtime_smoke_dimensions: tuple[str, ...],
    max_local_holdout_gap: float | None,
) -> bool:
    if candidate.embedded_official_rank is None or candidate.recorded_baseline_rank is None:
        return False
    if candidate.embedded_official_rank > candidate.recorded_baseline_rank:
        return False
    if candidate.holdout_resolved_rate is None:
        return False
    if candidate.holdout_resolved_rate < min_holdout_rate:
        return False
    if candidate.holdout_cases < min_holdout_cases:
        return False
    gap = candidate_local_holdout_gap(candidate)
    if max_local_holdout_gap is not None and gap is not None and gap > max_local_holdout_gap:
        return False
    if required_runtime_smoke_dimensions:
        if candidate.runtime_smoke_status != "passed":
            return False
        if not set(required_runtime_smoke_dimensions).issubset(
            set(candidate.runtime_smoke_input_dimensions)
        ):
            return False
    return True


def gap_row_from_candidate(
    candidate: CandidateRow,
    *,
    baseline_root: Path,
) -> OfficialGeneralizationGapRow:
    if candidate.embedded_official_rank is None or candidate.recorded_baseline_rank is None:
        raise ValueError("candidate must include embedded and baseline official ranks")
    candidate_score = official_score(candidate.embedded_official_rank)
    baseline_score = official_score(candidate.recorded_baseline_rank)
    candidate_passed = official_passed_tests(candidate.embedded_official_rank)
    baseline_passed = official_passed_tests(candidate.recorded_baseline_rank)
    baseline_payload = read_baseline_payload(baseline_root, candidate.task_id)
    probe_domains = read_result_probe_domains(candidate.result_path)
    return OfficialGeneralizationGapRow(
        task_id=candidate.task_id,
        gap_kind=(
            "official_regressed"
            if candidate.embedded_official_rank < candidate.recorded_baseline_rank
            else "official_equal_baseline"
        ),
        local_resolved_rate=candidate.resolved_rate,
        holdout_resolved_rate=candidate.holdout_resolved_rate,
        local_holdout_gap=candidate_local_holdout_gap(candidate),
        holdout_cases=candidate.holdout_cases,
        smoke_contract_axis_count=candidate.smoke_contract_axis_count,
        adaptive_axis_count=candidate.adaptive_axis_count,
        runtime_smoke_status=candidate.runtime_smoke_status,
        runtime_smoke_input_dimensions=candidate.runtime_smoke_input_dimensions,
        candidate_official_rank=candidate.embedded_official_rank,
        recorded_baseline_rank=candidate.recorded_baseline_rank,
        candidate_official_counted=read_result_official_summary(
            candidate.result_path, "counted"
        ),
        candidate_official_raw=read_result_official_summary(candidate.result_path, "raw"),
        recorded_baseline_counted=read_baseline_official_summary(baseline_payload),
        recorded_baseline_raw=read_baseline_raw_summary(
            baseline_payload,
            task_id=candidate.task_id,
        ),
        probe_domains=probe_domains,
        probe_domain_count=len(probe_domains),
        probe_domain_sprawl=len(probe_domains) >= PROBE_DOMAIN_SPRAWL_THRESHOLD,
        official_score_delta=candidate_score - baseline_score,
        official_passed_delta=candidate_passed - baseline_passed,
        result_path=candidate.result_path,
    )


def gap_sort_key(row: OfficialGeneralizationGapRow) -> tuple[int, int, float, int, str]:
    return (
        row.official_score_delta,
        row.official_passed_delta,
        -(row.holdout_resolved_rate if row.holdout_resolved_rate is not None else -1.0),
        -row.holdout_cases,
        row.task_id,
    )


def diagnostic_sort_key(row: OfficialGeneralizationGapRow) -> tuple[float, int, int, str]:
    return (
        -diagnostic_priority(row),
        row.official_score_delta,
        row.official_passed_delta,
        row.task_id,
    )


def generalization_failure_mode(row: OfficialGeneralizationGapRow) -> str:
    official_rate = official_pass_rate(row.candidate_official_rank)
    holdout_rate = row.holdout_resolved_rate if row.holdout_resolved_rate is not None else 0.0
    if row.local_resolved_rate >= 0.95 and holdout_rate >= 0.95 and official_rate <= 0.05:
        return "official_collapse_after_local_green"
    if row.official_score_delta < 0:
        return "official_regression_after_local_green"
    if row.official_passed_delta < 0:
        return "counted_tie_pass_loss"
    return "official_equal_baseline"


def diagnostic_priority(row: OfficialGeneralizationGapRow) -> float:
    holdout_rate = row.holdout_resolved_rate if row.holdout_resolved_rate is not None else 0.0
    official_rate = official_pass_rate(row.candidate_official_rank)
    local_gate_rate = min(row.local_resolved_rate, holdout_rate)
    predictiveness_gap = max(0.0, local_gate_rate - official_rate)
    mode_bonus = {
        "official_collapse_after_local_green": 100.0,
        "official_regression_after_local_green": 50.0,
        "counted_tie_pass_loss": 25.0,
        "official_equal_baseline": 0.0,
    }[generalization_failure_mode(row)]
    probe_domain_bonus = 5.0 if row.probe_domain_sprawl else 0.0
    return mode_bonus + probe_domain_bonus + predictiveness_gap


def official_score(rank: OfficialRank) -> int:
    return int(rank[2])


def official_passed_tests(rank: OfficialRank) -> int:
    return int(rank[3])


def official_pass_rate(rank: OfficialRank) -> float:
    return float(rank[4])


def read_result_official_summary(result_path: Path, key: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    summary = payload.get("official_eval_summary")
    if not isinstance(summary, dict):
        return None
    if key == "counted":
        counted = summary.get("counted")
        return official_summary_json(counted if isinstance(counted, dict) else summary)
    return official_summary_json(summary.get(key))


def read_result_probe_domains(result_path: Path) -> tuple[str, ...]:
    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    if not isinstance(payload, dict):
        return ()
    metadata = payload.get("implementation_metadata")
    if not isinstance(metadata, dict):
        return ()
    coverage = metadata.get("probe_axis_coverage")
    if not isinstance(coverage, dict):
        return ()
    domains: set[str] = set()
    domains.update(string_items(coverage.get("smoke_contract_domains")))
    domains.update(string_items(coverage.get("adaptive_domains")))
    domains.update(axis_domains(coverage.get("smoke_contract_axes")))
    domains.update(axis_domains(coverage.get("adaptive_axes")))
    return tuple(sorted(domains))


def string_items(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item)


def axis_domains(value: object) -> tuple[str, ...]:
    domains = []
    for axis in string_items(value):
        domain = axis.split(".", 1)[0]
        if domain:
            domains.append(domain)
    return tuple(domains)


def read_baseline_payload(root: Path, task_id: str) -> dict[str, Any] | None:
    if not root.exists():
        return None
    for path in root.glob("*.baseline.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        if payload.get("instance_id") == task_id:
            return payload
    return None


def read_baseline_official_summary(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    return official_summary_json(payload.get("official"))


def read_baseline_raw_summary(
    payload: dict[str, Any] | None,
    *,
    task_id: str,
) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    submission = payload.get("submission")
    if not isinstance(submission, dict):
        return None
    submission_path = submission.get("path")
    if not isinstance(submission_path, str) or not submission_path:
        return None
    archive_path = Path(submission_path)
    if not archive_path.is_absolute():
        archive_path = ROOT / archive_path
    eval_path = archive_path.parent / f"{task_id}.eval.json"
    if not eval_path.exists():
        return None
    return eval_summary_json(ProgramBenchEvalParser().parse(eval_path))


def official_summary_json(summary: object) -> dict[str, Any] | None:
    if not isinstance(summary, dict):
        return None
    passed_tests = as_non_negative_int(summary.get("passed_tests"))
    total_tests = as_non_negative_int(summary.get("total_tests"))
    pass_rate = as_optional_rate(summary.get("pass_rate"))
    if pass_rate is None and total_tests:
        pass_rate = passed_tests / total_tests
    return {
        "score": as_non_negative_int(summary.get("score")),
        "passed_tests": passed_tests,
        "total_tests": total_tests,
        "pass_rate": pass_rate or 0.0,
        "fully_resolved": summary.get("fully_resolved") is True,
        "almost_resolved": summary.get("almost_resolved") is True,
    }


def eval_summary_json(summary: Any) -> dict[str, Any]:
    return {
        "score": round(float(summary.score) * 100),
        "passed_tests": int(summary.passed_tests),
        "total_tests": int(summary.total_tests),
        "pass_rate": float(summary.pass_rate),
        "fully_resolved": bool(summary.fully_resolved),
        "almost_resolved": bool(summary.almost_resolved),
    }


def as_non_negative_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if value is None:
        value = 0
    try:
        parsed = float(cast(Any, value))
    except (TypeError, ValueError):
        return 0
    if parsed < 0 or not parsed.is_integer():
        return 0
    return int(parsed)


def as_optional_rate(value: object) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(cast(Any, value))
    except (TypeError, ValueError):
        return None
    if parsed < 0 or parsed > 1:
        return None
    return parsed


def write_json(
    rows: list[OfficialGeneralizationGapRow],
    limit: int,
    *,
    runs_root: str | Path,
    official_eval_root: str | Path,
    baseline_root: str | Path,
    min_holdout_rate: float,
    min_holdout_cases: int,
    required_runtime_smoke_dimensions: tuple[str, ...],
    latest_per_task: bool,
    max_local_holdout_gap: float | None,
    include_next_command: bool,
    fail_on_gap: bool,
) -> None:
    selected = rows[:limit]
    payload = {
        "schema_version": 1,
        "row_count": len(selected),
        "total_row_count": len(rows),
        "limit": limit,
        "gap_kind_counts": count_by_gap_kind(rows),
        "blocker_counts": {"official_not_above_baseline": len(rows)},
        "fail_on_gap": fail_on_gap,
        "would_fail": bool(rows),
        "rows": [
            gap_row_json(
                index + 1,
                row,
                runs_root=runs_root,
                official_eval_root=official_eval_root,
                baseline_root=baseline_root,
                min_holdout_rate=min_holdout_rate,
                min_holdout_cases=min_holdout_cases,
                required_runtime_smoke_dimensions=required_runtime_smoke_dimensions,
                latest_per_task=latest_per_task,
                max_local_holdout_gap=max_local_holdout_gap,
                include_next_command=include_next_command,
                fail_on_gap=fail_on_gap,
            )
            for index, row in enumerate(selected)
        ],
    }
    print(json.dumps(payload, indent=2))


def count_by_gap_kind(rows: list[OfficialGeneralizationGapRow]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.gap_kind] = counts.get(row.gap_kind, 0) + 1
    return counts


def gap_row_json(
    rank: int,
    row: OfficialGeneralizationGapRow,
    *,
    runs_root: str | Path,
    official_eval_root: str | Path,
    baseline_root: str | Path,
    min_holdout_rate: float,
    min_holdout_cases: int,
    required_runtime_smoke_dimensions: tuple[str, ...],
    latest_per_task: bool,
    max_local_holdout_gap: float | None,
    include_next_command: bool,
    fail_on_gap: bool,
) -> dict[str, Any]:
    candidate_pass_rate = official_pass_rate(row.candidate_official_rank)
    raw_score_delta, raw_passed_delta = official_raw_deltas(row)
    mode = generalization_failure_mode(row)
    priority = diagnostic_priority(row)
    data = {
        "rank": rank,
        "task_id": row.task_id,
        "gap_kind": row.gap_kind,
        "generalization_failure_mode": mode,
        "diagnostic_priority": priority,
        "local_resolved_rate": row.local_resolved_rate,
        "holdout_resolved_rate": row.holdout_resolved_rate,
        "local_holdout_gap": row.local_holdout_gap,
        "holdout_cases": row.holdout_cases,
        "smoke_contract_axis_count": row.smoke_contract_axis_count,
        "adaptive_axis_count": row.adaptive_axis_count,
        "runtime_smoke_status": row.runtime_smoke_status,
        "runtime_smoke_input_dimensions": list(row.runtime_smoke_input_dimensions),
        "probe_domains": list(row.probe_domains),
        "probe_domain_count": row.probe_domain_count,
        "probe_domain_sprawl": row.probe_domain_sprawl,
        "probe_domain_warning": probe_domain_warning(row),
        "candidate_official": official_rank_json(
            row.candidate_official_rank,
            row.candidate_official_counted,
        ),
        "recorded_baseline": official_rank_json(
            row.recorded_baseline_rank,
            row.recorded_baseline_counted,
        ),
        "candidate_official_raw": row.candidate_official_raw,
        "recorded_baseline_raw": row.recorded_baseline_raw,
        "official_score_delta": row.official_score_delta,
        "official_passed_delta": row.official_passed_delta,
        "official_raw_score_delta": raw_score_delta,
        "official_raw_passed_delta": raw_passed_delta,
        "local_official_pass_rate_gap": row.local_resolved_rate - candidate_pass_rate,
        "holdout_official_pass_rate_gap": (
            None
            if row.holdout_resolved_rate is None
            else row.holdout_resolved_rate - candidate_pass_rate
        ),
        "official_eval_allowed": False,
        "repeat_official_eval_recommended": False,
        "evidence_boundary": "aggregate_official_not_above_baseline",
        "next_action": "repair_local_generalization_before_more_official_eval",
        "blocker": "official_not_above_baseline",
        "result_path": str(row.result_path),
    }
    if include_next_command:
        data["next_command"] = build_gap_recheck_command(
            row.task_id,
            runs_root=runs_root,
            official_eval_root=official_eval_root,
            baseline_root=baseline_root,
            min_holdout_rate=min_holdout_rate,
            min_holdout_cases=min_holdout_cases,
            required_runtime_smoke_dimensions=required_runtime_smoke_dimensions,
            latest_per_task=latest_per_task,
            max_local_holdout_gap=max_local_holdout_gap,
            include_next_command=include_next_command,
            fail_on_gap=fail_on_gap,
        )
    return data


def probe_domain_warning(row: OfficialGeneralizationGapRow) -> str | None:
    if row.probe_domain_sprawl:
        return "probe_domain_sprawl"
    return None


def official_raw_deltas(
    row: OfficialGeneralizationGapRow,
) -> tuple[int | None, int | None]:
    if row.candidate_official_raw is None or row.recorded_baseline_raw is None:
        return None, None
    return (
        as_non_negative_int(row.candidate_official_raw.get("score"))
        - as_non_negative_int(row.recorded_baseline_raw.get("score")),
        as_non_negative_int(row.candidate_official_raw.get("passed_tests"))
        - as_non_negative_int(row.recorded_baseline_raw.get("passed_tests")),
    )


def official_rank_json(
    rank: OfficialRank,
    summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = {
        "score": official_score(rank),
        "passed_tests": official_passed_tests(rank),
        "pass_rate": official_pass_rate(rank),
        "fully_resolved": bool(rank[0]),
        "almost_resolved": bool(rank[1]),
    }
    if summary is not None:
        data["total_tests"] = as_non_negative_int(summary.get("total_tests"))
    return data


def write_markdown(
    rows: list[OfficialGeneralizationGapRow],
    limit: int,
    *,
    runs_root: str | Path,
    official_eval_root: str | Path,
    baseline_root: str | Path,
    min_holdout_rate: float,
    min_holdout_cases: int,
    required_runtime_smoke_dimensions: tuple[str, ...],
    latest_per_task: bool,
    max_local_holdout_gap: float | None,
    include_next_command: bool,
    fail_on_gap: bool,
) -> None:
    command_header = " | next command" if include_next_command else ""
    command_rule = " | ---" if include_next_command else ""
    print(
        "| rank | task | gap | local | holdout | local/holdout gap | axes | runtime dims | official | baseline | delta | next action"
        f"{command_header} |"
    )
    print(
        "| ---: | --- | --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---"
        f"{command_rule} |"
    )
    for index, row in enumerate(rows[:limit], start=1):
        candidate = row.candidate_official_rank
        baseline = row.recorded_baseline_rank
        command_cell = ""
        if include_next_command:
            command_cell = (
                " "
                + build_gap_recheck_command(
                    row.task_id,
                    runs_root=runs_root,
                    official_eval_root=official_eval_root,
                    baseline_root=baseline_root,
                    min_holdout_rate=min_holdout_rate,
                    min_holdout_cases=min_holdout_cases,
                    required_runtime_smoke_dimensions=required_runtime_smoke_dimensions,
                    latest_per_task=latest_per_task,
                    max_local_holdout_gap=max_local_holdout_gap,
                    include_next_command=include_next_command,
                    fail_on_gap=fail_on_gap,
                )
                + " |"
            )
        print(
            "| "
            f"{index} | {row.task_id} | {row.gap_kind} | "
            f"{format_rate(row.local_resolved_rate)} | "
            f"{format_rate(row.holdout_resolved_rate)} ({row.holdout_cases}) | "
            f"{format_rate(row.local_holdout_gap)} | "
            f"{row.smoke_contract_axis_count}/{row.adaptive_axis_count} | "
            f"{','.join(row.runtime_smoke_input_dimensions) or '-'} | "
            f"{official_score(candidate)} ({official_passed_tests(candidate)}) | "
            f"{official_score(baseline)} ({official_passed_tests(baseline)}) | "
            f"{row.official_score_delta}/{row.official_passed_delta} | "
            f"repair_local_generalization_before_more_official_eval |{command_cell}"
        )


def build_gap_recheck_command(
    task_id: str,
    *,
    runs_root: str | Path,
    official_eval_root: str | Path,
    baseline_root: str | Path,
    min_holdout_rate: float,
    min_holdout_cases: int,
    required_runtime_smoke_dimensions: tuple[str, ...],
    latest_per_task: bool,
    max_local_holdout_gap: float | None,
    include_next_command: bool,
    fail_on_gap: bool,
) -> str:
    command = (
        "python scripts/audit_official_generalization_gaps.py "
        f"--runs {quote_shell_arg(Path(runs_root).as_posix())} "
        f"--official-eval-root {quote_shell_arg(Path(official_eval_root).as_posix())} "
        f"--baseline-root {quote_shell_arg(Path(baseline_root).as_posix())} "
        f"--task {quote_shell_arg(task_id)} "
        f"--min-holdout-rate {min_holdout_rate:g} "
        f"--min-holdout-cases {int(min_holdout_cases)} "
    )
    if required_runtime_smoke_dimensions:
        command += (
            "--require-runtime-smoke-dimensions "
            f"{quote_shell_arg(','.join(required_runtime_smoke_dimensions))} "
        )
    if latest_per_task:
        command += "--latest-per-task "
    if max_local_holdout_gap is not None:
        command += f"--max-local-holdout-gap {max_local_holdout_gap:g} "
    if include_next_command:
        command += "--include-next-command "
    if fail_on_gap:
        command += "--fail-on-gap "
    return command + "--format json --limit 20"


def quote_shell_arg(value: str) -> str:
    if all(char.isalnum() or char in "._-/\\:," for char in value):
        return value
    return "'" + value.replace("'", "''") + "'"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    rows = collect_generalization_gaps(
        runs_root=args.runs,
        official_eval_root=args.official_eval_root,
        baseline_root=args.baseline_root,
        min_holdout_cases=args.min_holdout_cases,
        min_holdout_rate=args.min_holdout_rate,
        required_runtime_smoke_dimensions=args.require_runtime_smoke_dimensions,
        latest_per_task=args.latest_per_task,
        task_ids=args.task,
        max_local_holdout_gap=args.max_local_holdout_gap,
        sort_by=args.sort_by,
    )
    if args.format == "json":
        write_json(
            rows,
            args.limit,
            runs_root=args.runs,
            official_eval_root=args.official_eval_root,
            baseline_root=args.baseline_root,
            min_holdout_rate=args.min_holdout_rate,
            min_holdout_cases=args.min_holdout_cases,
            required_runtime_smoke_dimensions=args.require_runtime_smoke_dimensions,
            latest_per_task=args.latest_per_task,
            max_local_holdout_gap=args.max_local_holdout_gap,
            include_next_command=args.include_next_command,
            fail_on_gap=args.fail_on_gap,
        )
    else:
        write_markdown(
            rows,
            args.limit,
            runs_root=args.runs,
            official_eval_root=args.official_eval_root,
            baseline_root=args.baseline_root,
            min_holdout_rate=args.min_holdout_rate,
            min_holdout_cases=args.min_holdout_cases,
            required_runtime_smoke_dimensions=args.require_runtime_smoke_dimensions,
            latest_per_task=args.latest_per_task,
            max_local_holdout_gap=args.max_local_holdout_gap,
            include_next_command=args.include_next_command,
            fail_on_gap=args.fail_on_gap,
        )
    return 1 if args.fail_on_gap and rows else 0


if __name__ == "__main__":
    raise SystemExit(main())
