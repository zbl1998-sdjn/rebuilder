"""Run ReBuilder, gate by holdout, then run official ProgramBench eval."""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.evaluation import ProgramBenchEvalParser  # noqa: E402
from core.experiments import (  # noqa: E402
    AggregateFeedback,
    BaselineRecorder,
    ExperimentRegistry,
    ExperimentRun,
    StrategyBandit,
    StrategyVariant,
)
from core.programbench.catalog import load_sample_catalog, select_sample  # noqa: E402
from core.submission import parse_runtime_smoke_dimensions, runtime_smoke_metadata  # noqa: E402
from llm_clients.factory import load_config  # noqa: E402
from scripts.audit_holdout_improvement import audit_holdout_improvement  # noqa: E402

AssetMode = Literal["config", "enabled", "disabled"]


@dataclass(frozen=True)
class ClosedLoopPaths:
    session_root: Path
    workspace: Path
    output_root: Path
    generated: Path
    result: Path
    submission_root: Path
    submission: Path
    eval_json: Path


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
    parser = argparse.ArgumentParser(description="Run a gated official ProgramBench closed loop")
    parser.add_argument("instance_id", help="ProgramBench instance id")
    parser.add_argument(
        "--catalog",
        default="examples/programbench_samples/samples_full_20260512.json",
        help="Path to ProgramBench sample metadata JSON",
    )
    parser.add_argument("--runs", default="runs/closed_loop_official", help="Closed-loop run root")
    parser.add_argument("--config", default="config/settings.yaml", help="ReBuilder config path")
    parser.add_argument(
        "--probe-iterations",
        type=non_negative_int,
        default=10,
        help="ReBuilder LLM probe planning iterations; deterministic supplemental probes fill --min-probe-samples",
    )
    parser.add_argument(
        "--min-probe-samples",
        type=non_negative_int,
        default=50,
        help="Minimum ReBuilder behavior samples before implementation; default supports the holdout case gate",
    )
    parser.add_argument("--max-repairs", type=non_negative_int, default=3, help="ReBuilder repair iterations")
    parser.add_argument(
        "--near-miss-holdout-rate",
        type=rate_float,
        default=0.75,
        help="Holdout rate that triggers one deeper local repair retry before giving up",
    )
    parser.add_argument(
        "--near-miss-max-repairs",
        type=non_negative_int,
        default=5,
        help="Repair iterations for the near-miss retry; ignored unless higher than --max-repairs",
    )
    parser.add_argument(
        "--replacement-executor",
        choices=["local", "wsl"],
        default="wsl",
        help="Replacement executor for local differential testing",
    )
    parser.add_argument(
        "--static-output-assets",
        choices=["config", "enabled", "disabled"],
        default="disabled",
        help="Static output asset mode",
    )
    parser.add_argument(
        "--adaptive-probes",
        choices=["config", "enabled", "disabled"],
        default="config",
        help="Adaptive task-profile probe mode",
    )
    parser.add_argument(
        "--min-holdout-rate",
        type=rate_float,
        default=0.8,
        help="Minimum holdout rate before official eval",
    )
    parser.add_argument(
        "--min-holdout-cases",
        type=non_negative_int,
        default=10,
        help="Minimum internal holdout cases before official eval",
    )
    parser.add_argument(
        "--min-smoke-contract-axes",
        type=non_negative_int,
        default=0,
        help="Optional minimum local smoke-contract axes before packaging or official eval",
    )
    parser.add_argument(
        "--require-runtime-smoke-dimensions",
        type=parse_runtime_smoke_dimensions,
        default=(),
        dest="required_runtime_smoke_dimensions",
        help="Optional comma-separated runtime-smoke input dimensions before packaging or official eval",
    )
    parser.add_argument(
        "--require-holdout-improvement",
        action="store_true",
        help="Require this result to beat the task's previous reliable aggregate holdout before packaging",
    )
    parser.add_argument(
        "--min-holdout-improvement-delta",
        type=non_negative_float,
        default=0.0,
        help="Minimum positive holdout-rate delta over the previous reliable best when improvement is required",
    )
    parser.add_argument(
        "--holdout-history-root",
        default="runs",
        help="Historical runs root used by --require-holdout-improvement",
    )
    parser.add_argument(
        "--holdout-history-exclude-root",
        action="append",
        dest="holdout_history_exclude_roots",
        default=[],
        help="Historical result root to exclude from --require-holdout-improvement; may be repeated",
    )
    parser.add_argument(
        "--max-generalization-risk",
        choices=["low", "medium", "high"],
        default=None,
        help="Optional aggregate-only generalization risk ceiling before packaging or official eval",
    )
    parser.add_argument(
        "--generalization-risk-root",
        default="runs",
        help="Historical runs root used by --max-generalization-risk",
    )
    parser.add_argument(
        "--baseline-root",
        default="baselines/programbench",
        help="Recorded baseline root used by --max-generalization-risk",
    )
    parser.add_argument("--pull", action="store_true", help="Pull missing task_cleanroom image during preparation")
    parser.add_argument(
        "--official-eval-root",
        default="runs/programbench_official_eval",
        help="Root for official eval submission/eval artifacts",
    )
    parser.add_argument("--eval-run-name", default="", help="Official eval run directory name")
    parser.add_argument("--workers", type=positive_int, default=1, help="ProgramBench instance workers")
    parser.add_argument("--branch-workers", type=positive_int, default=1, help="ProgramBench branch workers")
    parser.add_argument("--docker-cpus", type=positive_int, default=4, help="Docker CPUs per ProgramBench eval container")
    parser.add_argument("--branch-retries", type=non_negative_int, default=1, help="ProgramBench branch retries")
    parser.add_argument(
        "--programbench-python",
        default="py",
        help="Python launcher that can import programbench",
    )
    parser.add_argument(
        "--programbench-python-version",
        default="3.14",
        help="Version argument for the py launcher; ignored for other launchers",
    )
    parser.add_argument("--model", default="glm-5.1", help="Model name for baseline recording")
    parser.add_argument("--baseline-output", default="baselines/programbench", help="Baseline output directory")
    parser.add_argument(
        "--strategy-registry",
        default="",
        help="Optional aggregate-only JSONL registry for closed-loop strategy selection and recording",
    )
    parser.add_argument(
        "--strategy-variant",
        default="",
        help="Optional strategy variant id to force instead of bandit selection",
    )
    parser.add_argument("--skip-official-eval", action="store_true", help="Stop after holdout-gated packaging")
    parser.add_argument(
        "--ack-external-llm-docker",
        action="store_true",
        help=(
            "Required before running. Acknowledge that closed-loop reconstruction may "
            "call external LLM APIs and Docker; --skip-official-eval only disables official eval."
        ),
    )
    parser.add_argument(
        "--ack-local-llm-docker",
        action="store_true",
        help=(
            "Required alternative for local-only LLM configs. Acknowledge that the run "
            "may use Docker and a file_bridge or loopback local_openai provider, but not external LLM APIs."
        ),
    )
    parser.add_argument("--force", action="store_true", help="Force ProgramBench official re-evaluation")
    return parser.parse_args(argv)


