"""Summarize ProgramBench eval JSON."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.evaluation import ProgramBenchEvalParser


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize ProgramBench eval JSON")
    parser.add_argument("eval_json", help="Path to <instance>.eval.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = ProgramBenchEvalParser().parse(args.eval_json)
    print(f"tests={summary.total_tests}")
    print(f"passed={summary.passed_tests}")
    print(f"pass_rate={summary.pass_rate:.4f}")
    print(f"fully_resolved={summary.fully_resolved}")
    print(f"almost_resolved={summary.almost_resolved}")
    if summary.error_code:
        print(f"error_code={summary.error_code}")


if __name__ == "__main__":
    main()
