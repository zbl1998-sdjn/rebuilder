"""Summarize local aggregate holdout trends across ReBuilder runs."""

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

from core.submission import parse_runtime_smoke_dimensions  # noqa: E402


@dataclass(frozen=True)
class HoldoutRun:
    task_id: str
    holdout_resolved_rate: float
    holdout_cases: int
    resolved_rate: float
    result_path: Path
    modified_at: float


@dataclass(frozen=True)
class HoldoutTrend:
    task_id: str
    best_holdout_resolved_rate: float
    best_holdout_cases: int
    best_result_path: Path
    latest_holdout_resolved_rate: float
    latest_holdout_cases: int
    latest_result_path: Path
    delta_from_best: float


@dataclass(frozen=True)
class WeakRerunRecommendation:
    task_id: str
    latest_holdout_resolved_rate: float
    latest_holdout_cases: int
    best_holdout_resolved_rate: float
    best_holdout_cases: int
    reason: str
    required_flags: str


def non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be non-negative")
    return parsed


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def non_negative_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError("value must be non-negative and finite")
    return parsed


def rate_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0 or parsed > 1:
        raise argparse.ArgumentTypeError("value must be a finite rate between 0 and 1")
    return parsed


def validate_rate_float(name: str, value: float) -> None:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite rate between 0 and 1") from exc
    if not math.isfinite(parsed) or parsed < 0 or parsed > 1:
        raise ValueError(f"{name} must be a finite rate between 0 and 1")


def validate_non_negative_finite_float(name: str, value: float) -> None:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be non-negative and finite") from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise ValueError(f"{name} must be non-negative and finite")


def validate_non_negative_finite_int(name: str, value: int) -> None:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be non-negative finite integer") from exc
    if not math.isfinite(parsed) or parsed < 0 or not parsed.is_integer():
        raise ValueError(f"{name} must be non-negative finite integer")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize local aggregate holdout trends")
    parser.add_argument("--runs", default="runs", help="Root directory containing result.json files")
    parser.add_argument(
        "--task",
        dest="task_ids",
        action="append",
        default=None,
        help="Limit output to a specific task_id; may be repeated",
    )
    parser.add_argument("--limit", type=positive_int, default=20)
    parser.add_argument(
        "--min-holdout-cases",
        type=non_negative_int,
        default=10,
        help="Minimum holdout cases required for best/latest trend rows",
    )
    parser.add_argument(
        "--min-holdout-rate",
        type=rate_float,
        default=0.8,
        help="Local holdout gate used when recommending weak-task reruns",
    )
    parser.add_argument(
        "--recommend-weak-reruns",
        action="store_true",
        help="Also print aggregate-only weak-task rerun recommendations",
    )
    parser.add_argument(
        "--include-rerun-command",
        action="store_true",
        help="Include a guarded run_weak_task_cleanroom_rerun.py dry-run command in recommendation rows",
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
        type=parse_runtime_smoke_dimensions,
        default=(),
        dest="rerun_required_runtime_smoke_dimensions",
        help=(
            "Optional comma-separated runtime-smoke dimensions to require in guarded "
            "weak-task rerun commands"
        ),
    )
    parser.add_argument(
        "--rerun-min-holdout-improvement-delta",
        type=non_negative_float,
        default=0.0,
        help="Optional holdout improvement delta gate to include in guarded weak-task rerun commands",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format. JSON emits aggregate-only holdout trends and weak-rerun recommendations.",
    )
    return parser.parse_args(argv)