def _is_loopback_url(base_url: object) -> bool:
    parsed = urlparse(str(base_url or ""))
    if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
        return False
    host = parsed.hostname.lower()
    if host == "localhost":
        return True
    return host.startswith("127.") or host == "::1"


def is_local_llm_config(config_path: str | Path) -> bool:
    try:
        config = load_config(str(config_path))
    except (OSError, KeyError, TypeError, ValueError):
        return False
    llm_config = config.get("llm") if isinstance(config, dict) else None
    if not isinstance(llm_config, dict):
        return False
    provider = llm_config.get("provider")
    if provider == "file_bridge":
        return True
    if provider == "local_openai":
        local_config = llm_config.get("local_openai")
        return isinstance(local_config, dict) and _is_loopback_url(local_config.get("base_url"))
    return False


def has_execution_ack(args: argparse.Namespace) -> bool:
    if args.ack_external_llm_docker:
        return True
    return bool(args.ack_local_llm_docker and is_local_llm_config(args.config))


def execution_ack_error(args: argparse.Namespace) -> str:
    if args.ack_local_llm_docker:
        return (
            "ERROR: local LLM ack --ack-local-llm-docker is only valid for file_bridge or "
            "loopback local_openai configs; use --ack-external-llm-docker for external providers."
        )
    return (
        "ERROR: --ack-external-llm-docker is required because the closed-loop run "
        "may call external LLM APIs and Docker. For file_bridge or loopback local_openai "
        "configs, pass --ack-local-llm-docker instead."
    )


