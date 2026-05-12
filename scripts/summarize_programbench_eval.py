"""Summarize ProgramBench eval JSON."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.evaluation import ProgramBenchEvalParser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize ProgramBench eval JSON")
    parser.add_argument("eval_json", help="Path to <instance>.eval.json")
    parser.add_argument(
        "--instance-id",
        default=None,
        help="ProgramBench instance id for counted-test filtering",
    )
    parser.add_argument(
        "--programbench-repo",
        default=None,
        help="Optional ProgramBench repository path containing task tests.json files",
    )
    return parser.parse_args(argv)


def print_summary(prefix: str, summary) -> None:
    label = f"{prefix}_" if prefix else ""
    print(f"{label}tests={summary.total_tests}")
    print(f"{label}passed={summary.passed_tests}")
    print(f"{label}pass_rate={summary.pass_rate:.4f}")
    print(f"{label}score={round(summary.score * 100)}")
    print(f"{label}fully_resolved={summary.fully_resolved}")
    print(f"{label}almost_resolved={summary.almost_resolved}")
    if summary.error_code:
        print(f"{label}error_code={summary.error_code}")


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    parser = ProgramBenchEvalParser()
    raw_summary = parser.parse(args.eval_json)
    if not args.instance_id:
        print_summary("", raw_summary)
        return

    counted_summary = parser.parse(
        args.eval_json,
        instance_id=args.instance_id,
        programbench_repo=args.programbench_repo,
    )
    print_summary("raw", raw_summary)
    print_summary("counted", counted_summary)


if __name__ == "__main__":
    main()