def collect_holdout_trends(
    runs_root: Path | str,
    *,
    min_holdout_cases: int = 10,
    task_ids: tuple[str, ...] | list[str] | None = None,
) -> list[HoldoutTrend]:
    selected_tasks = set(task_ids or ())
    by_task: dict[str, list[HoldoutRun]] = {}
    for result_path in Path(runs_root).rglob("result.json"):
        run = read_holdout_run(result_path)
        if run is None:
            continue
        if run.holdout_cases < min_holdout_cases:
            continue
        if selected_tasks and run.task_id not in selected_tasks:
            continue
        by_task.setdefault(run.task_id, []).append(run)

    trends = [build_trend(task_id, runs) for task_id, runs in by_task.items()]
    return sorted(
        trends,
        key=lambda row: (
            -row.latest_holdout_resolved_rate,
            -row.best_holdout_resolved_rate,
            -row.latest_holdout_cases,
            row.task_id,
        ),
    )


def read_holdout_run(result_path: Path) -> HoldoutRun | None:
    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    holdout_rate = as_optional_float(payload.get("holdout_resolved_rate"))
    holdout_cases = as_int(payload.get("holdout_cases"))
    if holdout_rate is None or holdout_cases <= 0:
        return None
    task_id = str(payload.get("task_id") or infer_task_id(result_path) or "")
    if not task_id:
        return None
    return HoldoutRun(
        task_id=task_id,
        holdout_resolved_rate=holdout_rate,
        holdout_cases=holdout_cases,
        resolved_rate=as_float(payload.get("resolved_rate")),
        result_path=result_path,
        modified_at=result_path.stat().st_mtime,
    )


def build_trend(task_id: str, runs: list[HoldoutRun]) -> HoldoutTrend:
    best = max(
        runs,
        key=lambda row: (
            row.holdout_resolved_rate,
            row.holdout_cases,
            row.modified_at,
            str(row.result_path),
        ),
    )
    latest = max(runs, key=lambda row: (row.modified_at, str(row.result_path)))
    return HoldoutTrend(
        task_id=task_id,
        best_holdout_resolved_rate=best.holdout_resolved_rate,
        best_holdout_cases=best.holdout_cases,
        best_result_path=best.result_path,
        latest_holdout_resolved_rate=latest.holdout_resolved_rate,
        latest_holdout_cases=latest.holdout_cases,
        latest_result_path=latest.result_path,
        delta_from_best=latest.holdout_resolved_rate - best.holdout_resolved_rate,
    )


def infer_task_id(result_path: Path) -> str | None:
    parts = result_path.parts
    if "generated" in parts:
        generated_index = parts.index("generated")
        if generated_index + 1 < len(parts):
            return parts[generated_index + 1]
    return result_path.parent.name or None


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


def format_rate(value: float) -> str:
    return f"{value:.1%}"


def trend_status(row: HoldoutTrend) -> str:
    if row.delta_from_best < 0:
        return "regressed"
    return "best"


def recommend_weak_reruns(
    rows: list[HoldoutTrend],
    *,
    min_holdout_rate: float = 0.8,
    history_root: str = "runs",
) -> list[WeakRerunRecommendation]:
    validate_rate_float("min_holdout_rate", min_holdout_rate)
    recommendations: list[WeakRerunRecommendation] = []
    flags = f"--skip-official-eval --require-holdout-improvement --holdout-history-root {history_root}"
    for row in rows:
        if row.best_holdout_resolved_rate >= min_holdout_rate:
            continue
        reason = "historical_best_below_gate"
        if row.delta_from_best < 0:
            reason = "latest_regressed_and_historical_best_below_gate"
        recommendations.append(
            WeakRerunRecommendation(
                task_id=row.task_id,
                latest_holdout_resolved_rate=row.latest_holdout_resolved_rate,
                latest_holdout_cases=row.latest_holdout_cases,
                best_holdout_resolved_rate=row.best_holdout_resolved_rate,
                best_holdout_cases=row.best_holdout_cases,
                reason=reason,
                required_flags=flags,
            )
        )
    return sorted(
        recommendations,
        key=lambda row: (
            row.best_holdout_resolved_rate,
            row.latest_holdout_resolved_rate,
            row.task_id,
        ),
    )


