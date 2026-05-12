import json
import subprocess
import sys

import pytest

from core.submission.gate import HoldoutGateError, SubmissionHoldoutGate


def write_result(path, **overrides):
    payload = {
        "task_id": "sample",
        "resolved_rate": 1.0,
        "exploration_cases": 8,
        "holdout_cases": 2,
        "holdout_resolved_rate": 1.0,
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_submission_holdout_gate_accepts_aggregate_holdout_result(tmp_path):
    result_path = write_result(tmp_path / "result.json", holdout_resolved_rate=0.9)

    summary = SubmissionHoldoutGate(min_rate=0.8).verify(result_path)

    assert summary.holdout_cases == 2
    assert summary.holdout_resolved_rate == 0.9


def test_submission_holdout_gate_rejects_missing_holdout(tmp_path):
    result_path = write_result(
        tmp_path / "result.json",
        holdout_cases=0,
        holdout_resolved_rate=None,
    )

    with pytest.raises(HoldoutGateError, match="holdout"):
        SubmissionHoldoutGate(min_rate=0.8).verify(result_path)


def test_submission_holdout_gate_rejects_below_threshold(tmp_path):
    result_path = write_result(tmp_path / "result.json", holdout_resolved_rate=0.5)

    with pytest.raises(HoldoutGateError, match="below"):
        SubmissionHoldoutGate(min_rate=0.8).verify(result_path)


def test_package_submission_script_requires_passing_holdout_gate(tmp_path):
    generated = tmp_path / "generated"
    generated.mkdir()
    (generated / "main.py").write_text("print('ok')\n", encoding="utf-8")
    result_path = write_result(tmp_path / "result.json", holdout_resolved_rate=0.4)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/package_submission.py",
            "sample",
            "--generated",
            str(generated),
            "--output",
            str(tmp_path / "out"),
            "--result",
            str(result_path),
            "--min-holdout-rate",
            "0.8",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "holdout" in result.stderr.lower()
    assert not (tmp_path / "out" / "sample" / "submission.tar.gz").exists()
