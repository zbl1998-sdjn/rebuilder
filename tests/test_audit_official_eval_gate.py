import json
import math
import subprocess
import sys

import pytest

from scripts.audit_official_eval_gate import audit_result, parse_args


def write_result(
    path,
    *,
    task_id="task.pass",
    holdout_rate=0.9,
    holdout_cases=12,
    smoke_axes=None,
    runtime_smoke=None,
    official_eval_summary=None,
):
    metadata = {}
    if smoke_axes is not None:
        metadata["probe_axis_coverage"] = {"smoke_contract_axis_count": smoke_axes}
    if runtime_smoke is not None:
        metadata["runtime_smoke"] = runtime_smoke
    path.parent.mkdir(parents=True)
    payload = {
        "task_id": task_id,
        "status": "failed",
        "resolved_rate": 0.9,
        "holdout_resolved_rate": holdout_rate,
        "holdout_cases": holdout_cases,
        "probes_conducted": 50,
        "iterations_used": 3,
        "implementation_metadata": metadata,
    }
    if official_eval_summary is not None:
        payload["official_eval_summary"] = official_eval_summary
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def write_baseline(path, task_id, *, score, passed_tests=1, total_tests=10):
    path.mkdir(parents=True, exist_ok=True)
    (path / f"{task_id}.baseline.json").write_text(
        json.dumps(
            {
                "instance_id": task_id,
                "official": {
                    "score": score,
                    "passed_tests": passed_tests,
                    "total_tests": total_tests,
                    "pass_rate": passed_tests / total_tests,
                    "fully_resolved": False,
                    "almost_resolved": False,
                },
            }
        ),
        encoding="utf-8",
    )


def official_summary(score, *, passed_tests=2, total_tests=10):
    return {
        "counted": {
            "score": score,
            "passed_tests": passed_tests,
            "total_tests": total_tests,
            "pass_rate": passed_tests / total_tests,
            "fully_resolved": False,
            "almost_resolved": False,
        }
    }


def test_audit_result_accepts_aggregate_holdout_gate_pass(tmp_path):
    result_path = write_result(tmp_path / "runs" / "task.pass" / "result.json")

    audit = audit_result(
        result_path,
        official_eval_root=tmp_path / "official",
        baseline_root=tmp_path / "baselines",
        min_holdout_rate=0.8,
        min_holdout_cases=10,
    )

    assert audit["task_id"] == "task.pass"
    assert audit["eligible"] is True
    assert audit["reason"] == "eligible"
    assert audit["holdout_cases"] == 12
    assert audit["holdout_resolved_rate"] == 0.9


def test_audit_result_blocks_already_official_task(tmp_path):
    result_path = write_result(tmp_path / "runs" / "task.done" / "result.json", task_id="task.done")
    eval_dir = tmp_path / "official" / "submission" / "task.done"
    eval_dir.mkdir(parents=True)
    (eval_dir / "task.done.eval.json").write_text("{}", encoding="utf-8")

    audit = audit_result(
        result_path,
        official_eval_root=tmp_path / "official",
        baseline_root=tmp_path / "baselines",
        min_holdout_rate=0.8,
        min_holdout_cases=10,
    )

    assert audit["eligible"] is False
    assert audit["reason"] == "already_official"


def test_audit_result_can_allow_existing_official_baseline_upgrade(tmp_path):
    write_baseline(tmp_path / "baselines", "task.done", score=10, passed_tests=10, total_tests=100)
    result_path = write_result(
        tmp_path / "runs" / "task.done" / "result.json",
        task_id="task.done",
        official_eval_summary=official_summary(12, passed_tests=12, total_tests=100),
    )
    eval_dir = tmp_path / "official" / "submission" / "task.done"
    eval_dir.mkdir(parents=True)
    (eval_dir / "task.done.eval.json").write_text("{}", encoding="utf-8")

    audit = audit_result(
        result_path,
        official_eval_root=tmp_path / "official",
        baseline_root=tmp_path / "baselines",
        allow_existing_official=True,
        min_holdout_rate=0.8,
        min_holdout_cases=10,
    )

    assert audit["eligible"] is True
    assert audit["reason"] == "eligible_baseline_upgrade"
    assert audit["has_official_eval"] is True


def test_audit_result_blocks_existing_official_when_candidate_does_not_beat_baseline(tmp_path):
    write_baseline(tmp_path / "baselines", "task.done", score=12, passed_tests=12, total_tests=100)
    result_path = write_result(
        tmp_path / "runs" / "task.done" / "result.json",
        task_id="task.done",
        official_eval_summary=official_summary(10, passed_tests=10, total_tests=100),
    )

    audit = audit_result(
        result_path,
        official_eval_root=tmp_path / "official",
        baseline_root=tmp_path / "baselines",
        allow_existing_official=True,
        min_holdout_rate=0.8,
        min_holdout_cases=10,
    )

    assert audit["eligible"] is False
    assert audit["reason"] == "official_not_above_baseline"
    assert audit["has_official_eval"] is True


