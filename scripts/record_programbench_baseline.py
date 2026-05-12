"""Record aggregate ProgramBench baseline metrics."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.experiments import BaselineRecorder


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record a ProgramBench aggregate baseline")
    parser.add_argument("instance_id", help="ProgramBench instance id")
    parser.add_argument("--local-result", required=True, help="Path to ReBuilder result.json")
    parser.add_argument("--official-eval", required=True, help="Path to official eval JSON")
    parser.add_argument("--submission", required=True, help="Path to submission.tar.gz")
    parser.add_argument("--output", default="baselines/programbench", help="Baseline output directory")
    parser.add_argument("--model", required=True, help="Model name used for the run")
    parser.add_argument("--config", required=True, help="Config file used for the run")
    parser.add_argument("--notes", default="", help="Short human-readable baseline note")
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    path = BaselineRecorder().record(
        instance_id=args.instance_id,
        local_result_path=Path(args.local_result),
        official_eval_path=Path(args.official_eval),
        submission_archive_path=Path(args.submission),
        output_dir=Path(args.output),
        model=args.model,
        config_path=args.config,
        notes=args.notes,
    )
    print(path)


if __name__ == "__main__":
    main()
