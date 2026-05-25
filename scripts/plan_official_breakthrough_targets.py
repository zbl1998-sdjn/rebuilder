"""Plan aggregate-only ProgramBench official breakthrough targets."""

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

from scripts.summarize_holdout_trends import (  # noqa: E402
    HoldoutTrend,
    build_guarded_rerun_command,
    collect_holdout_trends,
    format_rate,
    non_negative_float,
    non_negative_int,
    positive_int,
    quote_shell_arg,
    rate_float,
)
from scripts.rank_programbench_candidates import (  # noqa: E402
    discover_baseline_official_ranks as discover_candidate_baseline_official_ranks,
    discover_baseline_task_ids as discover_candidate_baseline_task_ids,
    discover_official_eval_task_ids as discover_candidate_official_eval_task_ids,
    normalize_required_runtime_smoke_dimensions,
    official_gate_blockers,
    official_gate_reason,
    read_candidate_row,
)

DEFAULT_MAX_LOCAL_HOLDOUT_GAP = 0.15
DEFAULT_LOCAL_GAP_RERUN_CONFIG = "config/smoke_file_bridge.yaml"


@dataclass(frozen=True)
class OfficialBaseline:
    task_id: str
    official_score: int
    official_pass_rate: float | None
    passed_tests: int | None
    total_tests: int | None
    baseline_path: Path


@dataclass(frozen=True)
class BreakthroughTarget:
    task_id: str
    official_score: int
    official_pass_rate: float | None
    passed_tests: int | None
    total_tests: int | None
    target_class: str
    next_action: str
    reason: str
    latest_holdout_resolved_rate: float | None
    latest_holdout_cases: int | None
    best_holdout_resolved_rate: float | None
    best_holdout_cases: int | None
    latest_result_path: Path | None
    best_result_path: Path | None
    baseline_path: Path


TARGET_CLASS_PRIORITY = {
    "ready_baseline_gate": 0,
    "restore_historical_gate": 1,
    "weak_cleanroom_rerun": 2,
    "missing_reliable_holdout": 3,
}
RUNTIME_SMOKE_DIMENSIONS = ("args", "stdin", "input_files", "env_vars", "default")
OFFICIAL_GENERALIZATION_GAP_CLASS = "official_generalization_gap"
OFFICIAL_GENERALIZATION_GAP_ACTION = "repair_local_generalization_before_more_official_eval"
OFFICIAL_EVAL_FAILURE_CLASS = "official_eval_operational_failure"
OFFICIAL_EVAL_FAILURE_ACTION = "repair_official_eval_harness_before_more_official_eval"
OFFICIAL_EVAL_RESULTS_READ_FAILED_ACTION = "repair_candidate_runtime_timeout_before_more_official_eval"
OFFICIAL_EVAL_INVALID_AGGREGATE_ACTION = "repair_official_eval_artifacts_before_more_official_eval"
OFFICIAL_EVAL_OPERATIONAL_FAILURE_REASONS = {
    "official_eval_failed_without_eval_json",
    "official_eval_results_read_failed",
    "official_eval_invalid_aggregate",
}
LOCAL_GENERALIZATION_GAP_CLASS = "local_generalization_gap"
LOCAL_GENERALIZATION_GAP_ACTION = "repair_local_generalization_before_official_eval"
LOCAL_GENERALIZATION_BLOCKERS = {
    "holdout_not_improved",
    "holdout_delta_below_min",
    "holdout_missing_current_holdout",
    "holdout_too_few_current_holdout_cases",
    "holdout_no_prior_reliable",
    "missing_holdout",
    "too_few_holdout_cases",
    "low_holdout_rate",
    "local_holdout_gap_too_high",
    "runtime_smoke_not_passed",
    "insufficient_runtime_smoke_dimensions",
    "insufficient_smoke_contract_axes",
}


def runtime_smoke_dimensions(value: str) -> str:
    raw_dimensions = [part.strip() for part in value.split(",")]
    selected = [dimension for dimension in raw_dimensions if dimension]
    allowed = set(RUNTIME_SMOKE_DIMENSIONS)
    if any(dimension not in allowed for dimension in selected):
        raise argparse.ArgumentTypeError(
            "must contain only: " + ", ".join(RUNTIME_SMOKE_DIMENSIONS)
        )
    ordered = [dimension for dimension in RUNTIME_SMOKE_DIMENSIONS if dimension in selected]
    return ",".join(ordered)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan aggregate-only targets for ProgramBench official baseline breakthroughs"
    )
    parser.add_argument("--runs", default="runs", help="Root directory containing result.json files")
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
        help="Minimum holdout cases required for a reliable local trend",
    )
    parser.add_argument(
        "--min-holdout-rate",
        type=rate_float,
        default=0.8,
        help="Local holdout gate used to classify breakthrough targets",
    )
    parser.add_argument(
        "--include-next-command",
        action="store_true",
        help="Include guarded aggregate-only next-step commands where available",
    )
    parser.add_argument(
        "--official-eval-root",
        default="runs/programbench_official_eval",
        help="Official eval root used when rendering baseline gate audit commands",
    )
    parser.add_argument(
        "--baseline-upgrade-min-smoke-contract-axes",
        type=non_negative_int,
        default=0,
        help="Optional smoke-contract axis gate to include in baseline-upgrade ranking commands",
    )
    parser.add_argument(
        "--baseline-upgrade-require-holdout-improvement",
        action="store_true",
        help="Include the aggregate holdout-improvement gate in baseline-upgrade ranking commands",
    )
    parser.add_argument(
        "--baseline-upgrade-min-holdout-improvement-delta",
        type=non_negative_float,
        default=0.0,
        help="Optional positive improvement margin for baseline-upgrade ranking commands",
    )
    parser.add_argument(
        "--baseline-upgrade-require-runtime-smoke-dimensions",
        type=runtime_smoke_dimensions,
        default="",
        help=(
            "Comma-separated runtime-smoke dimensions to include in baseline-upgrade "
            "ranking commands. Valid values: " + ", ".join(RUNTIME_SMOKE_DIMENSIONS)
        ),
    )
    parser.add_argument(
        "--baseline-upgrade-max-local-holdout-gap",
        type=rate_float,
        default=DEFAULT_MAX_LOCAL_HOLDOUT_GAP,
        help=(
            "Maximum allowed aggregate gap between local resolved_rate and "
            "holdout_resolved_rate for baseline-upgrade gate commands"
        ),
    )
    parser.add_argument(
        "--rerun-root",
        default="runs/weak_task_cleanroom_rerun",
        help="Root used when rendering guarded weak-task rerun commands",
    )
    parser.add_argument(
        "--rerun-min-smoke-contract-axes",
        type=non_negative_int,
        default=0,
        help="Optional smoke-contract axis gate to include in guarded weak-task rerun commands",
    )
    parser.add_argument(
        "--rerun-require-runtime-smoke-dimensions",
        type=runtime_smoke_dimensions,
        default="",
        help=(
            "Comma-separated runtime-smoke dimensions to include in guarded "
            "weak-task rerun commands. Valid values: "
            + ", ".join(RUNTIME_SMOKE_DIMENSIONS)
        ),
    )
    parser.add_argument(
        "--rerun-min-holdout-improvement-delta",
        type=non_negative_float,
        default=0.0,
        help="Optional holdout improvement delta gate to include in guarded weak-task rerun commands",
    )
    parser.add_argument(
        "--rerun-config",
        default="",
        help=(
            "Optional ReBuilder config path to include in guarded weak-task rerun commands. "
            "Use a file_bridge or loopback local_openai config for no-external LLM runs."
        ),
    )
    parser.add_argument(
        "--rerun-ack-local-llm-docker",
        action="store_true",
        help=(
            "Include --ack-local-llm-docker in guarded weak-task rerun commands so a later "
            "--execute conversion stays on file_bridge or loopback local_openai configs."
        ),
    )
    parser.add_argument(
        "--include-restore-ablation-command",
        action="store_true",
        help="Render guarded restore-axis strategy ablation dry-run commands for restore rows",
    )
    parser.add_argument(
        "--restore-ablation-command-kind",
        choices=("strategy", "batch"),
        default="strategy",
        help=(
            "Command shape for restore rows. 'strategy' renders the single-task "
            "strategy-ablation command; 'batch' renders the restore-axis batch "
            "wrapper so axis-action metadata can be shown before execution."
        ),
    )
    parser.add_argument(
        "--restore-ablation-show-axis-action",
        action="store_true",
        help=(
            "Include --show-axis-action when rendering restore-axis batch commands. "
            "Only applies with --restore-ablation-command-kind batch."
        ),
    )
    parser.add_argument(
        "--restore-ablation-apply-axis-action",
        action="store_true",
        help=(
            "Include --apply-axis-action when rendering restore-axis batch commands, "
            "so added-axis domains become child adaptive probe exclusions."
        ),
    )
    parser.add_argument(
        "--restore-ablation-root",
        default="runs/restore_axis_ablation_next",
        help="Root used when rendering guarded restore-axis strategy ablation dry-run commands",
    )
    parser.add_argument(
        "--restore-ablation-min-smoke-contract-axes",
        type=non_negative_int,
        default=1,
        help="Smoke-contract axis gate to include in guarded restore-axis ablation commands",
    )
    parser.add_argument(
        "--restore-ablation-require-runtime-smoke-dimensions",
        type=runtime_smoke_dimensions,
        default="",
        help=(
            "Comma-separated runtime-smoke dimensions to include in guarded "
            "restore-axis ablation commands. Valid values: "
            + ", ".join(RUNTIME_SMOKE_DIMENSIONS)
        ),
    )
    parser.add_argument(
        "--restore-ablation-max-local-holdout-gap",
        type=rate_float,
        default=DEFAULT_MAX_LOCAL_HOLDOUT_GAP,
        help=(
            "Maximum allowed aggregate gap between local resolved_rate and "
            "holdout_resolved_rate for restore-axis ablation package gates"
        ),
    )
    parser.add_argument(
        "--restore-ablation-config",
        default="",
        help=(
            "Optional ReBuilder config path to include in restore-axis ablation commands. "
            "Use a file_bridge or loopback local_openai config for no-external LLM runs."
        ),
    )
    parser.add_argument(
        "--restore-ablation-ack-local-llm-docker",
        action="store_true",
        help=(
            "Include --ack-local-llm-docker in restore-axis ablation commands so a later "
            "--execute conversion stays on file_bridge or loopback local_openai configs."
        ),
    )
    parser.add_argument(
        "--include-missing-holdout-command",
        action="store_true",
        help="Render guarded missing-holdout cleanroom rerun dry-run commands for missing holdout rows",
    )
    parser.add_argument(
        "--missing-holdout-rerun-root",
        default="runs/missing_holdout_cleanroom_rerun",
        help="Root used when rendering missing-holdout cleanroom rerun dry-run commands",
    )
    parser.add_argument(
        "--missing-holdout-min-smoke-contract-axes",
        type=non_negative_int,
        default=1,
        help="Smoke-contract axis gate to include in missing-holdout cleanroom rerun commands",
    )
    parser.add_argument(
        "--missing-holdout-require-runtime-smoke-dimensions",
        type=runtime_smoke_dimensions,
        default="",
        help=(
            "Comma-separated runtime-smoke dimensions to include in missing-holdout "
            "cleanroom rerun commands. Valid values: "
            + ", ".join(RUNTIME_SMOKE_DIMENSIONS)
        ),
    )
    parser.add_argument(
        "--missing-holdout-config",
        default="",
        help=(
            "Optional ReBuilder config path to include in missing-holdout commands. "
            "Use a file_bridge or loopback local_openai config for no-external LLM runs."
        ),
    )
    parser.add_argument(
        "--missing-holdout-ack-local-llm-docker",
        action="store_true",
        help=(
            "Include --ack-local-llm-docker in missing-holdout commands so a later "
            "--execute conversion stays on file_bridge or loopback local_openai configs."
        ),
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format. JSON emits aggregate-only rows for automation.",
    )
    return parser.parse_args(argv)