def test_audit_result_blocks_insufficient_smoke_axis_coverage_when_required(tmp_path):
    result_path = write_result(
        tmp_path / "runs" / "task.low_smoke" / "result.json",
        task_id="task.low_smoke",
        smoke_axes=1,
    )

    audit = audit_result(
        result_path,
        official_eval_root=tmp_path / "official",
        baseline_root=tmp_path / "baselines",
        min_holdout_rate=0.8,
        min_holdout_cases=10,
        min_smoke_contract_axes=2,
    )

    assert audit["eligible"] is False
    assert audit["reason"] == "insufficient_smoke_contract_axes"
    assert audit["smoke_contract_axis_count"] == 1
    assert audit["min_smoke_contract_axes"] == 2


def test_audit_result_blocks_missing_runtime_smoke_dimensions_when_required(tmp_path):
    result_path = write_result(tmp_path / "runs" / "task.no_runtime" / "result.json")

    audit = audit_result(
        result_path,
        official_eval_root=tmp_path / "official",
        baseline_root=tmp_path / "baselines",
        min_holdout_rate=0.8,
        min_holdout_cases=10,
        required_runtime_smoke_dimensions=("args", "input_files"),
    )

    assert audit["eligible"] is False
    assert audit["reason"] == "runtime_smoke_not_passed"
    assert audit["runtime_smoke_status"] == "missing"
    assert audit["runtime_smoke_input_dimensions"] == []
    assert audit["required_runtime_smoke_dimensions"] == ["args", "input_files"]


def test_audit_result_blocks_insufficient_runtime_smoke_dimensions(tmp_path):
    result_path = write_result(
        tmp_path / "runs" / "task.partial_runtime" / "result.json",
        runtime_smoke={"status": "passed", "input_dimensions": ["args"]},
    )

    audit = audit_result(
        result_path,
        official_eval_root=tmp_path / "official",
        baseline_root=tmp_path / "baselines",
        min_holdout_rate=0.8,
        min_holdout_cases=10,
        required_runtime_smoke_dimensions="args,input_files",
    )

    assert audit["eligible"] is False
    assert audit["reason"] == "insufficient_runtime_smoke_dimensions"
    assert audit["runtime_smoke_status"] == "passed"
    assert audit["runtime_smoke_input_dimensions"] == ["args"]
    assert audit["required_runtime_smoke_dimensions"] == ["args", "input_files"]


def test_audit_result_can_require_holdout_improvement_delta(tmp_path):
    runs = tmp_path / "runs"
    write_result(
        runs / "old" / "task.pass" / "result.json",
        task_id="task.pass",
        holdout_rate=0.89,
        holdout_cases=12,
    )
    result_path = write_result(
        runs / "new" / "task.pass" / "result.json",
        task_id="task.pass",
        holdout_rate=0.90,
        holdout_cases=12,
    )

    audit = audit_result(
        result_path,
        official_eval_root=tmp_path / "official",
        baseline_root=tmp_path / "baselines",
        min_holdout_rate=0.8,
        min_holdout_cases=10,
        require_holdout_improvement=True,
        holdout_history_root=runs,
        min_holdout_improvement_delta=0.02,
    )

    assert audit["eligible"] is False
    assert audit["reason"] == "holdout_delta_below_min"
    assert audit["holdout_improvement_reason"] == "delta_below_min"
    assert audit["holdout_delta_from_best_previous"] == 0.90 - 0.89
    assert audit["holdout_best_previous_resolved_rate"] == 0.89
    assert audit["holdout_best_previous_cases"] == 12
    assert audit["holdout_best_previous_result_path"] == str(runs / "old" / "task.pass" / "result.json")


