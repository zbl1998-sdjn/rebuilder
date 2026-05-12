"""Package generated code as ProgramBench submission."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.submission import HoldoutGateError, SubmissionHoldoutGate, SubmissionPackager


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Package generated code as ProgramBench submission")
    parser.add_argument("instance_id", help="ProgramBench instance id")
    parser.add_argument("--generated", required=True, help="Generated code directory")
    parser.add_argument("--output", default="submissions", help="Submission run root")
    parser.add_argument(
        "--result",
        required=True,
        help="Path to ReBuilder result.json containing aggregate internal holdout metrics",
    )
    parser.add_argument(
        "--min-holdout-rate",
        type=float,
        default=0.8,
        help="Minimum aggregate internal holdout resolved rate required for packaging",
    )
    parser.add_argument(
        "--min-holdout-cases",
        type=int,
        default=1,
        help="Minimum number of aggregate internal holdout cases required for packaging",
    )
    parser.add_argument(
        "--allow-unverified",
        action="store_true",
        help="Bypass the internal holdout gate for local debugging; do not use for official eval",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.allow_unverified:
        try:
            SubmissionHoldoutGate(min_rate=args.min_holdout_rate, min_cases=args.min_holdout_cases).verify(args.result)
        except HoldoutGateError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(2)
    archive = SubmissionPackager().package(
        generated_path=Path(args.generated),
        output_root=Path(args.output),
        instance_id=args.instance_id,
    )
    print(archive)


if __name__ == "__main__":
    main()
