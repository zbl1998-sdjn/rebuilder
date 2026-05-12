import json
import sys
from pathlib import Path

import pytest

from core.experiments.mini_lab import (
    MiniLabCommandBuilder,
    MiniLabResultCollector,
    MiniLabReportWriter,
)
from core.programbench.samples import ProgramBenchSample


def write_result(run_root: Path, instance_id: str, payload: dict) -> Path:
    result_path = run_root / instance_id / "generated" / instance_id / "result.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(payload), encoding="utf-8")
    return result_path


def sample(instance_id: str, image: str = "programbench/example:task_cleanroom") -> ProgramBenchSample:
    return ProgramBenchSample(
        instance_id=instance_id,
        docker_repository="example",
        source_project="owner/repo",
        cleanroom_image=image,
        task_image="programbench/example:task",
    )


def test_mini_lab_collector_summarizes_result_files(tmp_path):
    write_result(
        tmp_path,
        "task.one",
        {
            "task_id": "task.one",
            "status": "failed",
            "resolved_rate": 0.25,
            "holdout_resolved_rate": 0.5,
            "iterations_used": 1,
            "probes_conducted": 8,
            "exploration_cases": 6,
            "holdout_cases": 2,
            "implementation_metadata": {
                "static_output_assets_enabled": False,
                "contract_asset_status": "disabled",
            },
        },
    )
    write_result(
        tmp_path,
        "task.two",
        {
            "task_id": "task.two",
            "status": "success",
            "resolved_rate": 1.0,
            "holdout_resolved_rate": None,
            "iterations_used": 0,
            "probes_conducted": 4,
            "exploration_cases": 4,
            "holdout_cases": 0,
        },
    )

    report = MiniLabResultCollector().collect(tmp_path, ["task.one", "task.two"])

    assert report.task_count == 2
    assert report.average_resolved_rate == 0.625
    assert report.average_holdout_resolved_rate == 0.5
    assert report.rows[0].result_path.name == "result.json"
    assert report.rows[0].holdout_cases == 2
    assert report.rows[0].static_output_assets_enabled is False
    assert report.rows[0].contract_asset_status == "disabled"


def test_mini_lab_report_writer_writes_json_and_markdown(tmp_path):
    write_result(
        tmp_path,
        "task.one",
        {"task_id": "task.one", "status": "failed", "resolved_rate": 0.25},
    )
    report = MiniLabResultCollector().collect(tmp_path, ["task.one"])

    paths = MiniLabReportWriter().write(report, tmp_path / "mini_lab")

    payload = json.loads(paths.json_path.read_text(encoding="utf-8"))
    markdown = paths.markdown_path.read_text(encoding="utf-8")
    assert payload["task_count"] == 1
    assert payload["rows"][0]["task_id"] == "task.one"
    assert "ProgramBench Mini-Lab Summary" in markdown
    assert "task.one" in markdown
    assert "assets" in markdown


def test_mini_lab_command_builder_uses_cleanroom_image(tmp_path):
    workspace = tmp_path / "runs" / "task.one" / "workspace"
    command = MiniLabCommandBuilder(python_executable=sys.executable).build_rebuilder_command(
        sample=sample("task.one"),
        workspace_path=workspace,
        config_path=Path("config/smoke_glm.yaml"),
        max_repairs=1,
    )

    assert command[:2] == [sys.executable, "main.py"]
    assert "--task" in command
    assert str(workspace) in command
    assert "--reference-docker-image" in command
    assert "programbench/example:task_cleanroom" in command
    assert "--max-repairs" in command


def test_mini_lab_command_builder_rejects_task_image(tmp_path):
    with pytest.raises(ValueError, match="task_cleanroom"):
        MiniLabCommandBuilder().build_rebuilder_command(
            sample=sample("task.one", image="programbench/example:task"),
            workspace_path=tmp_path / "workspace",
            config_path=Path("config/smoke_glm.yaml"),
        )


def test_mini_lab_command_builder_applies_static_asset_override(tmp_path):
    command = MiniLabCommandBuilder(python_executable=sys.executable).build_rebuilder_command(
        sample=sample("task.one"),
        workspace_path=tmp_path / "workspace",
        config_path=Path("config/smoke_glm.yaml"),
        static_output_assets="enabled",
    )

    assert "--static-output-assets" in command
    assert "enabled" in command
