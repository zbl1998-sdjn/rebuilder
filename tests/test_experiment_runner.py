import json

from core.experiments.runner import ExperimentRunner
from core.programbench.samples import ProgramBenchSample
from core.session import RunSession


def test_experiment_runner_writes_dry_run_report(tmp_path):
    session = RunSession.create(tmp_path / "runs", "owner__repo.abcdef0", "programbench_cleanroom")
    sample = ProgramBenchSample(
        instance_id="owner__repo.abcdef0",
        docker_repository="owner_1776_repo.abcdef0",
        source_project="owner/repo",
        cleanroom_image="programbench/owner_1776_repo.abcdef0:task_cleanroom",
        task_image="programbench/owner_1776_repo.abcdef0:task",
    )

    report = ExperimentRunner().write_dry_run_report(
        session=session,
        sample=sample,
        architecture_variant="baseline",
    )

    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["instance_id"] == "owner__repo.abcdef0"
    assert payload["architecture_variant"] == "baseline"
    assert payload["cleanroom_image"].endswith(":task_cleanroom")
    assert payload["uses_hidden_tests"] is False