def collect_official_breakthrough_targets(
    runs_root: Path | str,
    baseline_root: Path | str,
    *,
    min_holdout_cases: int = 10,
    min_holdout_rate: float = 0.8,
) -> list[BreakthroughTarget]:
    validate_target_thresholds(
        min_holdout_cases=min_holdout_cases,
        min_holdout_rate=min_holdout_rate,
    )
    baselines = discover_official_baselines(Path(baseline_root))
    trends = {
        trend.task_id: trend
        for trend in collect_holdout_trends(
            Path(runs_root),
            min_holdout_cases=min_holdout_cases,
        )
    }
    rows = [
        build_target_row(
            baseline,
            trends.get(baseline.task_id),
            min_holdout_rate=min_holdout_rate,
        )
        for baseline in baselines.values()
    ]
    return sorted(rows, key=target_sort_key)


def validate_target_thresholds(*, min_holdout_cases: int, min_holdout_rate: float) -> None:
    try:
        parsed_cases = float(min_holdout_cases)
    except (TypeError, ValueError) as exc:
        raise ValueError("min_holdout_cases must be a non-negative integer") from exc
    if not math.isfinite(parsed_cases) or parsed_cases < 0 or not parsed_cases.is_integer():
        raise ValueError("min_holdout_cases must be a non-negative integer")
    try:
        parsed_rate = float(min_holdout_rate)
    except (TypeError, ValueError) as exc:
        raise ValueError("min_holdout_rate must be a finite rate between 0 and 1") from exc
    if not math.isfinite(parsed_rate) or parsed_rate < 0 or parsed_rate > 1:
        raise ValueError("min_holdout_rate must be a finite rate between 0 and 1")


def discover_official_baselines(root: Path) -> dict[str, OfficialBaseline]:
    if not root.exists():
        return {}
    rows: dict[str, OfficialBaseline] = {}
    for path in root.glob("*.baseline.json"):
        row = read_official_baseline(path)
        if row is None:
            continue
        current = rows.get(row.task_id)
        if current is None or (row.official_score, str(row.baseline_path)) > (
            current.official_score,
            str(current.baseline_path),
        ):
            rows[row.task_id] = row
    return rows


def read_official_baseline(path: Path) -> OfficialBaseline | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    task_id = payload.get("instance_id") or path.name.removesuffix(".baseline.json")
    if not task_id:
        return None
    official = payload.get("official") or {}
    if not isinstance(official, dict):
        return None
    score = as_optional_score(official.get("score"))
    pass_rate = as_optional_rate(official.get("pass_rate"))
    if score is None and pass_rate is not None:
        score = int(round(pass_rate * 100))
    if score is None:
        return None
    return OfficialBaseline(
        task_id=str(task_id),
        official_score=score,
        official_pass_rate=pass_rate,
        passed_tests=as_optional_int(official.get("passed_tests")),
        total_tests=as_optional_int(official.get("total_tests")),
        baseline_path=path,
    )


def build_target_row(
    baseline: OfficialBaseline,
    trend: HoldoutTrend | None,
    *,
    min_holdout_rate: float,
) -> BreakthroughTarget:
    if trend is None:
        return BreakthroughTarget(
            task_id=baseline.task_id,
            official_score=baseline.official_score,
            official_pass_rate=baseline.official_pass_rate,
            passed_tests=baseline.passed_tests,
            total_tests=baseline.total_tests,
            target_class="missing_reliable_holdout",
            next_action="build_reliable_holdout_signal",
            reason="no_reliable_local_holdout",
            latest_holdout_resolved_rate=None,
            latest_holdout_cases=None,
            best_holdout_resolved_rate=None,
            best_holdout_cases=None,
            latest_result_path=None,
            best_result_path=None,
            baseline_path=baseline.baseline_path,
        )
    if trend.latest_holdout_resolved_rate >= min_holdout_rate:
        target_class = "ready_baseline_gate"
        next_action = "audit_baseline_upgrade_candidate"
        reason = "latest_holdout_at_or_above_gate"
    elif trend.best_holdout_resolved_rate >= min_holdout_rate:
        target_class = "restore_historical_gate"
        next_action = "restore_or_ablate_historical_best"
        reason = "historical_best_at_gate_but_latest_regressed"
    else:
        target_class = "weak_cleanroom_rerun"
        next_action = "run_guarded_weak_task_rerun"
        reason = "historical_best_below_gate"
    return BreakthroughTarget(
        task_id=baseline.task_id,
        official_score=baseline.official_score,
        official_pass_rate=baseline.official_pass_rate,
        passed_tests=baseline.passed_tests,
        total_tests=baseline.total_tests,
        target_class=target_class,
        next_action=next_action,
        reason=reason,
        latest_holdout_resolved_rate=trend.latest_holdout_resolved_rate,
        latest_holdout_cases=trend.latest_holdout_cases,
        best_holdout_resolved_rate=trend.best_holdout_resolved_rate,
        best_holdout_cases=trend.best_holdout_cases,
        latest_result_path=trend.latest_result_path,
        best_result_path=trend.best_result_path,
        baseline_path=baseline.baseline_path,
    )


