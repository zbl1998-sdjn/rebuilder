"""Package generated code as ProgramBench submission."""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.submission import (  # noqa: E402
    HoldoutGateError,
    SubmissionHoldoutGate,
    SubmissionPackager,
    parse_runtime_smoke_dimensions,
)
from scripts.audit_generalization_risk import RISK_ORDER, collect_generalization_risks  # noqa: E402
from scripts.audit_holdout_improvement import audit_holdout_improvement  # noqa: E402


def non_negative_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative and finite")
    return parsed


def rate_float(value: str) -> float:
    parsed = non_negative_float(value)
    if parsed > 1:
        raise argparse.ArgumentTypeError("must be between 0 and 1")
    return parsed


def non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


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
        type=rate_float,
        default=0.8,
        help="Minimum aggregate internal holdout resolved rate required for packaging",
    )
    parser.add_argument(
        "--min-holdout-cases",
        type=non_negative_int,
        default=1,
        help="Minimum number of aggregate internal holdout cases required for packaging",
    )
    parser.add_argument(
        "--min-smoke-contract-axes",
        type=non_negative_int,
        default=0,
        help="Optional minimum local smoke-contract axes required for packaging",
    )
    parser.add_argument(
        "--require-runtime-smoke-dimensions",
        type=parse_runtime_smoke_dimensions,
        default=(),
        help="Optional comma-separated runtime-smoke input dimensions required for packaging",
    )
    parser.add_argument(
        "--require-holdout-improvement",
        action="store_true",
        help="Require this aggregate holdout result to beat the previous reliable local best",
    )
    parser.add_argument(
        "--holdout-history-root",
        default="runs",
        help="Root directory containing historical result.json files for improvement checks",
    )
    parser.add_argument(
        "--min-holdout-improvement-delta",
        type=non_negative_float,
        default=0.0,
        help="Minimum positive holdout-rate delta over the previous reliable best",
    )
    parser.add_argument(
        "--max-generalization-risk",
        choices=["low", "medium", "high"],
        default=None,
        help="Optional aggregate-only generalization risk ceiling required before packaging",
    )
    parser.add_argument(
        "--generalization-risk-root",
        default="runs",
        help="Root directory containing historical result.json files for generalization risk checks",
    )
    parser.add_argument(
        "--baseline-root",
        default="baselines/programbench",
        help="Root directory containing recorded *.baseline.json files for generalization risk checks",
    )
    parser.add_argument(
        "--official-eval-root",
        default="runs/programbench_official_eval",
        help="Root directory containing official *.eval.json files for generalization risk checks",
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
            SubmissionHoldoutGate(
                min_rate=args.min_holdout_rate,
                min_cases=args.min_holdout_cases,
                min_smoke_contract_axes=args.min_smoke_contract_axes,
                required_runtime_smoke_dimensions=args.require_runtime_smoke_dimensions,
            ).verify(args.result)
            if args.require_holdout_improvement:
                improvement = audit_holdout_improvement(
                    args.result,
                    runs_root=args.holdout_history_root,
                    min_holdout_cases=args.min_holdout_cases,
                    min_delta=args.min_holdout_improvement_delta,
                )
                if not improvement["improved"]:
                    print(
                        "ERROR: holdout improvement required before packaging "
                        f"(reason={improvement['reason']}).",
                        file=sys.stderr,
                    )
                    sys.exit(2)
            if args.max_generalization_risk is not None:
                risk = find_generalization_risk_for_task(
                    args.instance_id,
                    runs_root=args.generalization_risk_root,
                    baseline_root=args.baseline_root,
                    official_eval_root=args.official_eval_root,
                    min_holdout_rate=args.min_holdout_rate,
                    min_holdout_cases=args.min_holdout_cases,
                )
                if risk is None:
                    print(
                        "ERROR: generalization risk check required before packaging "
                        f"(reason=missing_risk_row, task={args.instance_id}).",
                        file=sys.stderr,
                    )
                    sys.exit(2)
                if RISK_ORDER[risk.risk_level] > RISK_ORDER[args.max_generalization_risk]:
                    print(
                        "ERROR: generalization risk too high before packaging "
                        f"(task={risk.task_id}, risk={risk.risk_level}, reason={risk.risk_reason}).",
                        file=sys.stderr,
                    )
                    sys.exit(2)
        except HoldoutGateError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(2)
    archive = SubmissionPackager().package(
        generated_path=Path(args.generated),
        output_root=Path(args.output),
        instance_id=args.instance_id,
    )
    print(archive)


def find_generalization_risk_for_task(
    task_id: str,
    *,
    runs_root: str,
    baseline_root: str,
    official_eval_root: str,
    min_holdout_rate: float,
    min_holdout_cases: int,
):
    for risk in collect_generalization_risks(
        runs_root,
        baseline_root,
        official_eval_root=official_eval_root,
        min_holdout_rate=min_holdout_rate,
        min_holdout_cases=min_holdout_cases,
    ):
        if risk.task_id == task_id:
            return risk
    return None


if __name__ == "__main__":
    main()
