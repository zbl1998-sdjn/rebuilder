from core.programbench.samples import ProgramBenchSample, parse_dockerhub_repository
import subprocess
import sys


def test_parse_dockerhub_repository_extracts_project_identity():
    sample = parse_dockerhub_repository(
        {
            "name": "ajeetdsouza_1776_zoxide.67ca1bc",
            "description": "ProgramBench task: ajeetdsouza/zoxide (MIT) - behavioral test environment",
            "pull_count": 222,
            "storage_size": 707229054,
            "last_updated": "2026-05-03T23:30:37.912486Z",
        }
    )

    assert sample.instance_id == "ajeetdsouza__zoxide.67ca1bc"
    assert sample.source_project == "ajeetdsouza/zoxide"
    assert sample.cleanroom_image == "programbench/ajeetdsouza_1776_zoxide.67ca1bc:task_cleanroom"
    assert sample.task_image == "programbench/ajeetdsouza_1776_zoxide.67ca1bc:task"


def test_programbench_sample_round_trips_to_json():
    sample = ProgramBenchSample(
        instance_id="owner__repo.abcdef0",
        docker_repository="owner_1776_repo.abcdef0",
        source_project="owner/repo",
        cleanroom_image="programbench/owner_1776_repo.abcdef0:task_cleanroom",
        task_image="programbench/owner_1776_repo.abcdef0:task",
        description="ProgramBench task: owner/repo (MIT) - behavioral test environment",
    )

    assert ProgramBenchSample.model_validate_json(sample.model_dump_json()) == sample


def test_fetch_script_can_show_help_from_repo_root():
    result = subprocess.run(
        [sys.executable, "scripts/fetch_programbench_samples.py", "--help"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Fetch ProgramBench sample metadata" in result.stdout