def target_sort_key(row: BreakthroughTarget) -> tuple[int, int, float, float, str]:
    latest = row.latest_holdout_resolved_rate if row.latest_holdout_resolved_rate is not None else -1.0
    best = row.best_holdout_resolved_rate if row.best_holdout_resolved_rate is not None else -1.0
    return (
        TARGET_CLASS_PRIORITY.get(row.target_class, 99),
        row.official_score,
        -best,
        -latest,
        row.task_id,
    )


def as_optional_score(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or parsed < 0 or parsed > 100:
        return None
    return int(round(parsed))


def as_optional_rate(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and 0 <= parsed <= 1 else None


def as_optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or parsed < 0 or not parsed.is_integer():
        return None
    return int(parsed)


def format_optional_rate(value: float | None, cases: int | None) -> str:
    if value is None:
        return "-"
    if cases is None:
        return format_rate(value)
    return f"{format_rate(value)} ({cases})"


def format_official(row: BreakthroughTarget) -> str:
    if row.passed_tests is not None and row.total_tests is not None:
        return f"{row.official_score} ({row.passed_tests}/{row.total_tests})"
    return str(row.official_score)


def write_markdown(
    rows: list[BreakthroughTarget],
    limit: int,
    *,
    include_next_command: bool = False,
    runs_root: str = "runs",
    baseline_root: str = "baselines/programbench",
    official_eval_root: str = "runs/programbench_official_eval",
    min_holdout_rate: float = 0.8,
    min_holdout_cases: int = 10,
    baseline_upgrade_min_smoke_contract_axes: int = 0,
    baseline_upgrade_require_holdout_improvement: bool = False,
    baseline_upgrade_min_holdout_improvement_delta: float = 0.0,
    baseline_upgrade_require_runtime_smoke_dimensions: str = "",
    baseline_upgrade_max_local_holdout_gap: float = DEFAULT_MAX_LOCAL_HOLDOUT_GAP,
    rerun_root: str = "runs/weak_task_cleanroom_rerun",
    rerun_min_smoke_contract_axes: int = 0,
    rerun_require_runtime_smoke_dimensions: str = "",
    rerun_min_holdout_improvement_delta: float = 0.0,
    rerun_config: str = "",
    rerun_ack_local_llm_docker: bool = False,
    include_restore_ablation_command: bool = False,
    restore_ablation_command_kind: str = "strategy",
    restore_ablation_show_axis_action: bool = False,
    restore_ablation_apply_axis_action: bool = False,
    restore_ablation_root: str = "runs/restore_axis_ablation_next",
    restore_ablation_min_smoke_contract_axes: int = 1,
    restore_ablation_require_runtime_smoke_dimensions: str = "",
    restore_ablation_max_local_holdout_gap: float = DEFAULT_MAX_LOCAL_HOLDOUT_GAP,
    restore_ablation_config: str = "",
    restore_ablation_ack_local_llm_docker: bool = False,
    include_missing_holdout_command: bool = False,
    missing_holdout_rerun_root: str = "runs/missing_holdout_cleanroom_rerun",
    missing_holdout_min_smoke_contract_axes: int = 1,
    missing_holdout_require_runtime_smoke_dimensions: str = "",
    missing_holdout_config: str = "",
    missing_holdout_ack_local_llm_docker: bool = False,
) -> None:
    selected = rows[: max(0, limit)]
    command_header = " | next command" if include_next_command else ""
    command_rule = " | ---" if include_next_command else ""
    print(
        "| rank | task | official score | latest holdout | best holdout | target class | "
        f"next action | reason | baseline gate | latest result | best result{command_header} |"
    )
    print(
        "| ---: | --- | ---: | ---: | ---: | --- | --- | --- | --- | --- | ---"
        f"{command_rule} |"
    )
    for index, row in enumerate(selected, start=1):
        baseline_gate = baseline_upgrade_gate_json(
            row,
            runs_root=runs_root,
            baseline_root=baseline_root,
            official_eval_root=official_eval_root,
            min_holdout_rate=min_holdout_rate,
            min_holdout_cases=min_holdout_cases,
            baseline_upgrade_min_smoke_contract_axes=baseline_upgrade_min_smoke_contract_axes,
            baseline_upgrade_require_holdout_improvement=baseline_upgrade_require_holdout_improvement,
            baseline_upgrade_min_holdout_improvement_delta=(
                baseline_upgrade_min_holdout_improvement_delta
            ),
            baseline_upgrade_require_runtime_smoke_dimensions=(
                baseline_upgrade_require_runtime_smoke_dimensions
            ),
            baseline_upgrade_max_local_holdout_gap=baseline_upgrade_max_local_holdout_gap,
        )
        baseline_gate_cell = baseline_upgrade_gate_label_from_gate(baseline_gate)
        command_cell = ""
        if include_next_command:
            command = build_next_command(
                row,
                runs_root=runs_root,
                baseline_root=baseline_root,
                official_eval_root=official_eval_root,
                min_holdout_rate=min_holdout_rate,
                min_holdout_cases=min_holdout_cases,
                baseline_upgrade_min_smoke_contract_axes=baseline_upgrade_min_smoke_contract_axes,
                baseline_upgrade_require_holdout_improvement=baseline_upgrade_require_holdout_improvement,
                baseline_upgrade_min_holdout_improvement_delta=baseline_upgrade_min_holdout_improvement_delta,
                baseline_upgrade_require_runtime_smoke_dimensions=baseline_upgrade_require_runtime_smoke_dimensions,
                baseline_upgrade_max_local_holdout_gap=baseline_upgrade_max_local_holdout_gap,
                rerun_root=rerun_root,
                rerun_min_smoke_contract_axes=rerun_min_smoke_contract_axes,
                rerun_require_runtime_smoke_dimensions=rerun_require_runtime_smoke_dimensions,
                rerun_min_holdout_improvement_delta=rerun_min_holdout_improvement_delta,
                rerun_config=rerun_config,
                rerun_ack_local_llm_docker=rerun_ack_local_llm_docker,
                include_restore_ablation_command=include_restore_ablation_command,
                restore_ablation_command_kind=restore_ablation_command_kind,
                restore_ablation_show_axis_action=restore_ablation_show_axis_action,
                restore_ablation_apply_axis_action=restore_ablation_apply_axis_action,
                restore_ablation_root=restore_ablation_root,
                restore_ablation_min_smoke_contract_axes=restore_ablation_min_smoke_contract_axes,
                restore_ablation_require_runtime_smoke_dimensions=(
                    restore_ablation_require_runtime_smoke_dimensions
                ),
                restore_ablation_max_local_holdout_gap=restore_ablation_max_local_holdout_gap,
                restore_ablation_config=restore_ablation_config,
                restore_ablation_ack_local_llm_docker=restore_ablation_ack_local_llm_docker,
                include_missing_holdout_command=include_missing_holdout_command,
                missing_holdout_rerun_root=missing_holdout_rerun_root,
                missing_holdout_min_smoke_contract_axes=missing_holdout_min_smoke_contract_axes,
                missing_holdout_require_runtime_smoke_dimensions=(
                    missing_holdout_require_runtime_smoke_dimensions
                ),
                missing_holdout_config=missing_holdout_config,
                missing_holdout_ack_local_llm_docker=missing_holdout_ack_local_llm_docker,
                baseline_upgrade_gate=baseline_gate,
            )
            command_cell = f" | `{command}`" if command else " | -"
        target_class = planned_target_class(row, baseline_gate)
        next_action = planned_next_action(row, baseline_gate)
        reason = planned_reason(row, baseline_gate)
        print(
            f"| {index} | {row.task_id} | {format_official(row)} | "
            f"{format_optional_rate(row.latest_holdout_resolved_rate, row.latest_holdout_cases)} | "
            f"{format_optional_rate(row.best_holdout_resolved_rate, row.best_holdout_cases)} | "
            f"{target_class} | {next_action} | {reason} | "
            f"{baseline_gate_cell} | {format_path(row.latest_result_path)} | "
            f"{format_path(row.best_result_path)}{command_cell} |"
        )


def optional_holdout_json(resolved_rate: float | None, cases: int | None) -> dict[str, object] | None:
    if resolved_rate is None:
        return None
    return {
        "resolved_rate": resolved_rate,
        "cases": cases,
    }


def breakthrough_target_json_row(
    row: BreakthroughTarget,
    rank: int,
    *,
    include_next_command: bool = False,
    runs_root: str = "runs",
    baseline_root: str = "baselines/programbench",
    official_eval_root: str = "runs/programbench_official_eval",
    min_holdout_rate: float = 0.8,
    min_holdout_cases: int = 10,
    baseline_upgrade_min_smoke_contract_axes: int = 0,
    baseline_upgrade_require_holdout_improvement: bool = False,
    baseline_upgrade_min_holdout_improvement_delta: float = 0.0,
    baseline_upgrade_require_runtime_smoke_dimensions: str = "",
    baseline_upgrade_max_local_holdout_gap: float = DEFAULT_MAX_LOCAL_HOLDOUT_GAP,
    rerun_root: str = "runs/weak_task_cleanroom_rerun",
    rerun_min_smoke_contract_axes: int = 0,
    rerun_require_runtime_smoke_dimensions: str = "",
    rerun_min_holdout_improvement_delta: float = 0.0,
    rerun_config: str = "",
    rerun_ack_local_llm_docker: bool = False,
    include_restore_ablation_command: bool = False,
    restore_ablation_command_kind: str = "strategy",
    restore_ablation_show_axis_action: bool = False,
    restore_ablation_apply_axis_action: bool = False,
    restore_ablation_root: str = "runs/restore_axis_ablation_next",
    restore_ablation_min_smoke_contract_axes: int = 1,
    restore_ablation_require_runtime_smoke_dimensions: str = "",
    restore_ablation_max_local_holdout_gap: float = DEFAULT_MAX_LOCAL_HOLDOUT_GAP,
    restore_ablation_config: str = "",
    restore_ablation_ack_local_llm_docker: bool = False,
    include_missing_holdout_command: bool = False,
    missing_holdout_rerun_root: str = "runs/missing_holdout_cleanroom_rerun",
    missing_holdout_min_smoke_contract_axes: int = 1,
    missing_holdout_require_runtime_smoke_dimensions: str = "",
    missing_holdout_config: str = "",
    missing_holdout_ack_local_llm_docker: bool = False,
) -> dict[str, object]:
    baseline_upgrade_gate = baseline_upgrade_gate_json(
        row,
        runs_root=runs_root,
        baseline_root=baseline_root,
        official_eval_root=official_eval_root,
        min_holdout_rate=min_holdout_rate,
        min_holdout_cases=min_holdout_cases,
        baseline_upgrade_min_smoke_contract_axes=baseline_upgrade_min_smoke_contract_axes,
        baseline_upgrade_require_holdout_improvement=baseline_upgrade_require_holdout_improvement,
        baseline_upgrade_min_holdout_improvement_delta=(
            baseline_upgrade_min_holdout_improvement_delta
        ),
        baseline_upgrade_require_runtime_smoke_dimensions=(
            baseline_upgrade_require_runtime_smoke_dimensions
        ),
        baseline_upgrade_max_local_holdout_gap=baseline_upgrade_max_local_holdout_gap,
    )
    next_command = None
    if include_next_command:
        next_command = build_next_command(
            row,
            runs_root=runs_root,
            baseline_root=baseline_root,
            official_eval_root=official_eval_root,
            min_holdout_rate=min_holdout_rate,
            min_holdout_cases=min_holdout_cases,
            baseline_upgrade_min_smoke_contract_axes=baseline_upgrade_min_smoke_contract_axes,
            baseline_upgrade_require_holdout_improvement=baseline_upgrade_require_holdout_improvement,
            baseline_upgrade_min_holdout_improvement_delta=baseline_upgrade_min_holdout_improvement_delta,
            baseline_upgrade_require_runtime_smoke_dimensions=baseline_upgrade_require_runtime_smoke_dimensions,
            baseline_upgrade_max_local_holdout_gap=baseline_upgrade_max_local_holdout_gap,
            rerun_root=rerun_root,
            rerun_min_smoke_contract_axes=rerun_min_smoke_contract_axes,
            rerun_require_runtime_smoke_dimensions=rerun_require_runtime_smoke_dimensions,
            rerun_min_holdout_improvement_delta=rerun_min_holdout_improvement_delta,
            rerun_config=rerun_config,
            rerun_ack_local_llm_docker=rerun_ack_local_llm_docker,
            include_restore_ablation_command=include_restore_ablation_command,
            restore_ablation_command_kind=restore_ablation_command_kind,
            restore_ablation_show_axis_action=restore_ablation_show_axis_action,
            restore_ablation_apply_axis_action=restore_ablation_apply_axis_action,
            restore_ablation_root=restore_ablation_root,
            restore_ablation_min_smoke_contract_axes=restore_ablation_min_smoke_contract_axes,
            restore_ablation_require_runtime_smoke_dimensions=(
                restore_ablation_require_runtime_smoke_dimensions
            ),
            restore_ablation_max_local_holdout_gap=restore_ablation_max_local_holdout_gap,
            restore_ablation_config=restore_ablation_config,
            restore_ablation_ack_local_llm_docker=restore_ablation_ack_local_llm_docker,
            include_missing_holdout_command=include_missing_holdout_command,
            missing_holdout_rerun_root=missing_holdout_rerun_root,
            missing_holdout_min_smoke_contract_axes=missing_holdout_min_smoke_contract_axes,
            missing_holdout_require_runtime_smoke_dimensions=(
                missing_holdout_require_runtime_smoke_dimensions
            ),
            missing_holdout_config=missing_holdout_config,
            missing_holdout_ack_local_llm_docker=missing_holdout_ack_local_llm_docker,
            baseline_upgrade_gate=baseline_upgrade_gate,
        )
    return {
        "rank": rank,
        "task_id": row.task_id,
        "official": {
            "score": row.official_score,
            "pass_rate": row.official_pass_rate,
            "passed_tests": row.passed_tests,
            "total_tests": row.total_tests,
        },
        "target_class": planned_target_class(row, baseline_upgrade_gate),
        "next_action": planned_next_action(row, baseline_upgrade_gate),
        "reason": planned_reason(row, baseline_upgrade_gate),
        "latest_holdout": optional_holdout_json(row.latest_holdout_resolved_rate, row.latest_holdout_cases),
        "best_holdout": optional_holdout_json(row.best_holdout_resolved_rate, row.best_holdout_cases),
        "latest_result_path": format_json_path(row.latest_result_path),
        "best_result_path": format_json_path(row.best_result_path),
        "baseline_path": format_json_path(row.baseline_path),
        "baseline_upgrade_gate": baseline_upgrade_gate,
        "next_command": next_command or None,
    }


def baseline_upgrade_gate_label(
    row: BreakthroughTarget,
    *,
    runs_root: str,
    baseline_root: str,
    official_eval_root: str,
    min_holdout_rate: float,
    min_holdout_cases: int,
    baseline_upgrade_min_smoke_contract_axes: int = 0,
    baseline_upgrade_require_holdout_improvement: bool = False,
    baseline_upgrade_min_holdout_improvement_delta: float = 0.0,
    baseline_upgrade_require_runtime_smoke_dimensions: str = "",
    baseline_upgrade_max_local_holdout_gap: float = DEFAULT_MAX_LOCAL_HOLDOUT_GAP,
) -> str:
    gate = baseline_upgrade_gate_json(
        row,
        runs_root=runs_root,
        baseline_root=baseline_root,
        official_eval_root=official_eval_root,
        min_holdout_rate=min_holdout_rate,
        min_holdout_cases=min_holdout_cases,
        baseline_upgrade_min_smoke_contract_axes=baseline_upgrade_min_smoke_contract_axes,
        baseline_upgrade_require_holdout_improvement=baseline_upgrade_require_holdout_improvement,
        baseline_upgrade_min_holdout_improvement_delta=baseline_upgrade_min_holdout_improvement_delta,
        baseline_upgrade_require_runtime_smoke_dimensions=(
            baseline_upgrade_require_runtime_smoke_dimensions
        ),
        baseline_upgrade_max_local_holdout_gap=baseline_upgrade_max_local_holdout_gap,
    )
    return baseline_upgrade_gate_label_from_gate(gate)


def baseline_upgrade_gate_label_from_gate(gate: dict[str, object] | None) -> str:
    if gate is None:
        return "-"
    blockers = gate.get("blockers")
    if isinstance(blockers, list) and blockers:
        return ",".join(str(blocker) for blocker in blockers)
    return str(gate.get("reason") or "-")


def gate_blockers(gate: dict[str, object] | None) -> list[str]:
    if gate is None:
        return []
    blockers = gate.get("blockers")
    if not isinstance(blockers, list):
        return []
    return [str(blocker) for blocker in blockers]


def is_official_generalization_gap(
    row: BreakthroughTarget,
    gate: dict[str, object] | None,
) -> bool:
    return (
        row.target_class == "ready_baseline_gate"
        and "official_not_above_baseline" in gate_blockers(gate)
    )


def is_official_eval_operational_failure(
    row: BreakthroughTarget,
    gate: dict[str, object] | None,
) -> bool:
    return (
        row.target_class == "ready_baseline_gate"
        and official_eval_operational_failure_reason(gate) is not None
    )


def official_eval_operational_failure_reason(gate: dict[str, object] | None) -> str | None:
    for blocker in gate_blockers(gate):
        if blocker in OFFICIAL_EVAL_OPERATIONAL_FAILURE_REASONS:
            return blocker
    return None


def local_generalization_blocker(gate: dict[str, object] | None) -> str | None:
    for blocker in gate_blockers(gate):
        if blocker in LOCAL_GENERALIZATION_BLOCKERS:
            return blocker
    return None


def is_local_generalization_gap(
    row: BreakthroughTarget,
    gate: dict[str, object] | None,
) -> bool:
    return (
        row.target_class == "ready_baseline_gate"
        and local_generalization_blocker(gate) is not None
    )


def planned_target_class(
    row: BreakthroughTarget,
    gate: dict[str, object] | None,
) -> str:
    if is_official_eval_operational_failure(row, gate):
        return OFFICIAL_EVAL_FAILURE_CLASS
    if is_official_generalization_gap(row, gate):
        return OFFICIAL_GENERALIZATION_GAP_CLASS
    if is_local_generalization_gap(row, gate):
        return LOCAL_GENERALIZATION_GAP_CLASS
    return row.target_class


def planned_next_action(
    row: BreakthroughTarget,
    gate: dict[str, object] | None,
) -> str:
    if is_official_eval_operational_failure(row, gate):
        reason = official_eval_operational_failure_reason(gate)
        if reason == "official_eval_results_read_failed":
            return OFFICIAL_EVAL_RESULTS_READ_FAILED_ACTION
        if reason == "official_eval_invalid_aggregate":
            return OFFICIAL_EVAL_INVALID_AGGREGATE_ACTION
        return OFFICIAL_EVAL_FAILURE_ACTION
    if is_official_generalization_gap(row, gate):
        return OFFICIAL_GENERALIZATION_GAP_ACTION
    if is_local_generalization_gap(row, gate):
        return LOCAL_GENERALIZATION_GAP_ACTION
    return row.next_action


def planned_reason(
    row: BreakthroughTarget,
    gate: dict[str, object] | None,
) -> str:
    if is_official_eval_operational_failure(row, gate):
        return official_eval_operational_failure_reason(gate) or "official_eval_invalid_aggregate"
    if is_official_generalization_gap(row, gate):
        return "official_not_above_baseline"
    if is_local_generalization_gap(row, gate):
        blocker = local_generalization_blocker(gate)
        if blocker is not None:
            return blocker
    return row.reason


def baseline_upgrade_gate_json(
    row: BreakthroughTarget,
    *,
    runs_root: str,
    baseline_root: str,
    official_eval_root: str,
    min_holdout_rate: float,
    min_holdout_cases: int,
    baseline_upgrade_min_smoke_contract_axes: int = 0,
    baseline_upgrade_require_holdout_improvement: bool = False,
    baseline_upgrade_min_holdout_improvement_delta: float = 0.0,
    baseline_upgrade_require_runtime_smoke_dimensions: str = "",
    baseline_upgrade_max_local_holdout_gap: float = DEFAULT_MAX_LOCAL_HOLDOUT_GAP,
) -> dict[str, object] | None:
    if row.target_class != "ready_baseline_gate":
        return None
    required_runtime_smoke_dimensions = normalize_required_runtime_smoke_dimensions(
        baseline_upgrade_require_runtime_smoke_dimensions
    )
    gate: dict[str, object] = {
        "checked": False,
        "eligible": False,
        "reason": "missing_latest_result",
        "blockers": ["missing_latest_result"],
        "min_holdout_rate": min_holdout_rate,
        "min_holdout_cases": min_holdout_cases,
        "min_smoke_contract_axes": int(baseline_upgrade_min_smoke_contract_axes),
        "require_holdout_improvement": bool(baseline_upgrade_require_holdout_improvement),
        "min_holdout_improvement_delta": baseline_upgrade_min_holdout_improvement_delta,
        "required_runtime_smoke_dimensions": list(required_runtime_smoke_dimensions),
        "max_local_holdout_gap": baseline_upgrade_max_local_holdout_gap,
        "candidate": None,
    }
    if row.latest_result_path is None:
        return gate

    official_task_ids = discover_candidate_official_eval_task_ids(Path(official_eval_root))
    baseline_root_path = Path(baseline_root)
    official_task_ids.update(discover_candidate_baseline_task_ids(baseline_root_path))
    baseline_ranks = discover_candidate_baseline_official_ranks(baseline_root_path)
    candidate = read_candidate_row(
        row.latest_result_path,
        official_task_ids,
        baseline_ranks,
        official_eval_root=official_eval_root,
    )
    if candidate is None:
        gate.update({"reason": "candidate_unreadable", "blockers": ["candidate_unreadable"]})
        return gate

    blockers = official_gate_blockers(
        candidate,
        min_holdout_rate=min_holdout_rate,
        min_holdout_cases=min_holdout_cases,
        min_smoke_contract_axes=baseline_upgrade_min_smoke_contract_axes,
        required_runtime_smoke_dimensions=required_runtime_smoke_dimensions,
        require_holdout_improvement=baseline_upgrade_require_holdout_improvement,
        holdout_history_root=runs_root,
        min_holdout_improvement_delta=baseline_upgrade_min_holdout_improvement_delta,
        max_local_holdout_gap=baseline_upgrade_max_local_holdout_gap,
        allow_existing_official=True,
    )
    reason = official_gate_reason(
        candidate,
        min_holdout_rate=min_holdout_rate,
        min_holdout_cases=min_holdout_cases,
        min_smoke_contract_axes=baseline_upgrade_min_smoke_contract_axes,
        required_runtime_smoke_dimensions=required_runtime_smoke_dimensions,
        require_holdout_improvement=baseline_upgrade_require_holdout_improvement,
        holdout_history_root=runs_root,
        min_holdout_improvement_delta=baseline_upgrade_min_holdout_improvement_delta,
        max_local_holdout_gap=baseline_upgrade_max_local_holdout_gap,
        allow_existing_official=True,
    )
    blocker_list = list(blockers) if isinstance(blockers, list) else [str(blockers)]
    gate.update(
        {
            "checked": True,
            "eligible": reason in {"eligible", "eligible_baseline_upgrade"},
            "reason": reason,
            "blockers": blocker_list,
            "candidate": {
                "holdout_resolved_rate": candidate.holdout_resolved_rate,
                "holdout_cases": candidate.holdout_cases,
                "smoke_contract_axis_count": candidate.smoke_contract_axis_count,
                "runtime_smoke_status": candidate.runtime_smoke_status,
                "runtime_smoke_input_dimensions": list(candidate.runtime_smoke_input_dimensions),
                "has_official_eval": candidate.has_official_eval,
                "official_eval_failure_reason": candidate.official_eval_failure_reason,
                "official_eval_failure_report_path": (
                    None
                    if candidate.official_eval_failure_report_path is None
                    else str(candidate.official_eval_failure_report_path)
                ),
                "result_path": str(candidate.result_path),
            },
        }
    )
    return gate


def breakthrough_targets_json_payload(
    rows: list[BreakthroughTarget],
    limit: int,
    *,
    include_next_command: bool = False,
    runs_root: str = "runs",
    baseline_root: str = "baselines/programbench",
    official_eval_root: str = "runs/programbench_official_eval",
    min_holdout_rate: float = 0.8,
    min_holdout_cases: int = 10,
    baseline_upgrade_min_smoke_contract_axes: int = 0,
    baseline_upgrade_require_holdout_improvement: bool = False,
    baseline_upgrade_min_holdout_improvement_delta: float = 0.0,
    baseline_upgrade_require_runtime_smoke_dimensions: str = "",
    baseline_upgrade_max_local_holdout_gap: float = DEFAULT_MAX_LOCAL_HOLDOUT_GAP,
    rerun_root: str = "runs/weak_task_cleanroom_rerun",
    rerun_min_smoke_contract_axes: int = 0,
    rerun_require_runtime_smoke_dimensions: str = "",
    rerun_min_holdout_improvement_delta: float = 0.0,
    rerun_config: str = "",
    rerun_ack_local_llm_docker: bool = False,
    include_restore_ablation_command: bool = False,
    restore_ablation_command_kind: str = "strategy",
    restore_ablation_show_axis_action: bool = False,
    restore_ablation_apply_axis_action: bool = False,
    restore_ablation_root: str = "runs/restore_axis_ablation_next",
    restore_ablation_min_smoke_contract_axes: int = 1,
    restore_ablation_require_runtime_smoke_dimensions: str = "",
    restore_ablation_max_local_holdout_gap: float = DEFAULT_MAX_LOCAL_HOLDOUT_GAP,
    restore_ablation_config: str = "",
    restore_ablation_ack_local_llm_docker: bool = False,
    include_missing_holdout_command: bool = False,
    missing_holdout_rerun_root: str = "runs/missing_holdout_cleanroom_rerun",
    missing_holdout_min_smoke_contract_axes: int = 1,
    missing_holdout_require_runtime_smoke_dimensions: str = "",
    missing_holdout_config: str = "",
    missing_holdout_ack_local_llm_docker: bool = False,
) -> dict[str, object]:
    selected = rows[: max(0, limit)]
    return {
        "schema_version": 1,
        "row_count": len(selected),
        "total_row_count": len(rows),
        "limit": limit,
        "rows": [
            breakthrough_target_json_row(
                row,
                rank,
                include_next_command=include_next_command,
                runs_root=runs_root,
                baseline_root=baseline_root,
                official_eval_root=official_eval_root,
                min_holdout_rate=min_holdout_rate,
                min_holdout_cases=min_holdout_cases,
                baseline_upgrade_min_smoke_contract_axes=baseline_upgrade_min_smoke_contract_axes,
                baseline_upgrade_require_holdout_improvement=baseline_upgrade_require_holdout_improvement,
                baseline_upgrade_min_holdout_improvement_delta=baseline_upgrade_min_holdout_improvement_delta,
                baseline_upgrade_require_runtime_smoke_dimensions=baseline_upgrade_require_runtime_smoke_dimensions,
                baseline_upgrade_max_local_holdout_gap=baseline_upgrade_max_local_holdout_gap,
                rerun_root=rerun_root,
                rerun_min_smoke_contract_axes=rerun_min_smoke_contract_axes,
                rerun_require_runtime_smoke_dimensions=rerun_require_runtime_smoke_dimensions,
                rerun_min_holdout_improvement_delta=rerun_min_holdout_improvement_delta,
                rerun_config=rerun_config,
                rerun_ack_local_llm_docker=rerun_ack_local_llm_docker,
                include_restore_ablation_command=include_restore_ablation_command,
                restore_ablation_command_kind=restore_ablation_command_kind,
                restore_ablation_show_axis_action=restore_ablation_show_axis_action,
                restore_ablation_apply_axis_action=restore_ablation_apply_axis_action,
                restore_ablation_root=restore_ablation_root,
                restore_ablation_min_smoke_contract_axes=restore_ablation_min_smoke_contract_axes,
                restore_ablation_require_runtime_smoke_dimensions=(
                    restore_ablation_require_runtime_smoke_dimensions
                ),
                restore_ablation_max_local_holdout_gap=restore_ablation_max_local_holdout_gap,
                restore_ablation_config=restore_ablation_config,
                restore_ablation_ack_local_llm_docker=restore_ablation_ack_local_llm_docker,
                include_missing_holdout_command=include_missing_holdout_command,
                missing_holdout_rerun_root=missing_holdout_rerun_root,
                missing_holdout_min_smoke_contract_axes=missing_holdout_min_smoke_contract_axes,
                missing_holdout_require_runtime_smoke_dimensions=(
                    missing_holdout_require_runtime_smoke_dimensions
                ),
                missing_holdout_config=missing_holdout_config,
                missing_holdout_ack_local_llm_docker=missing_holdout_ack_local_llm_docker,
            )
            for rank, row in enumerate(selected, start=1)
        ],
    }


def write_json(
    rows: list[BreakthroughTarget],
    limit: int,
    *,
    include_next_command: bool = False,
    runs_root: str = "runs",
    baseline_root: str = "baselines/programbench",
    official_eval_root: str = "runs/programbench_official_eval",
    min_holdout_rate: float = 0.8,
    min_holdout_cases: int = 10,
    baseline_upgrade_min_smoke_contract_axes: int = 0,
    baseline_upgrade_require_holdout_improvement: bool = False,
    baseline_upgrade_min_holdout_improvement_delta: float = 0.0,
    baseline_upgrade_require_runtime_smoke_dimensions: str = "",
    baseline_upgrade_max_local_holdout_gap: float = DEFAULT_MAX_LOCAL_HOLDOUT_GAP,
    rerun_root: str = "runs/weak_task_cleanroom_rerun",
    rerun_min_smoke_contract_axes: int = 0,
    rerun_require_runtime_smoke_dimensions: str = "",
    rerun_min_holdout_improvement_delta: float = 0.0,
    rerun_config: str = "",
    rerun_ack_local_llm_docker: bool = False,
    include_restore_ablation_command: bool = False,
    restore_ablation_command_kind: str = "strategy",
    restore_ablation_show_axis_action: bool = False,
    restore_ablation_apply_axis_action: bool = False,
    restore_ablation_root: str = "runs/restore_axis_ablation_next",
    restore_ablation_min_smoke_contract_axes: int = 1,
    restore_ablation_require_runtime_smoke_dimensions: str = "",
    restore_ablation_max_local_holdout_gap: float = DEFAULT_MAX_LOCAL_HOLDOUT_GAP,
    restore_ablation_config: str = "",
    restore_ablation_ack_local_llm_docker: bool = False,
    include_missing_holdout_command: bool = False,
    missing_holdout_rerun_root: str = "runs/missing_holdout_cleanroom_rerun",
    missing_holdout_min_smoke_contract_axes: int = 1,
    missing_holdout_require_runtime_smoke_dimensions: str = "",
    missing_holdout_config: str = "",
    missing_holdout_ack_local_llm_docker: bool = False,
) -> None:
    payload = breakthrough_targets_json_payload(
        rows,
        limit,
        include_next_command=include_next_command,
        runs_root=runs_root,
        baseline_root=baseline_root,
        official_eval_root=official_eval_root,
        min_holdout_rate=min_holdout_rate,
        min_holdout_cases=min_holdout_cases,
        baseline_upgrade_min_smoke_contract_axes=baseline_upgrade_min_smoke_contract_axes,
        baseline_upgrade_require_holdout_improvement=baseline_upgrade_require_holdout_improvement,
        baseline_upgrade_min_holdout_improvement_delta=baseline_upgrade_min_holdout_improvement_delta,
        baseline_upgrade_require_runtime_smoke_dimensions=baseline_upgrade_require_runtime_smoke_dimensions,
        baseline_upgrade_max_local_holdout_gap=baseline_upgrade_max_local_holdout_gap,
        rerun_root=rerun_root,
        rerun_min_smoke_contract_axes=rerun_min_smoke_contract_axes,
        rerun_require_runtime_smoke_dimensions=rerun_require_runtime_smoke_dimensions,
        rerun_min_holdout_improvement_delta=rerun_min_holdout_improvement_delta,
        rerun_config=rerun_config,
        rerun_ack_local_llm_docker=rerun_ack_local_llm_docker,
        include_restore_ablation_command=include_restore_ablation_command,
        restore_ablation_command_kind=restore_ablation_command_kind,
        restore_ablation_show_axis_action=restore_ablation_show_axis_action,
        restore_ablation_apply_axis_action=restore_ablation_apply_axis_action,
        restore_ablation_root=restore_ablation_root,
        restore_ablation_min_smoke_contract_axes=restore_ablation_min_smoke_contract_axes,
        restore_ablation_require_runtime_smoke_dimensions=(
            restore_ablation_require_runtime_smoke_dimensions
        ),
        restore_ablation_max_local_holdout_gap=restore_ablation_max_local_holdout_gap,
        restore_ablation_config=restore_ablation_config,
        restore_ablation_ack_local_llm_docker=restore_ablation_ack_local_llm_docker,
        include_missing_holdout_command=include_missing_holdout_command,
        missing_holdout_rerun_root=missing_holdout_rerun_root,
        missing_holdout_min_smoke_contract_axes=missing_holdout_min_smoke_contract_axes,
        missing_holdout_require_runtime_smoke_dimensions=(
            missing_holdout_require_runtime_smoke_dimensions
        ),
        missing_holdout_config=missing_holdout_config,
        missing_holdout_ack_local_llm_docker=missing_holdout_ack_local_llm_docker,
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def build_next_command(
    row: BreakthroughTarget,
    *,
    runs_root: str,
    baseline_root: str,
    official_eval_root: str,
    min_holdout_rate: float,
    min_holdout_cases: int,
    baseline_upgrade_min_smoke_contract_axes: int = 0,
    baseline_upgrade_require_holdout_improvement: bool = False,
    baseline_upgrade_min_holdout_improvement_delta: float = 0.0,
    baseline_upgrade_require_runtime_smoke_dimensions: str = "",
    baseline_upgrade_max_local_holdout_gap: float = DEFAULT_MAX_LOCAL_HOLDOUT_GAP,
    rerun_root: str = "runs/weak_task_cleanroom_rerun",
    rerun_min_smoke_contract_axes: int = 0,
    rerun_require_runtime_smoke_dimensions: str = "",
    rerun_min_holdout_improvement_delta: float = 0.0,
    rerun_config: str = "",
    rerun_ack_local_llm_docker: bool = False,
    include_restore_ablation_command: bool = False,
    restore_ablation_command_kind: str = "strategy",
    restore_ablation_show_axis_action: bool = False,
    restore_ablation_apply_axis_action: bool = False,
    restore_ablation_root: str = "runs/restore_axis_ablation_next",
    restore_ablation_min_smoke_contract_axes: int = 1,
    restore_ablation_require_runtime_smoke_dimensions: str = "",
    restore_ablation_max_local_holdout_gap: float = DEFAULT_MAX_LOCAL_HOLDOUT_GAP,
    restore_ablation_config: str = "",
    restore_ablation_ack_local_llm_docker: bool = False,
    include_missing_holdout_command: bool = False,
    missing_holdout_rerun_root: str = "runs/missing_holdout_cleanroom_rerun",
    missing_holdout_min_smoke_contract_axes: int = 1,
    missing_holdout_require_runtime_smoke_dimensions: str = "",
    missing_holdout_config: str = "",
    missing_holdout_ack_local_llm_docker: bool = False,
    baseline_upgrade_gate: dict[str, object] | None = None,
) -> str:
    if is_official_generalization_gap(row, baseline_upgrade_gate):
        return build_official_generalization_gap_command(
            row.task_id,
            runs_root=runs_root,
            baseline_root=baseline_root,
            official_eval_root=official_eval_root,
            min_holdout_rate=min_holdout_rate,
            min_holdout_cases=min_holdout_cases,
            require_runtime_smoke_dimensions=baseline_upgrade_require_runtime_smoke_dimensions,
        )
    if is_local_generalization_gap(row, baseline_upgrade_gate):
        return build_local_generalization_gap_command(
            row.task_id,
            runs_root=runs_root,
            baseline_root=baseline_root,
            official_eval_root=official_eval_root,
            rerun_root=rerun_root,
            rerun_config=rerun_config,
            rerun_ack_local_llm_docker=rerun_ack_local_llm_docker,
            rerun_min_smoke_contract_axes=rerun_min_smoke_contract_axes,
            rerun_require_runtime_smoke_dimensions=rerun_require_runtime_smoke_dimensions,
            rerun_min_holdout_improvement_delta=rerun_min_holdout_improvement_delta,
            max_local_holdout_gap=baseline_upgrade_max_local_holdout_gap,
        )
    if row.target_class == "weak_cleanroom_rerun":
        return build_guarded_rerun_command(
            row.task_id,
            rerun_root,
            config=rerun_config or None,
            ack_local_llm_docker=rerun_ack_local_llm_docker,
            min_smoke_contract_axes=rerun_min_smoke_contract_axes,
            required_runtime_smoke_dimensions=rerun_require_runtime_smoke_dimensions,
            min_holdout_improvement_delta=rerun_min_holdout_improvement_delta,
        )
    if row.target_class == "ready_baseline_gate":
        command = (
            "python scripts/rank_programbench_candidates.py "
            f"--runs {quote_shell_arg(Path(runs_root).as_posix())} "
            f"--official-eval-root {quote_shell_arg(Path(official_eval_root).as_posix())} "
            f"--baseline-root {quote_shell_arg(Path(baseline_root).as_posix())} "
            f"--min-holdout-rate {min_holdout_rate:g} "
            f"--min-holdout-cases {int(min_holdout_cases)} "
            f"--max-local-holdout-gap {baseline_upgrade_max_local_holdout_gap:g} "
            "--official-eligible-only --allow-existing-official --latest-per-task "
        )
        if baseline_upgrade_min_smoke_contract_axes > 0:
            command += f"--min-smoke-contract-axes {int(baseline_upgrade_min_smoke_contract_axes)} "
        if baseline_upgrade_require_runtime_smoke_dimensions:
            command += (
                "--require-runtime-smoke-dimensions "
                f"{quote_shell_arg(baseline_upgrade_require_runtime_smoke_dimensions)} "
            )
        if baseline_upgrade_require_holdout_improvement:
            command += "--require-holdout-improvement "
            if baseline_upgrade_min_holdout_improvement_delta > 0:
                command += (
                    "--min-holdout-improvement-delta "
                    f"{baseline_upgrade_min_holdout_improvement_delta:g} "
                )
        return command + "--limit 20"
    if row.target_class == "restore_historical_gate" and include_restore_ablation_command:
        return build_restore_ablation_command(
            row.task_id,
            restore_ablation_root,
            runs_root=runs_root,
            baseline_root=baseline_root,
            min_smoke_contract_axes=restore_ablation_min_smoke_contract_axes,
            require_runtime_smoke_dimensions=(
                restore_ablation_require_runtime_smoke_dimensions
            ),
            max_local_holdout_gap=restore_ablation_max_local_holdout_gap,
            config=restore_ablation_config,
            ack_local_llm_docker=restore_ablation_ack_local_llm_docker,
            command_kind=restore_ablation_command_kind,
            show_axis_action=restore_ablation_show_axis_action,
            apply_axis_action=restore_ablation_apply_axis_action,
        )
    if row.target_class == "restore_historical_gate" and row.best_result_path is not None:
        return (
            "python scripts/audit_official_eval_gate.py "
            f"{quote_shell_arg(str(row.best_result_path))} "
            f"--official-eval-root {quote_shell_arg(Path(official_eval_root).as_posix())} "
            f"--baseline-root {quote_shell_arg(Path(baseline_root).as_posix())} "
            f"--min-holdout-rate {min_holdout_rate:g} "
            f"--min-holdout-cases {int(min_holdout_cases)} "
            "--allow-existing-official"
        )
    if row.target_class == "missing_reliable_holdout" and include_missing_holdout_command:
        return build_missing_holdout_command(
            row.task_id,
            missing_holdout_rerun_root,
            min_smoke_contract_axes=missing_holdout_min_smoke_contract_axes,
            require_runtime_smoke_dimensions=missing_holdout_require_runtime_smoke_dimensions,
            config=missing_holdout_config,
            ack_local_llm_docker=missing_holdout_ack_local_llm_docker,
        )
    return ""


def build_local_generalization_gap_command(
    task_id: str,
    *,
    runs_root: str,
    baseline_root: str,
    official_eval_root: str,
    rerun_root: str,
    rerun_config: str = "",
    rerun_ack_local_llm_docker: bool = False,
    rerun_min_smoke_contract_axes: int = 0,
    rerun_require_runtime_smoke_dimensions: str = "",
    rerun_min_holdout_improvement_delta: float = 0.0,
    max_local_holdout_gap: float,
) -> str:
    return build_guarded_rerun_command(
        task_id,
        rerun_root,
        config=rerun_config or DEFAULT_LOCAL_GAP_RERUN_CONFIG,
        ack_local_llm_docker=True,
        min_smoke_contract_axes=rerun_min_smoke_contract_axes,
        required_runtime_smoke_dimensions=rerun_require_runtime_smoke_dimensions,
        min_holdout_improvement_delta=rerun_min_holdout_improvement_delta,
        max_generalization_risk="low",
        max_local_holdout_gap=max_local_holdout_gap,
        generalization_risk_root=Path(runs_root).as_posix(),
        baseline_root=Path(baseline_root).as_posix(),
        official_eval_root=Path(official_eval_root).as_posix(),
    )


def build_official_generalization_gap_command(
    task_id: str,
    *,
    runs_root: str,
    baseline_root: str,
    official_eval_root: str,
    min_holdout_rate: float,
    min_holdout_cases: int,
    require_runtime_smoke_dimensions: str = "",
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
    if require_runtime_smoke_dimensions:
        command += (
            "--require-runtime-smoke-dimensions "
            f"{quote_shell_arg(require_runtime_smoke_dimensions)} "
        )
    return command + "--latest-per-task --format json --limit 20"


def build_restore_ablation_command(
    task_id: str,
    restore_ablation_root: str,
    *,
    runs_root: str,
    baseline_root: str,
    min_smoke_contract_axes: int,
    require_runtime_smoke_dimensions: str = "",
    max_local_holdout_gap: float = DEFAULT_MAX_LOCAL_HOLDOUT_GAP,
    config: str = "",
    ack_local_llm_docker: bool = False,
    command_kind: str = "strategy",
    show_axis_action: bool = False,
    apply_axis_action: bool = False,
) -> str:
    if command_kind not in {"strategy", "batch"}:
        raise ValueError(f"Unsupported restore ablation command kind: {command_kind}")

    if command_kind == "batch":
        command = (
            "python scripts/run_restore_axis_ablation_batch.py "
            f"{quote_shell_arg(task_id)} "
            f"--runs {quote_shell_arg(Path(runs_root).as_posix())} "
            f"--baseline-root {quote_shell_arg(Path(baseline_root).as_posix())} "
            f"--output-root {quote_shell_arg(Path(restore_ablation_root).as_posix())} "
            "--variants baseline_no_adaptive adaptive_profile adaptive_deep "
            f"--min-smoke-contract-axes {int(min_smoke_contract_axes)} "
            "--max-generalization-risk low "
            f"--max-local-holdout-gap {max_local_holdout_gap:g} "
        )
        if require_runtime_smoke_dimensions:
            command += (
                "--require-runtime-smoke-dimensions "
                f"{quote_shell_arg(require_runtime_smoke_dimensions)} "
            )
        if config:
            command += f"--config {quote_shell_arg(config)} "
        if ack_local_llm_docker:
            command += "--ack-local-llm-docker "
        if show_axis_action:
            command += "--show-axis-action "
        if apply_axis_action:
            command += "--apply-axis-action "
        return command + "--format json --dry-run"

    run_root = Path(restore_ablation_root) / safe_path_component(task_id)
    command = (
        "python scripts/run_official_strategy_ablation.py "
        f"{quote_shell_arg(task_id)} "
        f"--runs {quote_shell_arg(run_root.as_posix())} "
        "--variants baseline_no_adaptive adaptive_profile adaptive_deep "
        "--skip-official-eval "
        "--require-holdout-improvement "
        f"--holdout-history-root {quote_shell_arg(Path(runs_root).as_posix())} "
        "--max-generalization-risk low "
        f"--max-local-holdout-gap {max_local_holdout_gap:g} "
        f"--generalization-risk-root {quote_shell_arg(Path(runs_root).as_posix())} "
        f"--baseline-root {quote_shell_arg(Path(baseline_root).as_posix())} "
        f"--min-smoke-contract-axes {int(min_smoke_contract_axes)} "
    )
    if require_runtime_smoke_dimensions:
        command += (
            "--require-runtime-smoke-dimensions "
            f"{quote_shell_arg(require_runtime_smoke_dimensions)} "
        )
    if config:
        command += f"--config {quote_shell_arg(config)} "
    if ack_local_llm_docker:
        command += "--ack-local-llm-docker "
    return command + "--dry-run"


def build_missing_holdout_command(
    task_id: str,
    missing_holdout_rerun_root: str,
    *,
    min_smoke_contract_axes: int,
    require_runtime_smoke_dimensions: str = "",
    config: str = "",
    ack_local_llm_docker: bool = False,
) -> str:
    run_root = Path(missing_holdout_rerun_root) / safe_path_component(task_id)
    command = (
        "python scripts/run_missing_holdout_cleanroom_rerun.py "
        f"{quote_shell_arg(task_id)} "
    )
    if config:
        command += f"--config {quote_shell_arg(config)} "
    command += f"--runs {quote_shell_arg(run_root.as_posix())} "
    if min_smoke_contract_axes > 0:
        command += f"--min-smoke-contract-axes {int(min_smoke_contract_axes)} "
    if require_runtime_smoke_dimensions:
        command += (
            "--require-runtime-smoke-dimensions "
            f"{quote_shell_arg(require_runtime_smoke_dimensions)} "
        )
    if ack_local_llm_docker:
        command += "--ack-local-llm-docker "
    return command + "--dry-run"


def safe_path_component(value: str) -> str:
    return "".join(character if character.isalnum() or character in "._-" else "_" for character in value)


def format_path(path: Path | None) -> str:
    if path is None:
        return "-"
    return str(path)


def format_json_path(path: Path | None) -> str | None:
    if path is None:
        return None
    return str(path)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    rows = collect_official_breakthrough_targets(
        args.runs,
        args.baseline_root,
        min_holdout_cases=args.min_holdout_cases,
        min_holdout_rate=args.min_holdout_rate,
    )
    write = write_json if args.format == "json" else write_markdown
    write(
        rows,
        args.limit,
        include_next_command=args.include_next_command,
        runs_root=args.runs,
        baseline_root=args.baseline_root,
        official_eval_root=args.official_eval_root,
        min_holdout_rate=args.min_holdout_rate,
        min_holdout_cases=args.min_holdout_cases,
        baseline_upgrade_min_smoke_contract_axes=args.baseline_upgrade_min_smoke_contract_axes,
        baseline_upgrade_require_holdout_improvement=args.baseline_upgrade_require_holdout_improvement,
        baseline_upgrade_min_holdout_improvement_delta=args.baseline_upgrade_min_holdout_improvement_delta,
        baseline_upgrade_require_runtime_smoke_dimensions=args.baseline_upgrade_require_runtime_smoke_dimensions,
        baseline_upgrade_max_local_holdout_gap=args.baseline_upgrade_max_local_holdout_gap,
        rerun_root=args.rerun_root,
        rerun_min_smoke_contract_axes=args.rerun_min_smoke_contract_axes,
        rerun_require_runtime_smoke_dimensions=args.rerun_require_runtime_smoke_dimensions,
        rerun_min_holdout_improvement_delta=args.rerun_min_holdout_improvement_delta,
        rerun_config=args.rerun_config,
        rerun_ack_local_llm_docker=args.rerun_ack_local_llm_docker,
        include_restore_ablation_command=args.include_restore_ablation_command,
        restore_ablation_command_kind=args.restore_ablation_command_kind,
        restore_ablation_show_axis_action=args.restore_ablation_show_axis_action,
        restore_ablation_apply_axis_action=args.restore_ablation_apply_axis_action,
        restore_ablation_root=args.restore_ablation_root,
        restore_ablation_min_smoke_contract_axes=args.restore_ablation_min_smoke_contract_axes,
        restore_ablation_require_runtime_smoke_dimensions=(
            args.restore_ablation_require_runtime_smoke_dimensions
        ),
        restore_ablation_max_local_holdout_gap=args.restore_ablation_max_local_holdout_gap,
        restore_ablation_config=args.restore_ablation_config,
        restore_ablation_ack_local_llm_docker=args.restore_ablation_ack_local_llm_docker,
        include_missing_holdout_command=args.include_missing_holdout_command,
        missing_holdout_rerun_root=args.missing_holdout_rerun_root,
        missing_holdout_min_smoke_contract_axes=args.missing_holdout_min_smoke_contract_axes,
        missing_holdout_require_runtime_smoke_dimensions=(
            args.missing_holdout_require_runtime_smoke_dimensions
        ),
        missing_holdout_config=args.missing_holdout_config,
        missing_holdout_ack_local_llm_docker=args.missing_holdout_ack_local_llm_docker,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
