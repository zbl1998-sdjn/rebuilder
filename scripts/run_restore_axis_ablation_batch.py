"""Print or run guarded restore-axis ProgramBench strategy ablations."""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit_generalization_risk import DEFAULT_MAX_LOCAL_HOLDOUT_GAP  # noqa: E402
from scripts.audit_restore_targets import collect_restore_target_audits  # noqa: E402
from scripts.plan_official_breakthrough_targets import (  # noqa: E402
    BreakthroughTarget,
    collect_official_breakthrough_targets,
    safe_path_component,
)
from core.submission import parse_runtime_smoke_dimensions  # noqa: E402
from scripts.run_official_closed_loop import is_local_llm_config  # noqa: E402

DEFAULT_VARIANTS = ("baseline_no_adaptive", "adaptive_profile", "adaptive_deep")


@dataclass(frozen=True)
class RestoreBatchTarget:
    task_id: str
    axis_delta_action: str | None = None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print or run guarded restore-axis strategy ablations for ProgramBench tasks"
    )
    parser.add_argument("instance_ids", nargs="*", help="Optional restore target ids to include")
    parser.add_argument("--runs", default="runs", help="Historical runs root")
    parser.add_argument("--baseline-root", default="baselines/programbench", help="Recorded baseline root")
    parser.add_argument("--official-eval-root", default="runs/programbench_official_eval")
    parser.add_argument("--output-root", default="runs/restore_axis_ablation_next", help="Ablation output root")
    parser.add_argument("--config", default="config/settings.yaml", help="ReBuilder config path")
    parser.add_argument("--limit", type=positive_int, default=20, help="Maximum restore targets to include")
    parser.add_argument("--min-holdout-cases", type=non_negative_int, default=10)
    parser.add_argument("--min-holdout-rate", type=rate_float, default=0.8)
    parser.add_argument("--variants", nargs="+", default=list(DEFAULT_VARIANTS), help="Strategy variants to run")
    parser.add_argument("--min-smoke-contract-axes", type=non_negative_int, default=1)
    parser.add_argument(
        "--require-runtime-smoke-dimensions",
        type=parse_runtime_smoke_dimensions,
        default=(),
        dest="required_runtime_smoke_dimensions",
    )
    parser.add_argument("--max-generalization-risk", choices=["low", "medium", "high"], default="low")
    parser.add_argument(
        "--max-local-holdout-gap",
        type=rate_float,
        default=DEFAULT_MAX_LOCAL_HOLDOUT_GAP,
        help="Maximum local-vs-holdout aggregate gap forwarded to strategy ablation commands",
    )
    parser.add_argument(
        "--axis-action-domain",
        action="append",
        default=[],
        help="Only include restore targets whose cleanroom axis action references this domain. Repeatable.",
    )
    parser.add_argument(
        "--show-axis-action",
        action="store_true",
        help="Annotate dry-run/execution banners with cleanroom axis actions.",
    )
    parser.add_argument(
        "--apply-axis-action",
        action="store_true",
        help=(
            "Translate cleanroom axis actions into child ReBuilder flags. "
            "Currently ablate_added_axis_domains excludes those adaptive probe domains "
            "and relaxes the child smoke-axis floor to 0."
        ),
    )
    parser.add_argument("--keep-going", action="store_true", help="Continue executing after a target command fails")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually run strategy ablation commands. Without this flag, commands are printed only.",
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
        help="Print strategy ablation commands without running them. This is the default behavior.",
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
        help="Timeout per strategy ablation command when --execute is used",
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


def rate_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0 or parsed > 1:
        raise argparse.ArgumentTypeError("value must be a finite rate between 0 and 1")
    return parsed


def select_restore_targets(args: argparse.Namespace) -> list[BreakthroughTarget]:
    rows = collect_official_breakthrough_targets(
        args.runs,
        args.baseline_root,
        min_holdout_cases=args.min_holdout_cases,
        min_holdout_rate=args.min_holdout_rate,
    )
    selected_ids = set(args.instance_ids)
    restore_rows = [
        row
        for row in rows
        if row.target_class == "restore_historical_gate" and (not selected_ids or row.task_id in selected_ids)
    ]
    return restore_rows[: args.limit]


def select_restore_batch_targets(args: argparse.Namespace) -> list[RestoreBatchTarget]:
    if args.axis_action_domain or args.show_axis_action or args.apply_axis_action:
        audits = collect_restore_target_audits(
            args.runs,
            args.baseline_root,
            official_eval_root=args.official_eval_root,
            min_holdout_cases=args.min_holdout_cases,
            min_holdout_rate=args.min_holdout_rate,
        )
        selected_ids = set(args.instance_ids)
        selected_domains = set(args.axis_action_domain)
        rows = [
            row
            for row in audits
            if (not selected_ids or row.task_id in selected_ids)
            and (not selected_domains or selected_domains.intersection(axis_action_domains(row.axis_delta_action)))
        ]
        return [
            RestoreBatchTarget(task_id=row.task_id, axis_delta_action=row.axis_delta_action)
            for row in rows[: args.limit]
        ]
    return [RestoreBatchTarget(task_id=row.task_id) for row in select_restore_targets(args)]


