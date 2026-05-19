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


def test_load_sample_catalog_skips_malformed_entries(tmp_path):
    catalog_path = tmp_path / "samples.json"
    catalog_path.write_text(
        json.dumps(
            [
                "not an object",
                {
                    "instance_id": "owner__repo.abcdef0",
                    "docker_repository": "owner_1776_repo.abcdef0",
                    "source_project": "owner/repo",
                    "cleanroom_image": "programbench/owner_1776_repo.abcdef0:task_cleanroom",
                    "task_image": "programbench/owner_1776_repo.abcdef0:task",
                },
                {
                    "instance_id": "missing-required-fields",
                },
            ]
        ),
        encoding="utf-8",
    )

    samples = load_sample_catalog(catalog_path)

    assert [sample.instance_id for sample in samples] == ["owner__repo.abcdef0"]


def test_load_sample_catalog_rejects_non_list_payload(tmp_path):
    catalog_path = tmp_path / "samples.json"
    catalog_path.write_text(json.dumps({"instance_id": "owner__repo.abcdef0"}), encoding="utf-8")

    with pytest.raises(ValueError, match="ProgramBench sample catalog must contain a JSON list"):
        load_sample_catalog(catalog_path)


def test_load_sample_catalog_rejects_invalid_json(tmp_path):
    catalog_path = tmp_path / "samples.json"
    catalog_path.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(ValueError, match="ProgramBench sample catalog must be valid JSON"):
        load_sample_catalog(catalog_path)


def test_load_sample_catalog_rejects_duplicate_instance_ids(tmp_path):
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
                },
                {
                    "instance_id": "owner__repo.abcdef0",
                    "docker_repository": "other_1776_repo.abcdef0",
                    "source_project": "other/repo",
                    "cleanroom_image": "programbench/other_1776_repo.abcdef0:task_cleanroom",
                    "task_image": "programbench/other_1776_repo.abcdef0:task",
                },
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Duplicate ProgramBench sample instance_id: owner__repo.abcdef0"):
        load_sample_catalog(catalog_path)


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