def build_paths(instance_id: str, runs_root: Path | str, official_eval_root: Path | str, eval_run_name: str = ""):
    run_root = Path(runs_root)
    session_root = run_root / instance_id
    output_root = session_root / "generated" / instance_id
    generated = output_root / instance_id
    run_name = eval_run_name or f"submission_{instance_id.replace('.', '_').replace('__', '_')}"
    submission_root = Path(official_eval_root) / run_name
    return ClosedLoopPaths(
        session_root=session_root,
        workspace=session_root / "workspace",
        output_root=output_root,
        generated=generated,
        result=generated / "result.json",
        submission_root=submission_root,
        submission=submission_root / instance_id / "submission.tar.gz",
        eval_json=submission_root / instance_id / f"{instance_id}.eval.json",
    )


def build_prepare_command(args: argparse.Namespace) -> list[str]:
    command = [
        sys.executable,
        "scripts/prepare_programbench_task.py",
        args.instance_id,
        "--catalog",
        args.catalog,
        "--runs",
        args.runs,
    ]
    if args.pull:
        command.append("--pull")
    return command


def build_rebuilder_command(
    args: argparse.Namespace,
    paths: ClosedLoopPaths,
    cleanroom_image: str,
    max_repairs: int | None = None,
) -> list[str]:
    repair_iterations = args.max_repairs if max_repairs is None else max_repairs
    command = [
        sys.executable,
        "main.py",
        "--task",
        str(paths.workspace),
        "--config",
        args.config,
        "--output",
        str(paths.output_root),
        "--max-repairs",
        str(repair_iterations),
        "--probe-iterations",
        str(args.probe_iterations),
        "--min-probe-samples",
        str(args.min_probe_samples),
        "--reference-docker-image",
        cleanroom_image,
        "--replacement-executor",
        args.replacement_executor,
        "--adaptive-probes",
        args.adaptive_probes,
    ]
    if args.static_output_assets != "config":
        command.extend(["--static-output-assets", args.static_output_assets])
    return command


def build_strategy_candidates(args: argparse.Namespace) -> list[StrategyVariant]:
    """Build safe aggregate-learning strategy variants from run-time knobs."""
    base_params = {
        "probe_budget": int(args.probe_iterations),
        "min_samples": int(args.min_probe_samples),
        "max_repair_attempts": int(args.max_repairs),
        "implementation_mode": f"static_assets:{args.static_output_assets}",
        "model": str(args.model),
    }
    deep_probe_budget = max(int(args.probe_iterations), 20)
    deep_min_samples = max(int(args.min_probe_samples), 80)
    deep_repairs = max(int(args.max_repairs), int(args.near_miss_max_repairs))
    return [
        StrategyVariant(
            variant_id="adaptive_profile",
            strategy="closed_loop",
            params={**base_params, "use_adaptive_probes": True},
        ),
        StrategyVariant(
            variant_id="baseline_no_adaptive",
            strategy="closed_loop",
            params={**base_params, "use_adaptive_probes": False},
        ),
        StrategyVariant(
            variant_id="adaptive_deep",
            strategy="closed_loop",
            params={
                **base_params,
                "use_adaptive_probes": True,
                "probe_budget": deep_probe_budget,
                "min_samples": deep_min_samples,
                "max_repair_attempts": deep_repairs,
            },
        ),
    ]


