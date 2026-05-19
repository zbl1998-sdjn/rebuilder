import json
import math
import os
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
        "implementation_metadata": {
            "probe_axis_coverage": {
                "smoke_contract_axis_count": 2,
                "adaptive_axis_count": 3,
            }
        },
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_submission_holdout_gate_accepts_aggregate_holdout_result(tmp_path):
    result_path = write_result(tmp_path / "result.json", holdout_resolved_rate=0.9)

    summary = SubmissionHoldoutGate(min_rate=0.8).verify(result_path)

    assert summary.holdout_cases == 2
    assert summary.holdout_resolved_rate == 0.9
    assert summary.min_cases == 1


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


def test_submission_holdout_gate_rejects_too_few_holdout_cases(tmp_path):
    result_path = write_result(tmp_path / "result.json", holdout_cases=2, holdout_resolved_rate=1.0)

    with pytest.raises(HoldoutGateError, match="below required 3"):
        SubmissionHoldoutGate(min_rate=0.8, min_cases=3).verify(result_path)


def test_submission_holdout_gate_rejects_malformed_aggregate_values(tmp_path):
    result_path = write_result(
        tmp_path / "result.json",
        holdout_cases="not-an-int",
        holdout_resolved_rate="not-a-float",
    )

    with pytest.raises(HoldoutGateError, match="holdout"):
        SubmissionHoldoutGate(min_rate=0.8, min_cases=3).verify(result_path)


def test_submission_holdout_gate_rejects_non_finite_holdout_rate(tmp_path):
    result_path = write_result(tmp_path / "result.json", holdout_cases=10, holdout_resolved_rate="nan")

    with pytest.raises(HoldoutGateError, match="holdout"):
        SubmissionHoldoutGate(min_rate=0.8).verify(result_path)


def test_submission_holdout_gate_rejects_out_of_range_holdout_rate(tmp_path):
    result_path = write_result(tmp_path / "result.json", holdout_cases=10, holdout_resolved_rate=1.2)

    with pytest.raises(HoldoutGateError, match="holdout"):
        SubmissionHoldoutGate(min_rate=0.8).verify(result_path)

    result_path = write_result(tmp_path / "negative_result.json", holdout_cases=10, holdout_resolved_rate=-0.1)

    with pytest.raises(HoldoutGateError, match="holdout"):
        SubmissionHoldoutGate(min_rate=0.8).verify(result_path)


def test_submission_holdout_gate_rejects_fractional_holdout_cases(tmp_path):
    result_path = write_result(tmp_path / "result.json", holdout_cases=2.5, holdout_resolved_rate=1.0)

    with pytest.raises(HoldoutGateError, match="holdout"):
        SubmissionHoldoutGate(min_rate=0.8, min_cases=2).verify(result_path)


def test_submission_holdout_gate_rejects_non_object_result_payload(tmp_path):
    result_path = tmp_path / "result.json"
    result_path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")

    with pytest.raises(HoldoutGateError, match="holdout"):
        SubmissionHoldoutGate(min_rate=0.8).verify(result_path)


def test_submission_holdout_gate_rejects_invalid_json_result_payload(tmp_path):
    result_path = tmp_path / "result.json"
    result_path.write_text("{", encoding="utf-8")

    with pytest.raises(HoldoutGateError, match="holdout"):
        SubmissionHoldoutGate(min_rate=0.8).verify(result_path)


def test_submission_holdout_gate_rejects_too_few_smoke_contract_axes(tmp_path):
    result_path = write_result(
        tmp_path / "result.json",
        implementation_metadata={
            "probe_axis_coverage": {
                "smoke_contract_axis_count": 1,
                "adaptive_axis_count": 4,
            }
        },
    )

    with pytest.raises(HoldoutGateError, match="smoke-contract axes"):
        SubmissionHoldoutGate(min_rate=0.8, min_smoke_contract_axes=2).verify(result_path)