def axis_action_domains(axis_delta_action: str) -> tuple[str, ...]:
    _prefix, separator, raw_domains = axis_delta_action.partition(":")
    if not separator:
        return ()
    return tuple(domain.strip() for domain in raw_domains.split(",") if domain.strip())


def axis_action_exclude_domains(axis_delta_action: str | None) -> tuple[str, ...]:
    if not axis_delta_action or not axis_delta_action.startswith("ablate_added_axis_domains:"):
        return ()
    return axis_action_domains(axis_delta_action)


def target_axis_exclude_domains(target: RestoreBatchTarget | None, args: argparse.Namespace) -> tuple[str, ...]:
    if not getattr(args, "apply_axis_action", False) or target is None:
        return ()
    return axis_action_exclude_domains(target.axis_delta_action)


def effective_min_smoke_contract_axes(target: RestoreBatchTarget | None, args: argparse.Namespace) -> int:
    if target_axis_exclude_domains(target, args):
        return 0
    return int(args.min_smoke_contract_axes)


def build_strategy_ablation_command(
    task_id: str,
    args: argparse.Namespace,
    target: RestoreBatchTarget | None = None,
) -> list[str]:
    run_root = Path(args.output_root) / safe_path_component(task_id)
    command = [
        sys.executable,
        "scripts/run_official_strategy_ablation.py",
        task_id,
        "--runs",
        run_root.as_posix(),
        "--config",
        args.config,
        "--variants",
        *args.variants,
        "--skip-official-eval",
        "--require-holdout-improvement",
        "--holdout-history-root",
        args.runs,
        "--max-generalization-risk",
        args.max_generalization_risk,
        "--max-local-holdout-gap",
        str(getattr(args, "max_local_holdout_gap", DEFAULT_MAX_LOCAL_HOLDOUT_GAP)),
        "--generalization-risk-root",
        args.runs,
        "--baseline-root",
        args.baseline_root,
        "--min-smoke-contract-axes",
        str(effective_min_smoke_contract_axes(target, args)),
    ]
    for domain in target_axis_exclude_domains(target, args):
        command.extend(["--adaptive-probe-exclude-domain", domain])
    if getattr(args, "required_runtime_smoke_dimensions", ()):
        command.extend(
            [
                "--require-runtime-smoke-dimensions",
                ",".join(args.required_runtime_smoke_dimensions),
            ]
        )
    if args.keep_going:
        command.append("--keep-going")
    if args.execute and not getattr(args, "dry_run", False):
        if args.ack_external_llm_docker:
            command.append("--ack-external-llm-docker")
        elif args.ack_local_llm_docker:
            command.append("--ack-local-llm-docker")
    if getattr(args, "dry_run", False) or not args.execute:
        command.append("--dry-run")
    return command


def format_target_banner(prefix: str, target: RestoreBatchTarget) -> str:
    message = f"{prefix}: {target.task_id}"
    if target.axis_delta_action:
        message += f" [axis_action={target.axis_delta_action}]"
    return message


def restore_batch_json_payload(targets: list[RestoreBatchTarget], args: argparse.Namespace) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for rank, target in enumerate(targets, start=1):
        rows.append(
            {
                "rank": rank,
                "task_id": target.task_id,
                "axis_delta_action": target.axis_delta_action,
                "applied_axis_exclude_domains": list(target_axis_exclude_domains(target, args)),
                "effective_min_smoke_contract_axes": effective_min_smoke_contract_axes(target, args),
                "command": build_strategy_ablation_command(target.task_id, args, target),
            }
        )
    return {
        "schema_version": 1,
        "execute": bool(args.execute and not args.dry_run),
        "row_count": len(rows),
        "rows": rows,
    }


def write_restore_batch_json_plan(targets: list[RestoreBatchTarget], args: argparse.Namespace) -> None:
    print(json.dumps(restore_batch_json_payload(targets, args), indent=2, ensure_ascii=False), flush=True)


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
    targets = select_restore_batch_targets(args)
    if not targets:
        print("No restore_historical_gate targets selected.", flush=True)
        return 0
    if args.format == "json" and args.execute and not args.dry_run:
        print(
            "ERROR: --format json is only supported for dry-run command plans.",
            file=sys.stderr,
            flush=True,
        )
        return 2
    if args.format == "json":
        write_restore_batch_json_plan(targets, args)
        return 0
    exit_code = 0
    for target in targets:
        command = build_strategy_ablation_command(target.task_id, args, target)
        if args.dry_run or not args.execute:
            print(format_target_banner("DRY-RUN restore-axis ablation", target), flush=True)
            print(" ".join(command), flush=True)
            continue
        print(format_target_banner("Running restore-axis ablation", target), flush=True)
        result = run_command(command, timeout_seconds=args.command_timeout_seconds)
        if result == 0:
            continue
        exit_code = result
        if not args.keep_going:
            return result
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