def select_strategy_variant(args: argparse.Namespace) -> StrategyVariant:
    """Select a closed-loop strategy variant from aggregate-only history."""
    candidates = build_strategy_candidates(args)
    if args.strategy_variant:
        for candidate in candidates:
            if candidate.variant_id == args.strategy_variant:
                return candidate
        valid = ", ".join(candidate.variant_id for candidate in candidates)
        raise ValueError(f"Unknown strategy variant {args.strategy_variant!r}; expected one of: {valid}")
    history = ExperimentRegistry(args.strategy_registry).load() if args.strategy_registry else []
    return StrategyBandit().select_variant(history, candidates)


def apply_strategy_variant(args: argparse.Namespace, variant: StrategyVariant) -> None:
    """Apply safe scalar strategy params to closed-loop CLI args."""
    params = variant.params
    if "use_adaptive_probes" in params:
        args.adaptive_probes = "enabled" if params["use_adaptive_probes"] else "disabled"
    if "probe_budget" in params:
        args.probe_iterations = int(params["probe_budget"])
    elif "max_iterations" in params:
        args.probe_iterations = int(params["max_iterations"])
    if "min_samples" in params:
        args.min_probe_samples = int(params["min_samples"])
    if "max_repair_attempts" in params:
        args.max_repairs = int(params["max_repair_attempts"])
    implementation_mode = params.get("implementation_mode")
    if isinstance(implementation_mode, str) and implementation_mode.startswith("static_assets:"):
        value = implementation_mode.partition(":")[2]
        if value in {"config", "enabled", "disabled"}:
            args.static_output_assets = value


def build_package_command(args: argparse.Namespace, paths: ClosedLoopPaths) -> list[str]:
    command = [
        sys.executable,
        "scripts/package_submission.py",
        args.instance_id,
        "--generated",
        str(paths.generated),
        "--result",
        str(paths.result),
        "--output",
        str(paths.submission_root),
        "--min-holdout-rate",
        str(args.min_holdout_rate),
        "--min-holdout-cases",
        str(args.min_holdout_cases),
    ]
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
                str(args.generalization_risk_root),
                "--baseline-root",
                str(args.baseline_root),
                "--official-eval-root",
                str(args.official_eval_root),
            ]
        )
    return command


def build_programbench_eval_command(args: argparse.Namespace, paths: ClosedLoopPaths) -> list[str]:
    launcher = [args.programbench_python]
    if args.programbench_python == "py" and args.programbench_python_version:
        launcher.append(f"-{args.programbench_python_version}")
    command = [
        *launcher,
        "-c",
        "from programbench.cli.main import app; app()",
        "eval",
        str(paths.submission_root),
        "--workers",
        str(args.workers),
        "--branch-workers",
        str(args.branch_workers),
        "--docker-cpus",
        str(args.docker_cpus),
        "--branch-retries",
        str(args.branch_retries),
    ]
    if args.force:
        command.append("--force")
    return command


def load_result(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def as_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    try:
        parsed = float(value or 0)
    except (TypeError, ValueError):
        return 0
    if not math.isfinite(parsed) or parsed < 0 or not parsed.is_integer():
        return 0
    return int(parsed)


def as_optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and 0.0 <= parsed <= 1.0 else None


def holdout_rate(payload: dict) -> float | None:
    return as_optional_float(payload.get("holdout_resolved_rate"))


def holdout_cases(payload: dict) -> int:
    return as_int(payload.get("holdout_cases"))


def smoke_contract_axis_count(payload: dict) -> int:
    metadata = payload.get("implementation_metadata")
    if not isinstance(metadata, dict):
        return 0
    coverage = metadata.get("probe_axis_coverage")
    if not isinstance(coverage, dict):
        return 0
    return as_int(coverage.get("smoke_contract_axis_count"))


def should_retry_near_miss(args: argparse.Namespace, rate: float | None) -> bool:
    if rate is None:
        return False
    if rate < args.near_miss_holdout_rate or rate >= args.min_holdout_rate:
        return False
    return args.near_miss_max_repairs > args.max_repairs


def build_subprocess_env() -> dict[str, str]:
    """Force UTF-8 output for child Python CLIs on Windows redirected consoles."""
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env.setdefault("NO_COLOR", "1")
    return env


def run_command(command: list[str]) -> None:
    print("+ " + " ".join(command), flush=True)
    result = subprocess.run(command, text=True, check=False, env=build_subprocess_env())
    if result.returncode != 0:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(command)}")