def test_audit_official_eval_gate_cli_returns_nonzero_for_low_holdout(tmp_path):
    result_path = write_result(
        tmp_path / "runs" / "task.low" / "result.json",
        task_id="task.low",
        holdout_rate=0.4,
        holdout_cases=12,
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/audit_official_eval_gate.py",
            str(result_path),
            "--official-eval-root",
            str(tmp_path / "official"),
            "--baseline-root",
            str(tmp_path / "baselines"),
            "--min-holdout-rate",
            "0.8",
            "--min-holdout-cases",
            "10",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    payload = json.loads(result.stdout)
    assert result.returncode == 2
    assert payload["eligible"] is False
    assert payload["reason"] == "low_holdout_rate"
    assert "hidden" not in result.stdout.lower()


def test_audit_official_eval_gate_cli_returns_json_for_invalid_result_payload(tmp_path):
    result_path = tmp_path / "runs" / "task.invalid" / "result.json"
    result_path.parent.mkdir(parents=True)
    result_path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/audit_official_eval_gate.py",
            str(result_path),
            "--official-eval-root",
            str(tmp_path / "official"),
            "--baseline-root",
            str(tmp_path / "baselines"),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    payload = json.loads(result.stdout)
    assert result.returncode == 2
    assert payload["eligible"] is False
    assert payload["reason"] == "invalid_result"
    assert "traceback" not in result.stderr.lower()


def test_audit_official_eval_gate_cli_accepts_runtime_smoke_dimension_gate(tmp_path):
    result_path = write_result(
        tmp_path / "runs" / "task.runtime" / "result.json",
        runtime_smoke={"status": "passed", "input_dimensions": ["args"]},
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/audit_official_eval_gate.py",
            str(result_path),
            "--official-eval-root",
            str(tmp_path / "official"),
            "--baseline-root",
            str(tmp_path / "baselines"),
            "--require-runtime-smoke-dimensions",
            "args,input_files",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    payload = json.loads(result.stdout)
    assert result.returncode == 2
    assert payload["eligible"] is False
    assert payload["reason"] == "insufficient_runtime_smoke_dimensions"
    assert payload["required_runtime_smoke_dimensions"] == ["args", "input_files"]


@pytest.mark.parametrize(
    ("threshold_kwargs", "message"),
    [
        ({"min_holdout_rate": -0.1}, "min_holdout_rate must be a finite rate between 0 and 1"),
        ({"min_holdout_rate": math.nan}, "min_holdout_rate must be a finite rate between 0 and 1"),
        ({"min_holdout_rate": 1.2}, "min_holdout_rate must be a finite rate between 0 and 1"),
        ({"min_holdout_cases": -1}, "min_holdout_cases must be non-negative"),
        ({"min_holdout_cases": math.nan}, "min_holdout_cases must be"),
        ({"min_holdout_cases": 1.5}, "min_holdout_cases must be"),
        ({"min_smoke_contract_axes": -1}, "min_smoke_contract_axes must be non-negative"),
        ({"min_smoke_contract_axes": math.nan}, "min_smoke_contract_axes must be"),
        ({"min_smoke_contract_axes": 1.5}, "min_smoke_contract_axes must be"),
        (
            {"required_runtime_smoke_dimensions": ("bad_dimension",)},
            "required_runtime_smoke_dimensions must contain only",
        ),
        ({"min_holdout_improvement_delta": -0.01}, "min_holdout_improvement_delta must be non-negative"),
        ({"min_holdout_improvement_delta": math.nan}, "min_holdout_improvement_delta must be non-negative"),
    ],
)
def test_audit_result_rejects_negative_thresholds(tmp_path, threshold_kwargs, message):
    result_path = write_result(tmp_path / "runs" / "task.pass" / "result.json")

    with pytest.raises(ValueError, match=message):
        audit_result(
            result_path,
            official_eval_root=tmp_path / "official",
            baseline_root=tmp_path / "baselines",
            **threshold_kwargs,
        )


@pytest.mark.parametrize(
    ("flag_and_value", "message"),
    [
        (("--min-holdout-rate", "-0.1"), "finite rate between 0 and 1"),
        (("--min-holdout-rate", "nan"), "finite rate between 0 and 1"),
        (("--min-holdout-cases", "-1"), "must be non-negative"),
        (("--min-smoke-contract-axes", "-1"), "must be non-negative"),
        (("--require-runtime-smoke-dimensions", "args,bad_dimension"), "must contain only"),
        (("--min-holdout-improvement-delta", "-0.01"), "must be non-negative"),
        (("--min-holdout-improvement-delta", "nan"), "must be non-negative"),
    ],
)
def test_audit_official_eval_gate_cli_rejects_negative_thresholds(tmp_path, flag_and_value, message):
    result_path = write_result(tmp_path / "runs" / "task.pass" / "result.json")
    flag, value = flag_and_value

    result = subprocess.run(
        [
            sys.executable,
            "scripts/audit_official_eval_gate.py",
            str(result_path),
            "--official-eval-root",
            str(tmp_path / "official"),
            "--baseline-root",
            str(tmp_path / "baselines"),
            flag,
            value,
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert message in result.stderr


def test_parse_args_rejects_out_of_range_holdout_rate():
    with pytest.raises(SystemExit):
        parse_args(["result.json", "--min-holdout-rate", "1.2"])
