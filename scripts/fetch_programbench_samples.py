"""Fetch official ProgramBench sample metadata.

This script records Docker image metadata only. It does not download hidden tests,
inspect source code, or pull task images.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.programbench.samples import fetch_programbench_samples  # noqa: E402


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("limit must be a positive integer")
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch ProgramBench sample metadata")
    parser.add_argument("--limit", type=positive_int, default=5, help="Number of samples to fetch")
    parser.add_argument(
        "--output",
        default="examples/programbench_samples/samples.json",
        help="Path to write sample metadata JSON",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    samples = fetch_programbench_samples(limit=args.limit)
    if args.limit > 0 and not samples:
        raise SystemExit("No valid ProgramBench sample records were fetched; not writing an empty catalog.")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps([sample.model_dump() for sample in samples], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Wrote {len(samples)} ProgramBench sample records to {output}")


if __name__ == "__main__":
    main()