def run_programbench_eval(args: argparse.Namespace, paths: ClosedLoopPaths) -> None:
    try:
        run_command(build_programbench_eval_command(args, paths))
    except RuntimeError:
        if paths.eval_json.exists():
            print(
                f"ProgramBench eval command failed after writing {paths.eval_json}; "
                "continuing with aggregate eval JSON",
                flush=True,
            )
            return
        raise


def summarize_eval(eval_json: Path, instance_id: str) -> tuple[int, int, int, int]:
    parser = ProgramBenchEvalParser()
    raw = parser.parse(eval_json)
    counted = parser.parse(eval_json, instance_id=instance_id)
    print(f"raw={raw.passed_tests}/{raw.total_tests} score={round(raw.score * 100)}")
    print(f"counted={counted.passed_tests}/{counted.total_tests} score={round(counted.score * 100)}")
    return raw.passed_tests, raw.total_tests, counted.passed_tests, counted.total_tests


def record_baseline(
    *,
    args: argparse.Namespace,
    paths: ClosedLoopPaths,
    raw_passed: int,
    raw_total: int,
    counted_passed: int,
    counted_total: int,
) -> Path:
    counted_score = round((counted_passed / counted_total) * 100) if counted_total else 0
    notes = (
        f"Official closed-loop aggregate baseline: {counted_passed}/{counted_total} counted tests, "
        f"score {counted_score}; raw eval {raw_passed}/{raw_total}; aggregate-only."
    )
    return BaselineRecorder().record(
        instance_id=args.instance_id,
        local_result_path=paths.result,
        official_eval_path=paths.eval_json,
        submission_archive_path=paths.submission,
        output_dir=Path(args.baseline_output),
        model=args.model,
        config_path=args.config,
        notes=notes,
    )


def official_summary_to_feedback(summary) -> AggregateFeedback:
    """Convert official eval summary into aggregate-only experiment feedback."""
    return AggregateFeedback(
        score=summary.score,
        passed_tests=summary.passed_tests,
        total_tests=summary.total_tests,
        pass_rate=summary.pass_rate,
        fully_resolved=summary.fully_resolved,
        almost_resolved=summary.almost_resolved,
        error_code=summary.error_code,
        warning_count=len(summary.warnings),
    )


def record_strategy_experiment(
    *,
    args: argparse.Namespace,
    paths: ClosedLoopPaths,
    variant: StrategyVariant | None,
) -> Path | None:
    """Append one official aggregate-only strategy result, when configured."""
    if not args.strategy_registry or variant is None:
        return None
    created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    summary = ProgramBenchEvalParser().parse(paths.eval_json, instance_id=args.instance_id)
    run = ExperimentRun(
        run_id=f"{args.instance_id}:{variant.variant_id}:{created_at}",
        instance_id=args.instance_id,
        variant=variant,
        official=official_summary_to_feedback(summary),
        holdout_cases=holdout_cases(load_result(paths.result)),
        created_at=created_at,
    )
    registry = ExperimentRegistry(args.strategy_registry)
    registry.append(run)
    return registry.path


