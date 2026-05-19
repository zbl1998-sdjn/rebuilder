"""Print or run guarded weak-task ProgramBench cleanroom reruns."""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.summarize_holdout_trends import (  # noqa: E402
    WeakRerunRecommendation,
    collect_holdout_trends,
    recommend_weak_reruns,
    safe_path_slug,
)
from core.submission import parse_runtime_smoke_dimensions  # noqa: E402
from scripts.run_official_closed_loop import is_local_llm_config  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print or run guarded weak-task cleanroom reruns for ProgramBench tasks"
    )
    parser.add_argument("instance_ids", nargs="*", help="Optional weak-task ids to include")
    parser.add_argument("--runs", default="runs", help="Historical runs root")
    parser.add_argument("--output-root", default="runs/weak_task_cleanroom_next", help="Rerun output root")
    parser.add_argument("--config", default="config/settings.yaml", help="ReBuilder config path")
    parser.add_argument("--limit", type=positive_int, default=3, help="Maximum weak-task targets to include")
    parser.add_argument("--min-holdout-cases", type=non_negative_int, default=10)
    parser.add_argument("--min-holdout-rate", type=rate_float, default=0.8)
    parser.add_argument("--min-smoke-contract-axes", type=non_negative_int, default=1)
    parser.add_argument(
        "--require-runtime-smoke-dimensions",
        type=parse_runtime_smoke_dimensions,
        default=(),
        dest="required_runtime_smoke_dimensions",
    )
    parser.add_argument("--min-holdout-improvement-delta", type=non_negative_float, default=0.02)
    parser.add_argument("--holdout-history-root", default=None)
    parser.add_argument("--pull", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--keep-going", action="store_true", help="Continue executing after a target command fails")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually run weak-task rerun commands. Without this flag, commands are printed only.",
    )
    parser.add_argument(
        "--ack-external-llm-docker",
        action="store_true",
        help=(
            "Required with --execute. Acknowledge that child runs may call external "
            "LLM APIs and Docker while official eval remains disabled by this wrapper."
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
        help="Print weak-task rerun commands without running them. This is the default behavior.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Dry-run output format. JSON is limited to command plans and never executes child commands.",
    )
    parser.add_argument(
        "--command-timeout-seconds",
        type=positive_float,
        default=21600.0,
        help="Timeout per weak-task rerun command when --execute is used",
    )
    return parser.parse_args(argv)


def non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be non-negative")
    return parsed


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def positive_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive and finite")
    return parsed


def non_negative_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError("value must be non-negative and finite")
    return parsed


def rate_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0 or parsed > 1:
        raise argparse.ArgumentTypeError("value must be a finite rate between 0 and 1")
    return parsed


def select_weak_batch_targets(args: argparse.Namespace) -> list[WeakRerunRecommendation]:
    trends = collect_holdout_trends(args.runs, min_holdout_cases=args.min_holdout_cases)
    recommendations = recommend_weak_reruns(
        trends,
        min_holdout_rate=args.min_holdout_rate,
        history_root=args.holdout_history_root or args.runs,
    )
    selected_ids = set(args.instance_ids)
    selected = [row for row in recommendations if not selected_ids or row.task_id in selected_ids]
    return selected[: args.limit]


def build_weak_rerun_command(task_id: str, args: argparse.Namespace) -> list[str]:
    run_root = Path(args.output_root) / safe_path_slug(task_id)
    command = [
        sys.executable,
        "scripts/run_weak_task_cleanroom_rerun.py",
        task_id,
        "--config",
        args.config,
        "--runs",
        run_root.as_posix(),
        "--min-holdout-rate",
        str(args.min_holdout_rate),
        "--min-holdout-cases",
        str(args.min_holdout_cases),
        "--min-holdout-improvement-delta",
        str(args.min_holdout_improvement_delta),
        "--holdout-history-root",
        args.holdout_history_root or args.runs,
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
    if args.pull:
        command.append("--pull")
    if args.force:
        command.append("--force")
    if args.execute and not getattr(args, "dry_run", False):
        command.append("--execute")
        if args.ack_external_llm_docker:
            command.append("--ack-external-llm-docker")
        elif args.ack_local_llm_docker:
            command.append("--ack-local-llm-docker")
    else:
        command.append("--dry-run")
    return command


def weak_batch_json_payload(
    targets: list[WeakRerunRecommendation], args: argparse.Namespace
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for rank, target in enumerate(targets, start=1):
        rows.append(
            {
                "rank": rank,
                "task_id": target.task_id,
                "latest_holdout_resolved_rate": target.latest_holdout_resolved_rate,
                "latest_holdout_cases": target.latest_holdout_cases,
                "best_holdout_resolved_rate": target.best_holdout_resolved_rate,
                "best_holdout_cases": target.best_holdout_cases,
                "reason": target.reason,
                "required_flags": target.required_flags,
                "command": build_weak_rerun_command(target.task_id, args),
            }
        )
    return {
        "schema_version": 1,
        "execute": bool(args.execute and not args.dry_run),
        "row_count": len(rows),
        "rows": rows,
    }


def write_weak_batch_json_plan(targets: list[WeakRerunRecommendation], args: argparse.Namespace) -> None:
    print(json.dumps(weak_batch_json_payload(targets, args), indent=2, ensure_ascii=False), flush=True)


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
    if args.execute and not args.dry_run and not (
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
            "ERROR: --execute requires --ack-external-llm-docker because child runs "
            "may call external LLM APIs and Docker. For file_bridge or loopback local_openai "
            "configs, pass --ack-local-llm-docker instead.",
            file=sys.stderr,
            flush=True,
        )
        return 2
    if args.format == "json" and args.execute and not args.dry_run:
        print(
            "ERROR: --format json is only supported for dry-run command plans.",
            file=sys.stderr,
            flush=True,
        )
        return 2
    targets = select_weak_batch_targets(args)
    if not targets:
        if args.format == "json":
            write_weak_batch_json_plan(targets, args)
        else:
            print("No weak-task rerun targets selected.", flush=True)
        return 0
    if args.format == "json":
        write_weak_batch_json_plan(targets, args)
        return 0
    exit_code = 0
    for target in targets:
        command = build_weak_rerun_command(target.task_id, args)
        if args.dry_run or not args.execute:
            print(f"DRY-RUN weak-task rerun: {target.task_id}", flush=True)
            print(" ".join(command), flush=True)
            continue
        print(f"Running weak-task rerun: {target.task_id}", flush=True)
        result = run_command(command, timeout_seconds=args.command_timeout_seconds)
        if result == 0:
            continue
        exit_code = result
        if not args.keep_going:
            return result
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
