"""Run official closed-loop strategy variants for one ProgramBench instance."""

from __future__ import annotations

import argparse
import math
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.submission import parse_runtime_smoke_dimensions  # noqa: E402
from scripts.audit_generalization_risk import DEFAULT_MAX_LOCAL_HOLDOUT_GAP  # noqa: E402
from scripts.run_official_closed_loop import is_local_llm_config  # noqa: E402

DEFAULT_VARIANTS = ("baseline_no_adaptive", "adaptive_profile", "adaptive_deep")
HOLDOUT_GATE_EXIT_CODE = 3


class CommandFailure(RuntimeError):
    """Closed-loop child command failed with a process exit code."""

    def __init__(self, returncode: int, command: list[str]):
        self.returncode = returncode
        self.command = command
        super().__init__(f"Command failed ({returncode}): {' '.join(command)}")


def non_negative_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative and finite")
    return parsed


def rate_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0 or parsed > 1:
        raise argparse.ArgumentTypeError("must be a finite rate between 0 and 1")
    return parsed


def positive_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive and finite")
    return parsed


def non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run official ProgramBench strategy ablations")
    parser.add_argument("instance_id", help="ProgramBench instance id")
    parser.add_argument(
        "--catalog",
        default="examples/programbench_samples/samples_full_20260512.json",
        help="Path to ProgramBench sample metadata JSON",
    )
    parser.add_argument("--runs", default="runs/official_strategy_ablation", help="Ablation run root")
    parser.add_argument("--config", default="config/settings.yaml", help="ReBuilder config path")
    parser.add_argument(
        "--strategy-registry",
        default="runs/programbench_strategy_registry.jsonl",
        help="Aggregate-only JSONL registry shared by all variants",
    )
    parser.add_argument(
        "--variants",
        nargs="+",
        default=list(DEFAULT_VARIANTS),
        help="Strategy variant ids to run in order",
    )
    parser.add_argument("--eval-run-prefix", default="strategy_ablation", help="Official eval run-name prefix")
    parser.add_argument(
        "--official-eval-root",
        default="runs/programbench_official_eval",
        help="Root for official eval submission/eval artifacts",
    )
    parser.add_argument("--probe-iterations", type=non_negative_int, default=10)
    parser.add_argument("--min-probe-samples", type=non_negative_int, default=50)
    parser.add_argument("--max-repairs", type=non_negative_int, default=3)
    parser.add_argument("--near-miss-holdout-rate", type=rate_float, default=0.75)
    parser.add_argument("--near-miss-max-repairs", type=non_negative_int, default=5)
    parser.add_argument("--replacement-executor", choices=["local", "wsl"], default="wsl")
    parser.add_argument("--static-output-assets", choices=["config", "enabled", "disabled"], default="disabled")
    parser.add_argument("--min-holdout-rate", type=rate_float, default=0.8)
    parser.add_argument("--min-holdout-cases", type=non_negative_int, default=10)
    parser.add_argument("--min-smoke-contract-axes", type=non_negative_int, default=0)
    parser.add_argument(
        "--require-runtime-smoke-dimensions",
        type=parse_runtime_smoke_dimensions,
        default=(),
        dest="required_runtime_smoke_dimensions",
    )
    parser.add_argument(
        "--adaptive-probe-exclude-domain",
        action="append",
        default=[],
        help=(
            "Exclude a task-profile domain from deterministic adaptive probes in "
            "child ReBuilder runs; repeatable."
        ),
    )
    parser.add_argument("--require-holdout-improvement", action="store_true")
    parser.add_argument("--min-holdout-improvement-delta", type=non_negative_float, default=0.0)
    parser.add_argument("--holdout-history-root", default="runs")
    parser.add_argument(
        "--holdout-history-exclude-root",
        action="append",
        dest="holdout_history_exclude_roots",
        default=[],
        help="Additional historical result root to exclude from every variant's improvement audit",
    )
    parser.add_argument("--max-generalization-risk", choices=["low", "medium", "high"], default=None)
    parser.add_argument(
        "--max-local-holdout-gap",
        type=rate_float,
        default=DEFAULT_MAX_LOCAL_HOLDOUT_GAP,
        help="Maximum local-vs-holdout aggregate gap forwarded to child generalization risk gates",
    )
    parser.add_argument("--generalization-risk-root", default="runs")
    parser.add_argument("--baseline-root", default="baselines/programbench")
    parser.add_argument("--workers", type=positive_int, default=1)
    parser.add_argument("--branch-workers", type=positive_int, default=1)
    parser.add_argument("--docker-cpus", type=positive_int, default=4)
    parser.add_argument("--branch-retries", type=non_negative_int, default=1)
    parser.add_argument("--programbench-python", default="py")
    parser.add_argument("--programbench-python-version", default="3.14")
    parser.add_argument("--model", default="glm-5.1")
    parser.add_argument("--baseline-output", default="baselines/programbench")
    parser.add_argument("--pull", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--skip-official-eval", action="store_true")
    parser.add_argument(
        "--ack-external-llm-docker",
        action="store_true",
        help=(
            "Required unless --dry-run. Acknowledge that child closed-loop runs may "
            "call external LLM APIs and Docker; --skip-official-eval only disables official eval."
        ),
    )
    parser.add_argument(
        "--ack-local-llm-docker",
        action="store_true",
        help=(
            "Required alternative unless --dry-run for file_bridge or loopback local_openai configs. "
            "Acknowledge local LLM handoff plus Docker, without external LLM APIs."
        ),
    )
    parser.add_argument("--keep-going", action="store_true", help="Continue after a variant fails")
    parser.add_argument("--dry-run", action="store_true", help="Print child closed-loop commands without executing them")
    parser.add_argument(
        "--command-timeout-seconds",
        type=positive_float,
        default=21600.0,
        help="Timeout per closed-loop variant command",
    )
    return parser.parse_args(argv)


def build_closed_loop_command(args: argparse.Namespace, variant: str) -> list[str]:
    variant_run_root = Path(args.runs) / variant
    eval_run_name = f"{args.eval_run_prefix}_{variant}"
    command = [
        sys.executable,
        "scripts/run_official_closed_loop.py",
        args.instance_id,
        "--catalog",
        args.catalog,
        "--runs",
        variant_run_root.as_posix(),
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
        "--official-eval-root",
        args.official_eval_root,
        "--eval-run-name",
        eval_run_name,
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
        "--baseline-output",
        args.baseline_output,
        "--strategy-registry",
        args.strategy_registry,
    ]
    if args.pull:
        command.append("--pull")
    if args.force:
        command.append("--force")
    if args.skip_official_eval:
        command.append("--skip-official-eval")
    if args.ack_external_llm_docker:
        command.append("--ack-external-llm-docker")
    elif args.ack_local_llm_docker:
        command.append("--ack-local-llm-docker")
    for domain in getattr(args, "adaptive_probe_exclude_domain", []) or []:
        command.extend(["--adaptive-probe-exclude-domain", str(domain)])
    if args.min_smoke_contract_axes > 0:
        command.extend(["--min-smoke-contract-axes", str(args.min_smoke_contract_axes)])
    if args.required_runtime_smoke_dimensions:
        command.extend(
            [
                "--require-runtime-smoke-dimensions",
                ",".join(args.required_runtime_smoke_dimensions),
            ]
        )
    if args.max_generalization_risk is not None:
        command.extend(
            [
                "--max-generalization-risk",
                args.max_generalization_risk,
                "--generalization-risk-root",
                args.generalization_risk_root,
                "--baseline-root",
                args.baseline_root,
                "--max-local-holdout-gap",
                str(args.max_local_holdout_gap),
            ]
        )
    if args.require_holdout_improvement:
        command.extend(
            [
                "--require-holdout-improvement",
                "--min-holdout-improvement-delta",
                str(args.min_holdout_improvement_delta),
                "--holdout-history-root",
                args.holdout_history_root,
            ]
        )
        for exclude_root in holdout_history_exclude_roots_for_child(args):
            command.extend(["--holdout-history-exclude-root", exclude_root])
    command.extend(["--strategy-variant", variant])
    return command


def build_subprocess_env() -> dict[str, str]:
    """Force UTF-8 output for child Python CLIs on Windows redirected consoles."""
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env.setdefault("NO_COLOR", "1")
    return env


def history_root_contains_current_ablation(args: argparse.Namespace) -> bool:
    if not args.require_holdout_improvement:
        return False
    history_root = Path(args.holdout_history_root).resolve()
    run_root = Path(args.runs).resolve()
    try:
        run_root.relative_to(history_root)
    except ValueError:
        return False
    return True


def holdout_history_exclude_roots_for_child(args: argparse.Namespace) -> list[str]:
    roots = [str(args.runs), *list(getattr(args, "holdout_history_exclude_roots", []))]
    unique_roots: list[str] = []
    for root in roots:
        if root not in unique_roots:
            unique_roots.append(root)
    return unique_roots


def warn_if_history_root_contains_current_ablation(args: argparse.Namespace) -> None:
    if not history_root_contains_current_ablation(args):
        return
    print(
        "WARNING: --holdout-history-root contains the current ablation --runs directory; "
        "child variants will pass --holdout-history-exclude-root for the parent ablation root. "
        "Use extra --holdout-history-exclude-root flags for any other in-flight experiment roots.",
        file=sys.stderr,
        flush=True,
    )


def run_command(command: list[str], *, timeout_seconds: float) -> None:
    print("+ " + " ".join(command), flush=True)
    result = subprocess.run(
        command,
        text=True,
        check=False,
        timeout=timeout_seconds,
        env=build_subprocess_env(),
    )
    if result.returncode != 0:
        raise CommandFailure(result.returncode, command)


def run_variant_commands(
    args: argparse.Namespace,
    *,
    runner: Callable[[list[str]], None],
) -> list[tuple[str, str]]:
    failures: list[tuple[str, str]] = []
    for variant in args.variants:
        command = build_closed_loop_command(args, variant)
        if args.dry_run:
            print(f"DRY-RUN strategy variant: {variant}", flush=True)
            print("+ " + " ".join(command), flush=True)
            continue
        print(f"Running strategy variant: {variant}", flush=True)
        try:
            runner(command)
        except CommandFailure as exc:
            if exc.returncode == HOLDOUT_GATE_EXIT_CODE:
                print(f"Variant skipped by holdout gate: {variant}: {exc}", flush=True)
                continue
            if not args.keep_going:
                raise
            failures.append((variant, str(exc)))
            print(f"Variant failed: {variant}: {exc}", flush=True)
        except RuntimeError as exc:
            if not args.keep_going:
                raise
            failures.append((variant, str(exc)))
            print(f"Variant failed: {variant}: {exc}", flush=True)
    return failures


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if not args.dry_run and not (
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
            raise SystemExit(2)
        print(
            "ERROR: execution requires --ack-external-llm-docker because child runs "
            "may call external LLM APIs and Docker. For file_bridge or loopback local_openai "
            "configs, pass --ack-local-llm-docker instead.",
            file=sys.stderr,
            flush=True,
        )
        raise SystemExit(2)
    warn_if_history_root_contains_current_ablation(args)
    failures = run_variant_commands(
        args,
        runner=lambda command: run_command(command, timeout_seconds=args.command_timeout_seconds),
    )
    if failures:
        failed = ", ".join(variant for variant, _message in failures)
        raise SystemExit(f"Strategy variants failed: {failed}")


if __name__ == "__main__":
    main()