def test_submission_holdout_gate_rejects_fractional_smoke_contract_axes(tmp_path):
    result_path = write_result(
        tmp_path / "result.json",
        implementation_metadata={
            "probe_axis_coverage": {
                "smoke_contract_axis_count": 2.5,
                "adaptive_axis_count": 4,
            }
        },
    )

    with pytest.raises(HoldoutGateError, match="smoke-contract axes"):
        SubmissionHoldoutGate(min_rate=0.8, min_smoke_contract_axes=2).verify(result_path)


def test_submission_holdout_gate_rejects_missing_runtime_smoke_dimensions(tmp_path):
    result_path = write_result(
        tmp_path / "result.json",
        implementation_metadata={
            "probe_axis_coverage": {
                "smoke_contract_axis_count": 2,
                "adaptive_axis_count": 4,
            },
            "runtime_smoke": {
                "status": "passed",
                "input_dimensions": ["args"],
            },
        },
    )

    with pytest.raises(HoldoutGateError, match="runtime-smoke dimensions"):
        SubmissionHoldoutGate(
            min_rate=0.8,
            required_runtime_smoke_dimensions=("args", "input_files"),
        ).verify(result_path)


def test_submission_holdout_gate_accepts_required_runtime_smoke_dimensions(tmp_path):
    result_path = write_result(
        tmp_path / "result.json",
        implementation_metadata={
            "probe_axis_coverage": {
                "smoke_contract_axis_count": 2,
                "adaptive_axis_count": 4,
            },
            "runtime_smoke": {
                "status": "passed",
                "input_dimensions": ["input_files", "args"],
            },
        },
    )

    summary = SubmissionHoldoutGate(
        min_rate=0.8,
        required_runtime_smoke_dimensions=("args", "input_files"),
    ).verify(result_path)

    assert summary.runtime_smoke_status == "passed"
    assert summary.runtime_smoke_input_dimensions == ("args", "input_files")
    assert summary.required_runtime_smoke_dimensions == ("args", "input_files")


@pytest.mark.parametrize(
    ("threshold_kwargs", "message"),
    [
        ({"min_rate": -0.1}, "min_rate must be non-negative"),
        ({"min_rate": math.nan}, "min_rate must be non-negative"),
        ({"min_rate": 1.1}, "min_rate must be between 0 and 1"),
        ({"min_cases": -1}, "min_cases must be non-negative"),
        ({"min_cases": 1.5}, "min_cases must be a non-negative integer"),
        ({"min_smoke_contract_axes": -1}, "min_smoke_contract_axes must be non-negative"),
        ({"min_smoke_contract_axes": 1.5}, "min_smoke_contract_axes must be a non-negative integer"),
    ],
)
def test_submission_holdout_gate_rejects_negative_thresholds(threshold_kwargs, message):
    with pytest.raises(ValueError, match=message):
        SubmissionHoldoutGate(**threshold_kwargs)


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


def test_package_submission_script_requires_min_smoke_contract_axes(tmp_path):
    generated = tmp_path / "generated"
    generated.mkdir()
    (generated / "main.py").write_text("print('ok')\n", encoding="utf-8")
    result_path = write_result(
        tmp_path / "result.json",
        implementation_metadata={
            "probe_axis_coverage": {
                "smoke_contract_axis_count": 1,
                "adaptive_axis_count": 4,
            }
        },
    )

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
            "--min-smoke-contract-axes",
            "2",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "smoke-contract axes" in result.stderr
    assert not (tmp_path / "out" / "sample" / "submission.tar.gz").exists()


def test_package_submission_script_requires_runtime_smoke_dimensions(tmp_path):
    generated = tmp_path / "generated"
    generated.mkdir()
    (generated / "main.py").write_text("print('ok')\n", encoding="utf-8")
    result_path = write_result(
        tmp_path / "result.json",
        implementation_metadata={
            "probe_axis_coverage": {
                "smoke_contract_axis_count": 2,
                "adaptive_axis_count": 4,
            },
            "runtime_smoke": {
                "status": "passed",
                "input_dimensions": ["args"],
            },
        },
    )

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
            "--require-runtime-smoke-dimensions",
            "args,input_files",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "runtime-smoke dimensions" in result.stderr
    assert not (tmp_path / "out" / "sample" / "submission.tar.gz").exists()


