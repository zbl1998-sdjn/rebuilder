"""Rank completed ProgramBench runs for the next official-eval candidates."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass(frozen=True)
class CandidateRow:
    task_id: str
    status: str
    resolved_rate: float
    holdout_resolved_rate: float | None
    holdout_cases: int
    probes_conducted: int
    iterations_used: int
    static_output_assets_enabled: bool | None
    has_official_eval: bool
    result_path: Path
    modified_at: float


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
    parser.add_argument("--limit", type=int, default=20, help="Maximum rows to print")
    parser.add_argument(
        "--min-holdout-cases",
        type=int,
        default=10,
        help="Minimum holdout cases required for a reliable candidate ranking",
    )
    parser.add_argument(
        "--only-unofficial",
        action="store_true",
        help="Only show tasks without an existing official eval artifact",
    )
    return parser.parse_args(argv)


def collect_candidates(
    runs_root: Path | str,
    official_eval_root: Path | str,
    *,
    baseline_root: Path | str = "baselines/programbench",
    only_unofficial: bool = False,
    min_holdout_cases: int = 10,
) -> list[CandidateRow]:
    official_task_ids = discover_official_eval_task_ids(Path(official_eval_root))
    official_task_ids.update(discover_baseline_task_ids(Path(baseline_root)))
    best_by_task: dict[str, CandidateRow] = {}
    for result_path in Path(runs_root).rglob("result.json"):
        row = read_candidate_row(result_path, official_task_ids)
        if row is None:
            continue
        if only_unofficial and row.has_official_eval:
            continue
        current = best_by_task.get(row.task_id)
        if current is None or candidate_sort_key(row, min_holdout_cases) > candidate_sort_key(current, min_holdout_cases):
            best_by_task[row.task_id] = row
    return sorted(best_by_task.values(), key=lambda row: candidate_sort_key(row, min_holdout_cases), reverse=True)


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
        instance_id = payload.get("instance_id")
        if instance_id:
            task_ids.add(str(instance_id))
    return task_ids


def read_candidate_row(result_path: Path, official_task_ids: set[str]) -> CandidateRow | None:
    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    task_id = payload.get("task_id") or infer_task_id(result_path)
    if not task_id:
        return None
    metadata = payload.get("implementation_metadata") or {}
    return CandidateRow(
        task_id=task_id,
        status=str(payload.get("status", "unknown")),
        resolved_rate=as_float(payload.get("resolved_rate")),
        holdout_resolved_rate=as_optional_float(payload.get("holdout_resolved_rate")),
        holdout_cases=int(payload.get("holdout_cases", 0) or 0),
        probes_conducted=int(payload.get("probes_conducted", 0) or 0),
        iterations_used=int(payload.get("iterations_used", 0) or 0),
        static_output_assets_enabled=as_optional_bool(metadata.get("static_output_assets_enabled")),
        has_official_eval=task_id in official_task_ids,
        result_path=result_path,
        modified_at=result_path.stat().st_mtime,
    )


def infer_task_id(result_path: Path) -> str | None:
    parts = result_path.parts
    if "generated" in parts:
        generated_index = parts.index("generated")
        if generated_index + 1 < len(parts):
            return parts[generated_index + 1]
    return result_path.parent.name or None


def candidate_sort_key(row: CandidateRow, min_holdout_cases: int = 10) -> tuple[int, int, float, float, float]:
    holdout = row.holdout_resolved_rate if row.holdout_resolved_rate is not None else -1.0
    enough_holdout = row.holdout_cases >= min_holdout_cases
    return (
        0 if row.has_official_eval else 1,
        1 if enough_holdout else 0,
        holdout,
        row.resolved_rate,
        row.modified_at,
    )


def as_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def as_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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


def write_markdown(rows: list[CandidateRow], limit: int) -> None:
    selected = rows[: max(0, limit)]
    print("| rank | task | local | holdout | holdout cases | status | probes | repairs | assets | official eval | result |")
    print("| ---: | --- | ---: | ---: | ---: | --- | ---: | ---: | --- | --- | --- |")
    for index, row in enumerate(selected, start=1):
        print(
            f"| {index} | {row.task_id} | {format_rate(row.resolved_rate)} | "
            f"{format_rate(row.holdout_resolved_rate)} | {row.holdout_cases} | {row.status} | "
            f"{row.probes_conducted} | {row.iterations_used} | "
            f"{format_bool(row.static_output_assets_enabled)} | "
            f"{format_bool(row.has_official_eval)} | {row.result_path} |"
        )


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    rows = collect_candidates(
        args.runs,
        args.official_eval_root,
        baseline_root=args.baseline_root,
        only_unofficial=args.only_unofficial,
        min_holdout_cases=args.min_holdout_cases,
    )
    write_markdown(rows, args.limit)


if __name__ == "__main__":
    main()
