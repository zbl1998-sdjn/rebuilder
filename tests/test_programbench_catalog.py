import json
import subprocess
import sys

import pytest

from core.programbench.catalog import load_sample_catalog, select_sample


def test_load_sample_catalog_and_select_by_instance_id(tmp_path):
    catalog_path = tmp_path / "samples.json"
    catalog_path.write_text(
        json.dumps(
            [
                {
                    "instance_id": "owner__repo.abcdef0",
                    "docker_repository": "owner_1776_repo.abcdef0",
                    "source_project": "owner/repo",
                    "cleanroom_image": "programbench/owner_1776_repo.abcdef0:task_cleanroom",
                    "task_image": "programbench/owner_1776_repo.abcdef0:task",
                }
            ]
        ),
        encoding="utf-8",
    )

    samples = load_sample_catalog(catalog_path)
    selected = select_sample(samples, "owner__repo.abcdef0")

    assert selected.source_project == "owner/repo"


def test_select_sample_raises_for_unknown_instance():
    with pytest.raises(KeyError, match="missing"):
        select_sample([], "missing")


def test_prepare_programbench_task_script_can_show_help():
    result = subprocess.run(
        [sys.executable, "scripts/prepare_programbench_task.py", "--help"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Prepare a ProgramBench cleanroom workspace" in result.stdout
