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
    discover_baseline_task_ids as discover_candidate_baseline_task_ids,
    discover_official_eval_task_ids as discover_candidate_official_eval_task_ids,
    normalize_required_runtime_smoke_dimensions,
    official_gate_blockers,
    official_gate_reason,
    read_candidate_row,
)


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
        "--include-restore-ablation-command",
        action="store_true",
        help="Render guarded restore-axis strategy ablation dry-run commands for restore rows",
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
    rerun_root: str = "runs/weak_task_cleanroom_rerun",
    rerun_min_smoke_contract_axes: int = 0,
    rerun_require_runtime_smoke_dimensions: str = "",
    rerun_min_holdout_improvement_delta: float = 0.0,
    include_restore_ablation_command: bool = False,
    restore_ablation_root: str = "runs/restore_axis_ablation_next",
    restore_ablation_min_smoke_contract_axes: int = 1,
    restore_ablation_require_runtime_smoke_dimensions: str = "",
    include_missing_holdout_command: bool = False,
    missing_holdout_rerun_root: str = "runs/missing_holdout_cleanroom_rerun",
    missing_holdout_min_smoke_contract_axes: int = 1,
    missing_holdout_require_runtime_smoke_dimensions: str = "",
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
        baseline_gate_cell = baseline_upgrade_gate_label(
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
        )
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
                rerun_root=rerun_root,
                rerun_min_smoke_contract_axes=rerun_min_smoke_contract_axes,
                rerun_require_runtime_smoke_dimensions=rerun_require_runtime_smoke_dimensions,
                rerun_min_holdout_improvement_delta=rerun_min_holdout_improvement_delta,
                include_restore_ablation_command=include_restore_ablation_command,
                restore_ablation_root=restore_ablation_root,
                restore_ablation_min_smoke_contract_axes=restore_ablation_min_smoke_contract_axes,
                restore_ablation_require_runtime_smoke_dimensions=(
                    restore_ablation_require_runtime_smoke_dimensions
                ),
                include_missing_holdout_command=include_missing_holdout_command,
                missing_holdout_rerun_root=missing_holdout_rerun_root,
                missing_holdout_min_smoke_contract_axes=missing_holdout_min_smoke_contract_axes,
                missing_holdout_require_runtime_smoke_dimensions=(
                    missing_holdout_require_runtime_smoke_dimensions
                ),
            )
            command_cell = f" | `{command}`" if command else " | -"
        print(
            f"| {index} | {row.task_id} | {format_official(row)} | "
            f"{format_optional_rate(row.latest_holdout_resolved_rate, row.latest_holdout_cases)} | "
            f"{format_optional_rate(row.best_holdout_resolved_rate, row.best_holdout_cases)} | "
            f"{row.target_class} | {row.next_action} | {row.reason} | "
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
    rerun_root: str = "runs/weak_task_cleanroom_rerun",
    rerun_min_smoke_contract_axes: int = 0,
    rerun_require_runtime_smoke_dimensions: str = "",
    rerun_min_holdout_improvement_delta: float = 0.0,
    include_restore_ablation_command: bool = False,
    restore_ablation_root: str = "runs/restore_axis_ablation_next",
    restore_ablation_min_smoke_contract_axes: int = 1,
    restore_ablation_require_runtime_smoke_dimensions: str = "",
    include_missing_holdout_command: bool = False,
    missing_holdout_rerun_root: str = "runs/missing_holdout_cleanroom_rerun",
    missing_holdout_min_smoke_contract_axes: int = 1,
    missing_holdout_require_runtime_smoke_dimensions: str = "",
) -> dict[str, object]:
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
            rerun_root=rerun_root,
            rerun_min_smoke_contract_axes=rerun_min_smoke_contract_axes,
            rerun_require_runtime_smoke_dimensions=rerun_require_runtime_smoke_dimensions,
            rerun_min_holdout_improvement_delta=rerun_min_holdout_improvement_delta,
            include_restore_ablation_command=include_restore_ablation_command,
            restore_ablation_root=restore_ablation_root,
            restore_ablation_min_smoke_contract_axes=restore_ablation_min_smoke_contract_axes,
            restore_ablation_require_runtime_smoke_dimensions=(
                restore_ablation_require_runtime_smoke_dimensions
            ),
            include_missing_holdout_command=include_missing_holdout_command,
            missing_holdout_rerun_root=missing_holdout_rerun_root,
            missing_holdout_min_smoke_contract_axes=missing_holdout_min_smoke_contract_axes,
            missing_holdout_require_runtime_smoke_dimensions=(
                missing_holdout_require_runtime_smoke_dimensions
            ),
        )
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
        "target_class": row.target_class,
        "next_action": row.next_action,
        "reason": row.reason,
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
    )
    if gate is None:
        return "-"
    blockers = gate.get("blockers")
    if isinstance(blockers, list) and blockers:
        return ",".join(str(blocker) for blocker in blockers)
    return str(gate.get("reason") or "-")


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
        "candidate": None,
    }
    if row.latest_result_path is None:
        return gate

    official_task_ids = discover_candidate_official_eval_task_ids(Path(official_eval_root))
    official_task_ids.update(discover_candidate_baseline_task_ids(Path(baseline_root)))
    candidate = read_candidate_row(row.latest_result_path, official_task_ids)
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
    rerun_root: str = "runs/weak_task_cleanroom_rerun",
    rerun_min_smoke_contract_axes: int = 0,
    rerun_require_runtime_smoke_dimensions: str = "",
    rerun_min_holdout_improvement_delta: float = 0.0,
    include_restore_ablation_command: bool = False,
    restore_ablation_root: str = "runs/restore_axis_ablation_next",
    restore_ablation_min_smoke_contract_axes: int = 1,
    restore_ablation_require_runtime_smoke_dimensions: str = "",
    include_missing_holdout_command: bool = False,
    missing_holdout_rerun_root: str = "runs/missing_holdout_cleanroom_rerun",
    missing_holdout_min_smoke_contract_axes: int = 1,
    missing_holdout_require_runtime_smoke_dimensions: str = "",
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
                rerun_root=rerun_root,
                rerun_min_smoke_contract_axes=rerun_min_smoke_contract_axes,
                rerun_require_runtime_smoke_dimensions=rerun_require_runtime_smoke_dimensions,
                rerun_min_holdout_improvement_delta=rerun_min_holdout_improvement_delta,
                include_restore_ablation_command=include_restore_ablation_command,
                restore_ablation_root=restore_ablation_root,
                restore_ablation_min_smoke_contract_axes=restore_ablation_min_smoke_contract_axes,
                restore_ablation_require_runtime_smoke_dimensions=(
                    restore_ablation_require_runtime_smoke_dimensions
                ),
                include_missing_holdout_command=include_missing_holdout_command,
                missing_holdout_rerun_root=missing_holdout_rerun_root,
                missing_holdout_min_smoke_contract_axes=missing_holdout_min_smoke_contract_axes,
                missing_holdout_require_runtime_smoke_dimensions=(
                    missing_holdout_require_runtime_smoke_dimensions
                ),
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
    rerun_root: str = "runs/weak_task_cleanroom_rerun",
    rerun_min_smoke_contract_axes: int = 0,
    rerun_require_runtime_smoke_dimensions: str = "",
    rerun_min_holdout_improvement_delta: float = 0.0,
    include_restore_ablation_command: bool = False,
    restore_ablation_root: str = "runs/restore_axis_ablation_next",
    restore_ablation_min_smoke_contract_axes: int = 1,
    restore_ablation_require_runtime_smoke_dimensions: str = "",
    include_missing_holdout_command: bool = False,
    missing_holdout_rerun_root: str = "runs/missing_holdout_cleanroom_rerun",
    missing_holdout_min_smoke_contract_axes: int = 1,
    missing_holdout_require_runtime_smoke_dimensions: str = "",
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
        rerun_root=rerun_root,
        rerun_min_smoke_contract_axes=rerun_min_smoke_contract_axes,
        rerun_require_runtime_smoke_dimensions=rerun_require_runtime_smoke_dimensions,
        rerun_min_holdout_improvement_delta=rerun_min_holdout_improvement_delta,
        include_restore_ablation_command=include_restore_ablation_command,
        restore_ablation_root=restore_ablation_root,
        restore_ablation_min_smoke_contract_axes=restore_ablation_min_smoke_contract_axes,
        restore_ablation_require_runtime_smoke_dimensions=(
            restore_ablation_require_runtime_smoke_dimensions
        ),
        include_missing_holdout_command=include_missing_holdout_command,
        missing_holdout_rerun_root=missing_holdout_rerun_root,
        missing_holdout_min_smoke_contract_axes=missing_holdout_min_smoke_contract_axes,
        missing_holdout_require_runtime_smoke_dimensions=(
            missing_holdout_require_runtime_smoke_dimensions
        ),
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
    rerun_root: str = "runs/weak_task_cleanroom_rerun",
    rerun_min_smoke_contract_axes: int = 0,
    rerun_require_runtime_smoke_dimensions: str = "",
    rerun_min_holdout_improvement_delta: float = 0.0,
    include_restore_ablation_command: bool = False,
    restore_ablation_root: str = "runs/restore_axis_ablation_next",
    restore_ablation_min_smoke_contract_axes: int = 1,
    restore_ablation_require_runtime_smoke_dimensions: str = "",
    include_missing_holdout_command: bool = False,
    missing_holdout_rerun_root: str = "runs/missing_holdout_cleanroom_rerun",
    missing_holdout_min_smoke_contract_axes: int = 1,
    missing_holdout_require_runtime_smoke_dimensions: str = "",
) -> str:
    if row.target_class == "weak_cleanroom_rerun":
        return build_guarded_rerun_command(
            row.task_id,
            rerun_root,
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
        )
    return ""