def write_markdown(rows: list[HoldoutTrend], limit: int) -> None:
    selected = rows[: max(0, limit)]
    print("| rank | task | latest holdout | latest cases | best holdout | best cases | trend | latest result | best result |")
    print("| ---: | --- | ---: | ---: | ---: | ---: | --- | --- | --- |")
    for index, row in enumerate(selected, start=1):
        print(
            f"| {index} | {row.task_id} | {format_rate(row.latest_holdout_resolved_rate)} | "
            f"{row.latest_holdout_cases} | {format_rate(row.best_holdout_resolved_rate)} | "
            f"{row.best_holdout_cases} | {trend_status(row)} | {row.latest_result_path} | {row.best_result_path} |"
        )


def write_recommendations(
    rows: list[WeakRerunRecommendation],
    limit: int,
    *,
    min_holdout_rate: float,
    include_rerun_command: bool = False,
    rerun_root: str = "runs/weak_task_cleanroom_rerun",
    rerun_min_smoke_contract_axes: int = 0,
    rerun_required_runtime_smoke_dimensions: tuple[str, ...] = (),
    rerun_min_holdout_improvement_delta: float = 0.0,
) -> None:
    selected = rows[: max(0, limit)]
    print()
    command_header = " | guarded command" if include_rerun_command else ""
    command_rule = " | ---" if include_rerun_command else ""
    print(f"| rank | task | latest holdout | best holdout | rerun target | reason | required flags{command_header} |")
    print(f"| ---: | --- | ---: | ---: | --- | --- | ---{command_rule} |")
    for index, row in enumerate(selected, start=1):
        target = f">= {format_rate(min_holdout_rate)} and > {format_rate(row.best_holdout_resolved_rate)}"
        command_cell = ""
        if include_rerun_command:
            command_cell = (
                " | `"
                f"{build_guarded_rerun_command(row.task_id, rerun_root, min_smoke_contract_axes=rerun_min_smoke_contract_axes, required_runtime_smoke_dimensions=rerun_required_runtime_smoke_dimensions, min_holdout_improvement_delta=rerun_min_holdout_improvement_delta)}"
                "`"
            )
        print(
            f"| {index} | {row.task_id} | "
            f"{format_rate(row.latest_holdout_resolved_rate)} ({row.latest_holdout_cases}) | "
            f"{format_rate(row.best_holdout_resolved_rate)} ({row.best_holdout_cases}) | "
            f"{target} | {row.reason} | `{row.required_flags}`{command_cell} |"
        )


def trend_json_row(row: HoldoutTrend, rank: int) -> dict[str, object]:
    return {
        "rank": rank,
        "task_id": row.task_id,
        "latest_holdout_resolved_rate": row.latest_holdout_resolved_rate,
        "latest_holdout_cases": row.latest_holdout_cases,
        "best_holdout_resolved_rate": row.best_holdout_resolved_rate,
        "best_holdout_cases": row.best_holdout_cases,
        "delta_from_best": row.delta_from_best,
        "trend": trend_status(row),
        "latest_result_path": str(row.latest_result_path),
        "best_result_path": str(row.best_result_path),
    }


def recommendation_json_row(
    row: WeakRerunRecommendation,
    rank: int,
    *,
    min_holdout_rate: float,
    include_rerun_command: bool = False,
    rerun_root: str = "runs/weak_task_cleanroom_rerun",
    rerun_min_smoke_contract_axes: int = 0,
    rerun_required_runtime_smoke_dimensions: tuple[str, ...] = (),
    rerun_min_holdout_improvement_delta: float = 0.0,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "rank": rank,
        "task_id": row.task_id,
        "latest_holdout_resolved_rate": row.latest_holdout_resolved_rate,
        "latest_holdout_cases": row.latest_holdout_cases,
        "best_holdout_resolved_rate": row.best_holdout_resolved_rate,
        "best_holdout_cases": row.best_holdout_cases,
        "rerun_target": {
            "min_holdout_rate": min_holdout_rate,
            "must_exceed_best_holdout_rate": row.best_holdout_resolved_rate,
        },
        "reason": row.reason,
        "required_flags": row.required_flags,
    }
    if include_rerun_command:
        payload["guarded_command"] = build_guarded_rerun_command(
            row.task_id,
            rerun_root,
            min_smoke_contract_axes=rerun_min_smoke_contract_axes,
            required_runtime_smoke_dimensions=rerun_required_runtime_smoke_dimensions,
            min_holdout_improvement_delta=rerun_min_holdout_improvement_delta,
        )
    return payload


