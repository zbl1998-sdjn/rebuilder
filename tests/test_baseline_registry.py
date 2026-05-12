import json
import tarfile

from core.evaluation.programbench import ProgramBenchEvalSummary
from core.experiments.baseline import BaselineRecorder


def test_baseline_recorder_writes_aggregate_only_record(tmp_path):
    local_result = tmp_path / "result.json"
    local_result.write_text(
        json.dumps(
            {
                "task_id": "owner__repo.abcdef0",
                "status": "failed",
                "resolved_rate": 0.167,
                "iterations_used": 1,
                "probes_conducted": 19,
                "holdout_resolved_rate": None,
            }
        ),
        encoding="utf-8",
    )
    official_eval = tmp_path / "eval.json"
    official_eval.write_text(
        json.dumps(
            {
                "test_results": [
                    {"status": "passed", "name": "hidden_a"},
                    {"status": "failed", "name": "hidden_b"},
                ],
                "warnings": ["WARN: one branch warning"],
                "error_code": None,
            }
        ),
        encoding="utf-8",
    )
    submission = tmp_path / "submission.tar.gz"
    with tarfile.open(submission, "w:gz") as tar:
        pass

    record_path = BaselineRecorder().record(
        instance_id="owner__repo.abcdef0",
        local_result_path=local_result,
        official_eval_path=official_eval,
        submission_archive_path=submission,
        output_dir=tmp_path / "baselines",
        model="glm-5.1",
        config_path="config/smoke_glm.yaml",
        notes="first official non-zero check",
    )

    payload = json.loads(record_path.read_text(encoding="utf-8"))
    assert payload["instance_id"] == "owner__repo.abcdef0"
    assert payload["model"] == "glm-5.1"
    assert payload["local"]["resolved_rate"] == 0.167
    assert payload["official"]["passed_tests"] == 1
    assert payload["official"]["total_tests"] == 2
    assert payload["official"]["pass_rate"] == 0.5
    assert payload["official"]["score"] == 50
    assert payload["submission"]["sha256"]
    assert "test_results" not in json.dumps(payload)
    assert "hidden_a" not in json.dumps(payload)


def test_baseline_recorder_uses_filtered_official_score(tmp_path, monkeypatch):
    local_result = tmp_path / "result.json"
    local_result.write_text(
        json.dumps(
            {
                "task_id": "owner__repo.abcdef0",
                "status": "success",
                "resolved_rate": 1.0,
                "iterations_used": 1,
                "probes_conducted": 23,
                "holdout_resolved_rate": 1.0,
            }
        ),
        encoding="utf-8",
    )
    official_eval = tmp_path / "eval.json"
    official_eval.write_text("{}", encoding="utf-8")
    submission = tmp_path / "submission.tar.gz"
    with tarfile.open(submission, "w:gz") as tar:
        pass

    summary = ProgramBenchEvalSummary(
        total_tests=508,
        passed_tests=393,
        pass_rate=393 / 508,
        score=0.77,
        fully_resolved=False,
        almost_resolved=False,
        warnings=[],
    )
    monkeypatch.setattr(
        BaselineRecorder,
        "_load_official_summary",
        lambda self, instance_id, official_eval_path: summary,
    )

    record_path = BaselineRecorder().record(
        instance_id="owner__repo.abcdef0",
        local_result_path=local_result,
        official_eval_path=official_eval,
        submission_archive_path=submission,
        output_dir=tmp_path / "baselines",
        model="glm-5.1",
        config_path="config/smoke_glm.yaml",
        notes="filtered official score",
    )

    payload = json.loads(record_path.read_text(encoding="utf-8"))
    assert payload["official"]["passed_tests"] == 393
    assert payload["official"]["total_tests"] == 508
    assert payload["official"]["score"] == 77
