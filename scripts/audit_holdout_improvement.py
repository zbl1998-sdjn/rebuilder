"""Audit whether one local result improves a task's reliable holdout best."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.summarize_holdout_trends import HoldoutRun, read_holdout_run  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit aggregate holdout improvement for one result.json")
    parser.add_argument("result", help="Path to a ReBuilder result.json")
    parser.add_argument("--runs", default="runs", help="Root directory containing historical result.json files")
    parser.add_argument("--min-holdout-cases", type=non_negative_int, default=10)
    parser.add_argument(
        "--min-delta",
        type=non_negative_float,
        default=0.0,
        help="Minimum positive holdout-rate delta over the previous best",
    )
    parser.add_argument(
        "--exclude-root",
        action="append",
        dest="exclude_roots",
        default=[],
        help="Ignore historical result.json files under this root; may be repeated",
    )
    return parser.parse_args(argv)


def non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be non-negative")
    return parsed


def non_negative_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError("value must be non-negative and finite")
    return parsed


def audit_holdout_improvement(
    result_path: Path | str,
    *,
    runs_root: Path | str = "runs",
    min_holdout_cases: int = 10,
    min_delta: float = 0.0,
    exclude_roots: Iterable[Path | str] = (),
) -> dict[str, Any]:
    validate_thresholds(min_holdout_cases=min_holdout_cases, min_delta=min_delta)
    current_path = Path(result_path)
    exclude_root_paths = normalize_roots(exclude_roots)
    current = read_holdout_run(current_path)
    if current is None:
        return base_audit(
            current_path,
            improved=False,
            reason="missing_current_holdout",
            min_holdout_cases=min_holdout_cases,
            min_delta=min_delta,
            exclude_roots=exclude_root_paths,
        )
    audit = base_audit(
        current_path,
        improved=False,
        reason="not_improved",
        min_holdout_cases=min_holdout_cases,
        min_delta=min_delta,
        current=current,
        exclude_roots=exclude_root_paths,
    )
    if current.holdout_cases < min_holdout_cases:
        audit["reason"] = "too_few_current_holdout_cases"
        return audit

    previous = [
        run
        for run in collect_reliable_task_runs(
            runs_root,
            task_id=current.task_id,
            min_holdout_cases=min_holdout_cases,
            exclude_roots=exclude_root_paths,
        )
        if not same_path(run.result_path, current_path)
    ]
    if not previous:
        audit["reason"] = "no_prior_reliable"
        return audit

    best = max(
        previous,
        key=lambda row: (
            row.holdout_resolved_rate,
            row.holdout_cases,
            row.modified_at,
            str(row.result_path),
        ),
    )
    delta = current.holdout_resolved_rate - best.holdout_resolved_rate
    audit.update(
        {
            "best_previous_holdout_resolved_rate": best.holdout_resolved_rate,
            "best_previous_holdout_cases": best.holdout_cases,
            "best_previous_result_path": str(best.result_path),
            "delta_from_best_previous": delta,
        }
    )
    if delta > min_delta:
        audit["improved"] = True
        audit["reason"] = "improved"
    elif delta > 0:
        audit["reason"] = "delta_below_min"
    return audit


def validate_thresholds(*, min_holdout_cases: int, min_delta: float) -> None:
    if not math.isfinite(min_delta) or min_delta < 0:
        raise ValueError("min_delta must be non-negative and finite")
    validate_non_negative_int_threshold("min_holdout_cases", min_holdout_cases)


def validate_non_negative_int_threshold(name: str, value: int) -> None:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a non-negative integer") from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise ValueError(f"{name} must be non-negative")
    if not parsed.is_integer():
        raise ValueError(f"{name} must be a non-negative integer")


def collect_reliable_task_runs(
    runs_root: Path | str,
    *,
    task_id: str,
    min_holdout_cases: int,
    exclude_roots: Iterable[Path] = (),
) -> list[HoldoutRun]:
    rows: list[HoldoutRun] = []
    for result_path in Path(runs_root).rglob("result.json"):
        if path_under_any_root(result_path, exclude_roots):
            continue
        run = read_holdout_run(result_path)
        if run is None:
            continue
        if run.task_id != task_id:
            continue
        if run.holdout_cases < min_holdout_cases:
            continue
        rows.append(run)
    return rows


def base_audit(
    result_path: Path,
    *,
    improved: bool,
    reason: str,
    min_holdout_cases: int,
    min_delta: float,
    current: HoldoutRun | None = None,
    exclude_roots: Iterable[Path] = (),
) -> dict[str, Any]:
    return {
        "improved": improved,
        "reason": reason,
        "task_id": current.task_id if current else None,
        "current_holdout_resolved_rate": current.holdout_resolved_rate if current else None,
        "current_holdout_cases": current.holdout_cases if current else None,
        "best_previous_holdout_resolved_rate": None,
        "best_previous_holdout_cases": None,
        "best_previous_result_path": None,
        "delta_from_best_previous": None,
        "min_holdout_cases": min_holdout_cases,
        "min_delta": min_delta,
        "result_path": str(result_path),
        "excluded_roots": [str(root) for root in exclude_roots],
    }


def same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return left == right


def normalize_roots(roots: Iterable[Path | str]) -> list[Path]:
    return [Path(root) for root in roots]


def path_under_any_root(path: Path, roots: Iterable[Path]) -> bool:
    return any(path_under_root(path, root) for root in roots)


def path_under_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    audit = audit_holdout_improvement(
        args.result,
        runs_root=args.runs,
        min_holdout_cases=args.min_holdout_cases,
        min_delta=args.min_delta,
        exclude_roots=args.exclude_roots,
    )
    print(json.dumps(audit, indent=2, sort_keys=True))
    return 0 if audit["improved"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