def holdout_trends_json_payload(
    rows: list[HoldoutTrend],
    limit: int,
    *,
    recommendations: list[WeakRerunRecommendation] | None = None,
    min_holdout_rate: float = 0.8,
    include_rerun_command: bool = False,
    rerun_root: str = "runs/weak_task_cleanroom_rerun",
    rerun_min_smoke_contract_axes: int = 0,
    rerun_required_runtime_smoke_dimensions: tuple[str, ...] = (),
    rerun_min_holdout_improvement_delta: float = 0.0,
) -> dict[str, object]:
    selected = rows[: max(0, limit)]
    recommendation_rows = recommendations or []
    selected_recommendations = recommendation_rows[: max(0, limit)]
    return {
        "schema_version": 1,
        "row_count": len(selected),
        "total_row_count": len(rows),
        "limit": limit,
        "rows": [trend_json_row(row, rank) for rank, row in enumerate(selected, start=1)],
        "recommendations": {
            "enabled": recommendations is not None,
            "row_count": len(selected_recommendations),
            "total_row_count": len(recommendation_rows),
            "rows": [
                recommendation_json_row(
                    row,
                    rank,
                    min_holdout_rate=min_holdout_rate,
                    include_rerun_command=include_rerun_command,
                    rerun_root=rerun_root,
                    rerun_min_smoke_contract_axes=rerun_min_smoke_contract_axes,
                    rerun_required_runtime_smoke_dimensions=(
                        rerun_required_runtime_smoke_dimensions
                    ),
                    rerun_min_holdout_improvement_delta=rerun_min_holdout_improvement_delta,
                )
                for rank, row in enumerate(selected_recommendations, start=1)
            ],
        },
    }


def write_json(
    rows: list[HoldoutTrend],
    limit: int,
    *,
    recommendations: list[WeakRerunRecommendation] | None = None,
    min_holdout_rate: float = 0.8,
    include_rerun_command: bool = False,
    rerun_root: str = "runs/weak_task_cleanroom_rerun",
    rerun_min_smoke_contract_axes: int = 0,
    rerun_required_runtime_smoke_dimensions: tuple[str, ...] = (),
    rerun_min_holdout_improvement_delta: float = 0.0,
) -> None:
    print(
        json.dumps(
            holdout_trends_json_payload(
                rows,
                limit,
                recommendations=recommendations,
                min_holdout_rate=min_holdout_rate,
                include_rerun_command=include_rerun_command,
                rerun_root=rerun_root,
                rerun_min_smoke_contract_axes=rerun_min_smoke_contract_axes,
                rerun_required_runtime_smoke_dimensions=(
                    rerun_required_runtime_smoke_dimensions
                ),
                rerun_min_holdout_improvement_delta=rerun_min_holdout_improvement_delta,
            ),
            indent=2,
            ensure_ascii=False,
        )
    )