def build_restore_ablation_command(
    task_id: str,
    restore_ablation_root: str,
    *,
    runs_root: str,
    baseline_root: str,
    min_smoke_contract_axes: int,
    require_runtime_smoke_dimensions: str = "",
) -> str:
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
        f"--generalization-risk-root {quote_shell_arg(Path(runs_root).as_posix())} "
        f"--baseline-root {quote_shell_arg(Path(baseline_root).as_posix())} "
        f"--min-smoke-contract-axes {int(min_smoke_contract_axes)} "
    )
    if require_runtime_smoke_dimensions:
        command += (
            "--require-runtime-smoke-dimensions "
            f"{quote_shell_arg(require_runtime_smoke_dimensions)} "
        )
    return command + "--dry-run"


def build_missing_holdout_command(
    task_id: str,
    missing_holdout_rerun_root: str,
    *,
    min_smoke_contract_axes: int,
    require_runtime_smoke_dimensions: str = "",
) -> str:
    run_root = Path(missing_holdout_rerun_root) / safe_path_component(task_id)
    command = (
        "python scripts/run_missing_holdout_cleanroom_rerun.py "
        f"{quote_shell_arg(task_id)} "
        f"--runs {quote_shell_arg(run_root.as_posix())} "
    )
    if min_smoke_contract_axes > 0:
        command += f"--min-smoke-contract-axes {int(min_smoke_contract_axes)} "
    if require_runtime_smoke_dimensions:
        command += (
            "--require-runtime-smoke-dimensions "
            f"{quote_shell_arg(require_runtime_smoke_dimensions)} "
        )
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
        rerun_root=args.rerun_root,
        rerun_min_smoke_contract_axes=args.rerun_min_smoke_contract_axes,
        rerun_require_runtime_smoke_dimensions=args.rerun_require_runtime_smoke_dimensions,
        rerun_min_holdout_improvement_delta=args.rerun_min_holdout_improvement_delta,
        include_restore_ablation_command=args.include_restore_ablation_command,
        restore_ablation_root=args.restore_ablation_root,
        restore_ablation_min_smoke_contract_axes=args.restore_ablation_min_smoke_contract_axes,
        restore_ablation_require_runtime_smoke_dimensions=(
            args.restore_ablation_require_runtime_smoke_dimensions
        ),
        include_missing_holdout_command=args.include_missing_holdout_command,
        missing_holdout_rerun_root=args.missing_holdout_rerun_root,
        missing_holdout_min_smoke_contract_axes=args.missing_holdout_min_smoke_contract_axes,
        missing_holdout_require_runtime_smoke_dimensions=(
            args.missing_holdout_require_runtime_smoke_dimensions
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
