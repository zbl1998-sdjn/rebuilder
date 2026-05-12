from pathlib import Path
from types import SimpleNamespace

from core.experiments.mini_lab import MiniLabReport, MiniLabRow
from scripts.run_programbench_mini_lab import (
    ensure_workspace,
    select_asset_variants,
    select_mini_lab_samples,
    write_ablation_report,
)
from core.programbench.samples import ProgramBenchSample


def sample(instance_id: str) -> ProgramBenchSample:
    return ProgramBenchSample(
        instance_id=instance_id,
        docker_repository=instance_id.replace("__", "_1776_"),
        source_project="owner/repo",
        cleanroom_image=f"programbench/{instance_id}:task_cleanroom",
        task_image=f"programbench/{instance_id}:task",
    )


def test_select_mini_lab_samples_prefers_explicit_instances():
    catalog = [sample("one"), sample("two"), sample("three")]

    selected = select_mini_lab_samples(catalog, instances=["three", "one"], limit=None)

    assert [item.instance_id for item in selected] == ["three", "one"]


def test_select_mini_lab_samples_uses_limit_when_no_instances():
    catalog = [sample("one"), sample("two"), sample("three")]

    selected = select_mini_lab_samples(catalog, instances=[], limit=2)

    assert [item.instance_id for item in selected] == ["one", "two"]


def test_select_asset_variants_returns_two_roots_for_both_mode(tmp_path):
    variants = select_asset_variants(tmp_path, "both")

    assert variants == [
        ("assets_enabled", tmp_path / "assets_enabled", "enabled"),
        ("assets_disabled", tmp_path / "assets_disabled", "disabled"),
    ]


def test_write_ablation_report_writes_delta_summary(tmp_path):
    enabled_report = MiniLabReport(
        rows=[
            MiniLabRow(
                task_id="task.one",
                status="failed",
                resolved_rate=0.8,
                holdout_resolved_rate=0.5,
                result_path=Path("runs/assets_enabled/task.one/generated/task.one/result.json"),
            )
        ]
    )
    disabled_report = MiniLabReport(
        rows=[
            MiniLabRow(
                task_id="task.one",
                status="failed",
                resolved_rate=0.6,
                holdout_resolved_rate=0.25,
                result_path=Path("runs/assets_disabled/task.one/generated/task.one/result.json"),
            )
        ]
    )

    json_path, markdown_path = write_ablation_report(enabled_report, disabled_report, tmp_path)
    payload = json_path.read_text(encoding="utf-8")
    markdown = markdown_path.read_text(encoding="utf-8")

    assert "average_resolved_rate_delta" in payload
    assert "task.one" in markdown
    assert "25.0%" in markdown


def test_ensure_workspace_rebuilds_stale_incomplete_workspace(tmp_path, monkeypatch):
    stale_root = tmp_path / "task.one"
    stale_workspace = stale_root / "workspace"
    stale_workspace.mkdir(parents=True)
    (stale_root / "session.json").write_text("{}", encoding="utf-8")
    (stale_root / "stale.txt").write_text("old", encoding="utf-8")

    class FakeAdapter:
        def prepare(self, sample, run_root, pull):
            workspace = Path(run_root) / sample.instance_id / "workspace"
            workspace.mkdir(parents=True)
            (workspace / "executable").write_text("#!/bin/sh\n", encoding="utf-8")
            (workspace / "README.md").write_text("docs", encoding="utf-8")
            return SimpleNamespace(session=SimpleNamespace(workspace_path=workspace))

    monkeypatch.setattr("scripts.run_programbench_mini_lab.ProgramBenchTaskAdapter", FakeAdapter)

    workspace = ensure_workspace(sample("task.one"), tmp_path, prepare_missing=True, pull=False)

    assert workspace == stale_workspace
    assert (workspace / "executable").exists()
    assert not (stale_root / "stale.txt").exists()
