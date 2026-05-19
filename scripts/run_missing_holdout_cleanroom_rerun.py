"""Run a local-only cleanroom rerun to build reliable holdout signal."""

from __future__ import annotations

import argparse
import math
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.submission import parse_runtime_smoke_dimensions  # noqa: E402
from scripts.run_official_closed_loop import is_local_llm_config  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a ProgramBench missing-holdout cleanroom rerun with official eval disabled"
    )
    parser.add_argument("instance_id", help="ProgramBench instance id")
    parser.add_argument(
        "--catalog",
        default="examples/programbench_samples/resolved_push_candidates_20260512.json",
        help="Path to ProgramBench sample metadata JSON",
    )
    parser.add_argument("--runs", default="runs/missing_holdout_cleanroom_rerun", help="Local rerun root")
    parser.add_argument("--config", default="config/settings.yaml", help="ReBuilder config path")
    parser.add_argument("--probe-iterations", type=_non_negative_int, default=10)
    parser.add_argument("--min-probe-samples", type=_non_negative_int, default=50)
    parser.add_argument("--max-repairs", type=_non_negative_int, default=3)
    parser.add_argument("--near-miss-holdout-rate", type=_rate_float, default=0.75)
    parser.add_argument("--near-miss-max-repairs", type=_non_negative_int, default=5)
    parser.add_argument("--replacement-executor", choices=["local", "wsl"], default="wsl")
    parser.add_argument("--static-output-assets", choices=["config", "enabled", "disabled"], default="disabled")
    parser.add_argument("--min-holdout-rate", type=_rate_float, default=0.8)
    parser.add_argument("--min-holdout-cases", type=_non_negative_int, default=10)
    parser.add_argument("--min-smoke-contract-axes", type=_non_negative_int, default=1)
    parser.add_argument(
        "--require-runtime-smoke-dimensions",
        type=parse_runtime_smoke_dimensions,
        default=(),
        dest="required_runtime_smoke_dimensions",
    )
    parser.add_argument("--workers", type=_positive_int, default=1)
    parser.add_argument("--branch-workers", type=_positive_int, default=1)
    parser.add_argument("--docker-cpus", type=_positive_int, default=4)
    parser.add_argument("--branch-retries", type=_non_negative_int, default=1)
    parser.add_argument("--programbench-python", default="py")
    parser.add_argument("--programbench-python-version", default="3.14")
    parser.add_argument("--model", default="glm-5.1")
    parser.add_argument("--strategy-registry", default=None)
    parser.add_argument("--strategy-variant", default=None)
    parser.add_argument("--pull", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually run the closed-loop command. Without this flag the wrapper only prints a dry-run command.",
    )
    parser.add_argument(
        "--ack-external-llm-docker",
        action="store_true",
        help=(
            "Required with --execute. Acknowledge that the closed-loop run may call "
            "external LLM APIs and Docker while official eval remains disabled."
        ),
    )
    parser.add_argument(
        "--ack-local-llm-docker",
        action="store_true",
        help=(
            "Required alternative with --execute for file_bridge or loopback local_openai configs. "
            "Acknowledge local LLM handoff plus Docker, without external LLM APIs."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the closed-loop command without running it. This is the default behavior.",
    )
    parser.add_argument(
        "--command-timeout-seconds",
        type=_positive_float,
        default=21600.0,
        help="Timeout for the closed-loop command",
    )
    return parser.parse_args(argv)


def _non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be non-negative")
    return parsed


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def _positive_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive and finite")
    return parsed


def _rate_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0 or parsed > 1:
        raise argparse.ArgumentTypeError("value must be a finite rate between 0 and 1")
    return parsed


def build_closed_loop_command(args: argparse.Namespace) -> list[str]:
    command = [
        sys.executable,
        "scripts/run_official_closed_loop.py",
        args.instance_id,
        "--catalog",
        args.catalog,
        "--runs",
        args.runs,
        "--config",
        args.config,
        "--probe-iterations",
        str(args.probe_iterations),
        "--min-probe-samples",
        str(args.min_probe_samples),
        "--max-repairs",
        str(args.max_repairs),
        "--near-miss-holdout-rate",
        str(args.near_miss_holdout_rate),
        "--near-miss-max-repairs",
        str(args.near_miss_max_repairs),
        "--replacement-executor",
        args.replacement_executor,
        "--static-output-assets",
        args.static_output_assets,
        "--min-holdout-rate",
        str(args.min_holdout_rate),
        "--min-holdout-cases",
        str(args.min_holdout_cases),
        "--workers",
        str(args.workers),
        "--branch-workers",
        str(args.branch_workers),
        "--docker-cpus",
        str(args.docker_cpus),
        "--branch-retries",
        str(args.branch_retries),
        "--programbench-python",
        args.programbench_python,
        "--programbench-python-version",
        args.programbench_python_version,
        "--model",
        args.model,
        "--skip-official-eval",
    ]
    if args.strategy_registry:
        command.extend(["--strategy-registry", args.strategy_registry])
    if args.strategy_variant:
        command.extend(["--strategy-variant", args.strategy_variant])
    if args.min_smoke_contract_axes > 0:
        command.extend(["--min-smoke-contract-axes", str(args.min_smoke_contract_axes)])
    if args.required_runtime_smoke_dimensions:
        command.extend(
            [
                "--require-runtime-smoke-dimensions",
                ",".join(args.required_runtime_smoke_dimensions),
            ]
        )
    if args.pull:
        command.append("--pull")
    if args.force:
        command.append("--force")
    if args.execute and not getattr(args, "dry_run", False):
        if args.ack_external_llm_docker:
            command.append("--ack-external-llm-docker")
        elif args.ack_local_llm_docker:
            command.append("--ack-local-llm-docker")
    return command


def build_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env.setdefault("NO_COLOR", "1")
    return env


def run_command(command: list[str], *, timeout_seconds: float) -> int:
    print("+ " + " ".join(command), flush=True)
    return subprocess.run(
        command,
        text=True,
        check=False,
        timeout=timeout_seconds,
        env=build_subprocess_env(),
    ).returncode


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    command = build_closed_loop_command(args)
    if args.dry_run or not args.execute:
        print(" ".join(command))
        return 0
    if not (
        args.ack_external_llm_docker
        or (args.ack_local_llm_docker and is_local_llm_config(args.config))
    ):
        if args.ack_local_llm_docker:
            print(
                "ERROR: local LLM ack --ack-local-llm-docker is only valid for file_bridge or "
                "loopback local_openai configs; use --ack-external-llm-docker for external providers.",
                file=sys.stderr,
                flush=True,
            )
            return 2
        print(
            "ERROR: --execute requires --ack-external-llm-docker because the run may "
            "call external LLM APIs and Docker. For file_bridge or loopback local_openai "
            "configs, pass --ack-local-llm-docker instead.",
            file=sys.stderr,
            flush=True,
        )
        return 2
    return run_command(command, timeout_seconds=args.command_timeout_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
