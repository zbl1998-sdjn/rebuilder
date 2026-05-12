"""Run a cleanroom ProgramBench mini-lab over multiple samples."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.experiments.mini_lab import (
    MiniLabCommandBuilder,
    MiniLabReportWriter,
    MiniLabResultCollector,
)
from core.programbench.adapter import ProgramBenchTaskAdapter
from core.programbench.catalog import load_sample_catalog, select_sample
from core.programbench.samples import ProgramBenchSample
from core.programbench.workspace import CleanroomWorkspace, CleanroomWorkspaceError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a ProgramBench cleanroom mini-lab")
    parser.add_argument(
        "--catalog",
        default="examples/programbench_samples/samples.json",
        help="Path to ProgramBench sample metadata JSON",
    )
    parser.add_argument(
        "--instances",
        nargs="*",
        default=[],
        help="Explicit ProgramBench instance ids to run",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="Number of catalog samples to run when --instances is omitted",
    )
    parser.add_argument("--runs", default="runs/programbench_mini_lab", help="Run-session root")
    parser.add_argument("--config", default="config/settings.yaml", help="ReBuilder config path")
    parser.add_argument("--max-repairs", type=int, default=None, help="Override repair iterations")
    parser.add_argument(
        "--static-output-assets",
        choices=["config", "enabled", "disabled", "both"],
        default="config",
        help="Override static output assets mode or run both enabled/disabled ablation variants",
    )
    parser.add_argument(
        "--ablation-output",
        default=None,
        help="Output directory for paired ablation report when --static-output-assets both",
    )
    parser.add_argument(
        "--prepare-missing",
        action="store_true",
        help="Prepare missing cleanroom workspaces before running",
    )
    parser.add_argument(
        "--pull",
        action="store_true",
        help="Pull missing task_cleanroom images during preparation",
    )
    return parser.parse_args()


def select_mini_lab_samples(
    catalog: list[ProgramBenchSample],
    instances: list[str],
    limit: int | None,
) -> list[ProgramBenchSample]:
    if instances:
        return [select_sample(catalog, instance_id) for instance_id in instances]
    bounded_limit = max(0, limit or 0)
    return catalog[:bounded_limit]


def ensure_workspace(
    sample: ProgramBenchSample,
    run_root: Path,
    prepare_missing: bool,
    pull: bool,
) -> Path:
    session_root = run_root / sample.instance_id
    workspace = session_root / "workspace"
    manifest = session_root / "session.json"
    if manifest.exists() and workspace.exists():
        try:
            CleanroomWorkspace.load(workspace)
            return workspace
        except CleanroomWorkspaceError:
            if not prepare_missing:
                raise
            shutil.rmtree(session_root)
    if not prepare_missing:
        raise FileNotFoundError(
            f"Missing prepared workspace for {sample.instance_id}: {workspace}. "
            "Pass --prepare-missing to export task_cleanroom workspaces."
        )
    prepared = ProgramBenchTaskAdapter().prepare(sample=sample, run_root=run_root, pull=pull)
    return prepared.session.workspace_path


def run_command(command: list[str]) -> None:
    result = subprocess.run(command, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(command)}")


def select_asset_variants(
    run_root: Path,
    static_output_assets: Literal["config", "enabled", "disabled", "both"],
) -> list[tuple[str, Path, Literal["config", "enabled", "disabled"]]]:
    if static_output_assets == "both":
        return [
            ("assets_enabled", run_root / "assets_enabled", "enabled"),
            ("assets_disabled", run_root / "assets_disabled", "disabled"),
        ]
    return [("default", run_root, static_output_assets)]


def write_ablation_report(
    enabled_report,
    disabled_report,
    output_dir: Path,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    enabled_by_id = {row.task_id: row for row in enabled_report.rows}
    disabled_by_id = {row.task_id: row for row in disabled_report.rows}
    shared_ids = sorted(set(enabled_by_id) & set(disabled_by_id))

    rows: list[dict[str, float | str | None]] = []
    for task_id in shared_ids:
        enabled_row = enabled_by_id[task_id]
        disabled_row = disabled_by_id[task_id]
        enabled_holdout = enabled_row.holdout_resolved_rate
        disabled_holdout = disabled_row.holdout_resolved_rate
        holdout_delta = None
        if enabled_holdout is not None and disabled_holdout is not None:
            holdout_delta = enabled_holdout - disabled_holdout
        rows.append(
            {
                "task_id": task_id,
                "enabled_resolved_rate": enabled_row.resolved_rate,
                "disabled_resolved_rate": disabled_row.resolved_rate,
                "resolved_rate_delta": enabled_row.resolved_rate - disabled_row.resolved_rate,
                "enabled_holdout_rate": enabled_holdout,
                "disabled_holdout_rate": disabled_holdout,
                "holdout_rate_delta": holdout_delta,
            }
        )

    payload = {
        "task_count": len(rows),
        "enabled_average_resolved_rate": enabled_report.average_resolved_rate,
        "disabled_average_resolved_rate": disabled_report.average_resolved_rate,
        "average_resolved_rate_delta": enabled_report.average_resolved_rate - disabled_report.average_resolved_rate,
        "enabled_average_holdout_rate": enabled_report.average_holdout_resolved_rate,
        "disabled_average_holdout_rate": disabled_report.average_holdout_resolved_rate,
        "rows": rows,
    }

    json_path = output_dir / "mini_lab_ablation_summary.json"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# ProgramBench Mini-Lab Assets Ablation",
        "",
        f"- tasks: {payload['task_count']}",
        f"- avg resolved (enabled): {payload['enabled_average_resolved_rate']:.1%}",
        f"- avg resolved (disabled): {payload['disabled_average_resolved_rate']:.1%}",
        f"- avg resolved delta (enabled-disabled): {payload['average_resolved_rate_delta']:.1%}",
    ]
    enabled_avg_holdout = payload["enabled_average_holdout_rate"]
    disabled_avg_holdout = payload["disabled_average_holdout_rate"]
    if enabled_avg_holdout is not None and disabled_avg_holdout is not None:
        lines.append(f"- avg holdout (enabled): {enabled_avg_holdout:.1%}")
        lines.append(f"- avg holdout (disabled): {disabled_avg_holdout:.1%}")
        lines.append(f"- avg holdout delta (enabled-disabled): {enabled_avg_holdout - disabled_avg_holdout:.1%}")

    lines.extend(
        [
            "",
            "| task | enabled resolved | disabled resolved | delta | enabled holdout | disabled holdout | delta |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in rows:
        enabled_holdout_text = "-" if row["enabled_holdout_rate"] is None else f"{row['enabled_holdout_rate']:.1%}"
        disabled_holdout_text = "-" if row["disabled_holdout_rate"] is None else f"{row['disabled_holdout_rate']:.1%}"
        holdout_delta = row["holdout_rate_delta"]
        holdout_delta_text = "-" if holdout_delta is None else f"{holdout_delta:.1%}"
        lines.append(
            f"| {row['task_id']} | {row['enabled_resolved_rate']:.1%} | {row['disabled_resolved_rate']:.1%} | "
            f"{row['resolved_rate_delta']:.1%} | {enabled_holdout_text} | {disabled_holdout_text} | {holdout_delta_text} |"
        )

    markdown_path = output_dir / "mini_lab_ablation_summary.md"
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, markdown_path


def main() -> None:
    args = parse_args()
    catalog = load_sample_catalog(args.catalog)
    selected = select_mini_lab_samples(catalog, instances=args.instances, limit=args.limit)
    if not selected:
        raise SystemExit("No ProgramBench samples selected.")

    run_root = Path(args.runs)
    variants = select_asset_variants(run_root, args.static_output_assets)
    builder = MiniLabCommandBuilder(python_executable=sys.executable)
    reports: dict[str, object] = {}
    completed_by_variant: dict[str, list[str]] = {}

    for variant_name, variant_root, asset_mode in variants:
        completed_ids: list[str] = []
        for sample in selected:
            workspace = ensure_workspace(
                sample=sample,
                run_root=variant_root,
                prepare_missing=args.prepare_missing,
                pull=args.pull,
            )
            command = builder.build_rebuilder_command(
                sample=sample,
                workspace_path=workspace,
                config_path=Path(args.config),
                max_repairs=args.max_repairs,
                static_output_assets=asset_mode,
            )
            print(f"Running {sample.instance_id} ({variant_name})")
            run_command(command)
            completed_ids.append(sample.instance_id)
        report = MiniLabResultCollector().collect(variant_root, completed_ids)
        paths = MiniLabReportWriter().write(report, variant_root / "mini_lab")
        reports[variant_name] = report
        completed_by_variant[variant_name] = completed_ids
        print(f"[{variant_name}] Mini-lab JSON: {paths.json_path}")
        print(f"[{variant_name}] Mini-lab Markdown: {paths.markdown_path}")

    if args.static_output_assets == "both":
        output_dir = Path(args.ablation_output) if args.ablation_output else (run_root / "mini_lab_ablation")
        ablation_json, ablation_markdown = write_ablation_report(
            enabled_report=reports["assets_enabled"],
            disabled_report=reports["assets_disabled"],
            output_dir=output_dir,
        )
        print(f"Ablation JSON: {ablation_json}")
        print(f"Ablation Markdown: {ablation_markdown}")


if __name__ == "__main__":
    main()