def build_guarded_rerun_command(
    task_id: str,
    rerun_root: str,
    *,
    config: str | None = None,
    ack_local_llm_docker: bool = False,
    min_smoke_contract_axes: int = 0,
    required_runtime_smoke_dimensions: tuple[str, ...] | list[str] | str = (),
    min_holdout_improvement_delta: float = 0.0,
    max_generalization_risk: str | None = None,
    max_local_holdout_gap: float | None = None,
    generalization_risk_root: str | None = None,
    baseline_root: str | None = None,
    official_eval_root: str | None = None,
) -> str:
    validate_non_negative_finite_int("min_smoke_contract_axes", min_smoke_contract_axes)
    required_dimensions = parse_runtime_smoke_dimensions(
        required_runtime_smoke_dimensions
    )
    validate_non_negative_finite_float(
        "min_holdout_improvement_delta",
        min_holdout_improvement_delta,
    )
    run_path = (Path(rerun_root) / safe_path_slug(task_id)).as_posix()
    command = (
        "python scripts/run_weak_task_cleanroom_rerun.py "
        f"{quote_shell_arg(task_id)} "
    )
    if config:
        command += f"--config {quote_shell_arg(config)} "
    command += f"--runs {quote_shell_arg(run_path)} --dry-run"
    if min_smoke_contract_axes > 0:
        command += f" --min-smoke-contract-axes {int(min_smoke_contract_axes)}"
    if required_dimensions:
        command += f" --require-runtime-smoke-dimensions {','.join(required_dimensions)}"
    if min_holdout_improvement_delta > 0:
        command += f" --min-holdout-improvement-delta {float(min_holdout_improvement_delta):g}"
    if max_generalization_risk:
        if max_generalization_risk not in {"low", "medium", "high"}:
            raise ValueError("max_generalization_risk must be low, medium, or high")
        command += f" --max-generalization-risk {max_generalization_risk}"
        if max_local_holdout_gap is not None:
            validate_rate_float("max_local_holdout_gap", max_local_holdout_gap)
            command += f" --max-local-holdout-gap {float(max_local_holdout_gap):g}"
        if generalization_risk_root:
            command += f" --generalization-risk-root {quote_shell_arg(generalization_risk_root)}"
        if baseline_root:
            command += f" --baseline-root {quote_shell_arg(baseline_root)}"
        if official_eval_root:
            command += f" --official-eval-root {quote_shell_arg(official_eval_root)}"
    if ack_local_llm_docker:
        command += " --ack-local-llm-docker"
    return command


def safe_path_slug(value: str) -> str:
    return "".join(char if char.isalnum() or char in "._-" else "_" for char in value)


def quote_shell_arg(value: str) -> str:
    if all(char.isalnum() or char in "._-/\\:" for char in value):
        return value
    return "'" + value.replace("'", "''") + "'"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    rows = collect_holdout_trends(
        args.runs,
        min_holdout_cases=args.min_holdout_cases,
        task_ids=args.task_ids,
    )
    recommendations: list[WeakRerunRecommendation] | None = None
    if args.recommend_weak_reruns:
        recommendations = recommend_weak_reruns(
            rows,
            min_holdout_rate=args.min_holdout_rate,
            history_root=args.runs,
        )
    if args.format == "json":
        write_json(
            rows,
            args.limit,
            recommendations=recommendations,
            min_holdout_rate=args.min_holdout_rate,
            include_rerun_command=args.include_rerun_command,
            rerun_root=args.rerun_root,
            rerun_min_smoke_contract_axes=args.rerun_min_smoke_contract_axes,
            rerun_required_runtime_smoke_dimensions=(
                args.rerun_required_runtime_smoke_dimensions
            ),
            rerun_min_holdout_improvement_delta=args.rerun_min_holdout_improvement_delta,
        )
    else:
        write_markdown(rows, args.limit)
    if args.recommend_weak_reruns and args.format == "markdown" and recommendations is not None:
        write_recommendations(
            recommendations,
            args.limit,
            min_holdout_rate=args.min_holdout_rate,
            include_rerun_command=args.include_rerun_command,
            rerun_root=args.rerun_root,
            rerun_min_smoke_contract_axes=args.rerun_min_smoke_contract_axes,
            rerun_required_runtime_smoke_dimensions=(
                args.rerun_required_runtime_smoke_dimensions
            ),
            rerun_min_holdout_improvement_delta=args.rerun_min_holdout_improvement_delta,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