def enforce_holdout_improvement_gate(args: argparse.Namespace, paths: ClosedLoopPaths) -> None:
    """Optionally require a local result to beat previous reliable holdout."""
    if not args.require_holdout_improvement:
        return
    audit = audit_holdout_improvement(
        paths.result,
        runs_root=args.holdout_history_root,
        min_holdout_cases=args.min_holdout_cases,
        min_delta=args.min_holdout_improvement_delta,
        exclude_roots=args.holdout_history_exclude_roots,
    )
    if audit["improved"]:
        print(
            "holdout_improvement=improved "
            f"delta={audit['delta_from_best_previous']} "
            f"best={audit['best_previous_holdout_resolved_rate']}",
            flush=True,
        )
        return
    print(
        "holdout_improvement="
        f"{audit['reason']} current={audit['current_holdout_resolved_rate']} "
        f"best={audit['best_previous_holdout_resolved_rate']}; skipping official eval",
        flush=True,
    )
    raise SystemExit(3)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if not has_execution_ack(args):
        print(execution_ack_error(args), file=sys.stderr, flush=True)
        raise SystemExit(2)
    strategy_variant = None
    if args.strategy_registry or args.strategy_variant:
        strategy_variant = select_strategy_variant(args)
        apply_strategy_variant(args, strategy_variant)
        print(f"strategy_variant={strategy_variant.variant_id}", flush=True)
    sample = select_sample(load_sample_catalog(args.catalog), args.instance_id)
    paths = build_paths(args.instance_id, args.runs, args.official_eval_root, args.eval_run_name)

    run_command(build_prepare_command(args))
    run_command(build_rebuilder_command(args, paths, sample.cleanroom_image))

    result_payload = load_result(paths.result)
    rate = holdout_rate(result_payload)
    if should_retry_near_miss(args, rate):
        print(
            f"holdout={rate:.4f} is a near miss; retrying local repair with "
            f"--max-repairs={args.near_miss_max_repairs}",
            flush=True,
        )
        run_command(build_rebuilder_command(args, paths, sample.cleanroom_image, args.near_miss_max_repairs))
        result_payload = load_result(paths.result)
        rate = holdout_rate(result_payload)
    cases = holdout_cases(result_payload)
    if cases < args.min_holdout_cases:
        print(f"holdout_cases={cases} below min={args.min_holdout_cases}; skipping official eval")
        raise SystemExit(3)
    if rate is None or rate < args.min_holdout_rate:
        print(f"holdout={rate if rate is not None else 'missing'} below min={args.min_holdout_rate}; skipping official eval")
        raise SystemExit(3)
    smoke_axes = smoke_contract_axis_count(result_payload)
    if smoke_axes < args.min_smoke_contract_axes:
        print(
            f"smoke_contract_axes={smoke_axes} below min={args.min_smoke_contract_axes}; "
            "skipping official eval"
        )
        raise SystemExit(3)
    runtime_smoke_status, runtime_smoke_dimensions = runtime_smoke_metadata(result_payload)
    if args.required_runtime_smoke_dimensions:
        missing_dimensions = tuple(
            dimension
            for dimension in args.required_runtime_smoke_dimensions
            if dimension not in runtime_smoke_dimensions
        )
        if runtime_smoke_status != "passed" or missing_dimensions:
            missing_text = ",".join(missing_dimensions) if missing_dimensions else "none"
            print(
                "runtime_smoke_dimensions="
                f"{','.join(runtime_smoke_dimensions) or 'missing'} "
                f"status={runtime_smoke_status or 'missing'} "
                f"missing_required={missing_text}; skipping official eval"
            )
            raise SystemExit(3)
    enforce_holdout_improvement_gate(args, paths)
    print(f"holdout={rate:.4f}; packaging")
    run_command(build_package_command(args, paths))

    if args.skip_official_eval:
        print(f"submission={paths.submission}")
        return

    run_programbench_eval(args, paths)
    raw_passed, raw_total, counted_passed, counted_total = summarize_eval(paths.eval_json, args.instance_id)
    baseline_path = record_baseline(
        args=args,
        paths=paths,
        raw_passed=raw_passed,
        raw_total=raw_total,
        counted_passed=counted_passed,
        counted_total=counted_total,
    )
    print(f"baseline={baseline_path}")
    registry_path = record_strategy_experiment(args=args, paths=paths, variant=strategy_variant)
    if registry_path:
        print(f"strategy_registry={registry_path}")


if __name__ == "__main__":
    main()
