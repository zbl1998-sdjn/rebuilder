"""Audit aggregate official eval artifacts against recorded baselines."""

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

from core.evaluation.programbench import ProgramBenchEvalParser  # noqa: E402


ACTIONABLE_STATUSES = {"baseline_upgrade", "unrecorded_official"}


@dataclass(frozen=True)
class BaselineCandidate:
    task_id: str
    status: str
    official_score: int
    official_passed: int
    official_total: int
    recorded_score: int | None
    eval_path: Path

    @property
    def delta(self) -> int | None:
        if self.recorded_score is None:
            return None
        return self.official_score - self.recorded_score


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit aggregate official baseline candidates")
    parser.add_argument(
        "--official-eval-root",
        default="runs/programbench_official_eval",
        help="Root containing official *.eval.json aggregate artifacts",
    )
    parser.add_argument(
        "--baseline-root",
        default="baselines/programbench",
        help="Root containing recorded *.baseline.json files",
    )
    parser.add_argument(
        "--programbench-repo",
        default=None,
        help="Optional ProgramBench repo root used for counted-test filtering",
    )
    parser.add_argument(
        "--actionable-only",
        action="store_true",
        help="Only show unrecorded non-zero official results and higher-than-recorded baselines",
    )
    parser.add_argument("--limit", type=positive_int, default=50)
    return parser.parse_args(argv)


def collect_baseline_candidates(
    official_eval_root: Path | str,
    baseline_root: Path | str,
    *,
    programbench_repo: Path | str | None = None,
    actionable_only: bool = False,
) -> list[BaselineCandidate]:
    recorded_scores = discover_recorded_baseline_scores(Path(baseline_root))
    best_by_task: dict[str, BaselineCandidate] = {}
    parser = ProgramBenchEvalParser()
    repo_path = Path(programbench_repo) if programbench_repo is not None else None
    for eval_path in Path(official_eval_root).rglob("*.eval.json"):
        task_id = eval_path.name.removesuffix(".eval.json")
        summary = parser.parse(eval_path, instance_id=task_id, programbench_repo=repo_path)
        row = BaselineCandidate(
            task_id=task_id,
            status=baseline_status(round(summary.score * 100), recorded_scores.get(task_id)),
            official_score=round(summary.score * 100),
            official_passed=summary.passed_tests,
            official_total=summary.total_tests,
            recorded_score=recorded_scores.get(task_id),
            eval_path=eval_path,
        )
        current = best_by_task.get(task_id)
        if current is None or candidate_preferred(row, current):
            best_by_task[task_id] = row
    rows = list(best_by_task.values())
    if actionable_only:
        rows = [row for row in rows if row.status in ACTIONABLE_STATUSES]
    return sorted(rows, key=baseline_candidate_sort_key)


def discover_recorded_baseline_scores(root: Path) -> dict[str, int]:
    scores: dict[str, int] = {}
    if not root.exists():
        return scores
    for path in root.glob("*.baseline.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        task_id = payload.get("instance_id")
        official = payload.get("official") or {}
        if not task_id or not isinstance(official, dict):
            continue
        score = as_int(official.get("score"))
        if score is None:
            continue
        scores[str(task_id)] = score
    return scores


def baseline_status(official_score: int, recorded_score: int | None) -> str:
    if recorded_score is None:
        return "unrecorded_official" if official_score > 0 else "unrecorded_zero"
    if official_score > recorded_score:
        return "baseline_upgrade"
    return "same_or_lower"


def candidate_preferred(row: BaselineCandidate, current: BaselineCandidate) -> bool:
    return (
        row.official_score,
        row.official_passed,
        row.official_total,
        str(row.eval_path),
    ) > (
        current.official_score,
        current.official_passed,
        current.official_total,
        str(current.eval_path),
    )


def baseline_candidate_sort_key(row: BaselineCandidate) -> tuple[int, int, str]:
    status_rank = {"baseline_upgrade": 0, "unrecorded_official": 1}.get(row.status, 2)
    return (status_rank, -row.official_score, row.task_id)


def as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or parsed < 0 or not parsed.is_integer():
        return None
    return int(parsed)


def format_optional_int(value: int | None) -> str:
    return "-" if value is None else str(value)


def write_markdown(rows: list[BaselineCandidate], *, limit: int) -> None:
    selected = rows[:limit]
    print("| rank | task | status | official score | official aggregate | recorded score | delta | eval |")
    print("| ---: | --- | --- | ---: | ---: | ---: | ---: | --- |")
    for index, row in enumerate(selected, start=1):
        print(
            f"| {index} | {row.task_id} | {row.status} | {row.official_score} | "
            f"{row.official_passed}/{row.official_total} | "
            f"{format_optional_int(row.recorded_score)} | {format_optional_int(row.delta)} | {row.eval_path} |"
        )


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    rows = collect_baseline_candidates(
        args.official_eval_root,
        args.baseline_root,
        programbench_repo=args.programbench_repo,
        actionable_only=args.actionable_only,
    )
    write_markdown(rows, limit=args.limit)


if __name__ == "__main__":
    main()
