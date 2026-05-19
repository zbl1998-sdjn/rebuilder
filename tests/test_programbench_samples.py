import json
import subprocess
import sys
from argparse import Namespace

import pytest

from core.programbench.samples import ProgramBenchSample, fetch_programbench_samples, parse_dockerhub_repository


class _FakeDockerHubResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_exc_info):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


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


def test_fetch_programbench_samples_skips_malformed_repository_entries(monkeypatch):
    def fake_urlopen(_request, timeout):
        assert timeout == 30
        return _FakeDockerHubResponse(
            {
                "results": [
                    "not a repository object",
                    {"description": "missing repository name"},
                    {"name": None, "description": "null repository name"},
                    {
                        "name": "owner_1776_repo.abcdef0",
                        "description": "ProgramBench task: owner/repo (MIT) - behavioral test environment",
                    },
                ],
                "next": None,
            }
        )

    monkeypatch.setattr("core.programbench.samples.urlopen", fake_urlopen)

    samples = fetch_programbench_samples(limit=1)

    assert [sample.instance_id for sample in samples] == ["owner__repo.abcdef0"]


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"results": {"name": "owner_1776_repo.abcdef0"}},
    ],
)
def test_fetch_programbench_samples_rejects_malformed_response_shape(monkeypatch, payload):
    def fake_urlopen(_request, timeout):
        assert timeout == 30
        return _FakeDockerHubResponse(payload)

    monkeypatch.setattr("core.programbench.samples.urlopen", fake_urlopen)

    with pytest.raises(ValueError, match="DockerHub response must contain a JSON list of repository results"):
        fetch_programbench_samples(limit=1)


def test_fetch_script_can_show_help_from_repo_root():
    result = subprocess.run(
        [sys.executable, "scripts/fetch_programbench_samples.py", "--help"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Fetch ProgramBench sample metadata" in result.stdout


def test_fetch_script_rejects_non_positive_limit_from_cli(tmp_path):
    output = tmp_path / "samples.json"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/fetch_programbench_samples.py",
            "--limit",
            "0",
            "--output",
            str(output),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "limit must be a positive integer" in result.stderr
    assert not output.exists()


def test_fetch_script_rejects_empty_positive_limit_catalog(tmp_path, monkeypatch):
    import scripts.fetch_programbench_samples as fetch_script

    output = tmp_path / "samples.json"
    monkeypatch.setattr(fetch_script, "fetch_programbench_samples", lambda limit: [])
    monkeypatch.setattr(
        fetch_script,
        "parse_args",
        lambda: Namespace(limit=2, output=str(output)),
    )

    with pytest.raises(SystemExit) as exc_info:
        fetch_script.main()

    assert "No valid ProgramBench sample records were fetched" in str(exc_info.value)
    assert not output.exists()
