"""Run ReBuilder, gate by holdout, then run official ProgramBench eval."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.evaluation import ProgramBenchEvalParser
from core.experiments import BaselineRecorder
from core.programbench.catalog import load_sample_catalog, select_sample

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
        type=int,
        default=10,
        help="ReBuilder LLM probe planning iterations; deterministic supplemental probes fill --min-probe-samples",
    )
    parser.add_argument(
        "--min-probe-samples",
        type=int,
        default=50,
        help="Minimum ReBuilder behavior samples before implementation; default supports the holdout case gate",
    )
    parser.add_argument("--max-repairs", type=int, default=3, help="ReBuilder repair iterations")
    parser.add_argument(
        "--near-miss-holdout-rate",
        type=float,
        default=0.75,
        help="Holdout rate that triggers one deeper local repair retry before giving up",
    )
    parser.add_argument(
        "--near-miss-max-repairs",
        type=int,
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
    parser.add_argument("--min-holdout-rate", type=float, default=0.8, help="Minimum holdout rate before official eval")
    parser.add_argument(
        "--min-holdout-cases",
        type=int,
        default=10,
        help="Minimum internal holdout cases before official eval",
    )
    parser.add_argument("--pull", action="store_true", help="Pull missing task_cleanroom image during preparation")
    parser.add_argument(
        "--official-eval-root",
        default="runs/programbench_official_eval",
        help="Root for official eval submission/eval artifacts",
    )
    parser.add_argument("--eval-run-name", default="", help="Official eval run directory name")
    parser.add_argument("--workers", type=int, default=1, help="ProgramBench instance workers")
    parser.add_argument("--branch-workers", type=int, default=1, help="ProgramBench branch workers")
    parser.add_argument("--docker-cpus", type=int, default=4, help="Docker CPUs per ProgramBench eval container")
    parser.add_argument("--branch-retries", type=int, default=1, help="ProgramBench branch retries")
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
    parser.add_argument("--skip-official-eval", action="store_true", help="Stop after holdout-gated packaging")
    parser.add_argument("--force", action="store_true", help="Force ProgramBench official re-evaluation")
    return parser.parse_args(argv)


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
    ]
    if args.static_output_assets != "config":
        command.extend(["--static-output-assets", args.static_output_assets])
    return command


def build_package_command(args: argparse.Namespace, paths: ClosedLoopPaths) -> list[str]:
    return [
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
    return json.loads(path.read_text(encoding="utf-8"))


def holdout_rate(payload: dict) -> float | None:
    value = payload.get("holdout_resolved_rate")
    if value is None:
        return None
    return float(value)


def holdout_cases(payload: dict) -> int:
    return int(payload.get("holdout_cases") or 0)


def should_retry_near_miss(args: argparse.Namespace, rate: float | None) -> bool:
    if rate is None:
        return False
    if rate < args.near_miss_holdout_rate or rate >= args.min_holdout_rate:
        return False
    return args.near_miss_max_repairs > args.max_repairs


def run_command(command: list[str]) -> None:
    print("+ " + " ".join(command), flush=True)
    result = subprocess.run(command, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(command)}")


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


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
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
    print(f"holdout={rate:.4f}; packaging")
    run_command(build_package_command(args, paths))

    if args.skip_official_eval:
        print(f"submission={paths.submission}")
        return

    run_command(build_programbench_eval_command(args, paths))
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


if __name__ == "__main__":
    main()