def test_package_submission_script_requires_min_holdout_cases(tmp_path):
    generated = tmp_path / "generated"
    generated.mkdir()
    (generated / "main.py").write_text("print('ok')\n", encoding="utf-8")
    result_path = write_result(tmp_path / "result.json", holdout_cases=2, holdout_resolved_rate=1.0)

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
            "--min-holdout-cases",
            "3",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "holdout" in result.stderr.lower()
    assert "below required 3" in result.stderr
    assert not (tmp_path / "out" / "sample" / "submission.tar.gz").exists()


def test_package_submission_script_can_require_holdout_improvement(tmp_path):
    generated = tmp_path / "generated"
    generated.mkdir()
    (generated / "main.py").write_text("print('ok')\n", encoding="utf-8")
    runs = tmp_path / "runs"
    best = runs / "best" / "result.json"
    current = runs / "current" / "result.json"
    best.parent.mkdir(parents=True)
    current.parent.mkdir(parents=True)
    write_result(best, holdout_cases=10, holdout_resolved_rate=0.8)
    write_result(current, holdout_cases=10, holdout_resolved_rate=0.75)

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
            str(current),
            "--min-holdout-rate",
            "0.7",
            "--min-holdout-cases",
            "10",
            "--require-holdout-improvement",
            "--holdout-history-root",
            str(runs),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "holdout improvement" in result.stderr.lower()
    assert not (tmp_path / "out" / "sample" / "submission.tar.gz").exists()


def test_package_submission_script_can_require_low_generalization_risk(tmp_path):
    generated = tmp_path / "generated"
    generated.mkdir()
    (generated / "main.py").write_text("print('ok')\n", encoding="utf-8")
    runs = tmp_path / "runs"
    baselines = tmp_path / "baselines"
    baselines.mkdir()
    (baselines / "sample.baseline.json").write_text(
        json.dumps(
            {
                "instance_id": "sample",
                "official": {
                    "score": 8,
                    "pass_rate": 0.08,
                    "passed_tests": 8,
                    "total_tests": 100,
                },
            }
        ),
        encoding="utf-8",
    )
    best = runs / "best" / "result.json"
    latest = runs / "latest" / "result.json"
    best.parent.mkdir(parents=True)
    latest.parent.mkdir(parents=True)
    write_result(best, holdout_cases=10, holdout_resolved_rate=0.9)
    write_result(
        latest,
        holdout_cases=12,
        holdout_resolved_rate=0.4,
        implementation_metadata={
            "probe_axis_coverage": {
                "smoke_contract_axis_count": 17,
                "adaptive_axis_count": 15,
            }
        },
    )
    os.utime(best, (1_700_000_100, 1_700_000_100))
    os.utime(latest, (1_700_000_200, 1_700_000_200))

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
            str(best),
            "--min-holdout-rate",
            "0.8",
            "--min-holdout-cases",
            "10",
            "--max-generalization-risk",
            "low",
            "--generalization-risk-root",
            str(runs),
            "--baseline-root",
            str(baselines),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "generalization risk" in result.stderr.lower()
    assert "new_axis_expansion_regression" in result.stderr
    assert not (tmp_path / "out" / "sample" / "submission.tar.gz").exists()


@pytest.mark.parametrize(
    "flag_and_value",
    [
        ("--min-holdout-rate", "-0.1"),
        ("--min-holdout-rate", "nan"),
        ("--min-holdout-rate", "1.1"),
        ("--min-holdout-cases", "-1"),
        ("--min-smoke-contract-axes", "-1"),
        ("--min-holdout-improvement-delta", "-0.01"),
        ("--min-holdout-improvement-delta", "nan"),
    ],
)
def test_package_submission_script_rejects_negative_gate_thresholds(tmp_path, flag_and_value):
    generated = tmp_path / "generated"
    generated.mkdir()
    (generated / "main.py").write_text("print('ok')\n", encoding="utf-8")
    result_path = write_result(tmp_path / "result.json", holdout_cases=10, holdout_resolved_rate=1.0)
    flag, value = flag_and_value

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
            flag,
            value,
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "must be" in result.stderr
    assert not (tmp_path / "out" / "sample" / "submission.tar.gz").exists()
