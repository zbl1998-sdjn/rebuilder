import importlib
import json
import os
import subprocess
import sys

import pytest


def load_module():
    try:
        return importlib.import_module("scripts.audit_generalization_risk")
    except ModuleNotFoundError:
        pytest.fail("scripts.audit_generalization_risk is not implemented yet")


def write_result(
    path,
    task_id,
    holdout_rate,
    holdout_cases,
    *,
    local_resolved_rate=None,
    timestamp=1_700_000_000,
    smoke_axes=0,
    adaptive_axes=0,
    official_eval_summary=None,
    secret_marker=None,
):
    target = path / task_id / "generated" / task_id
    target.mkdir(parents=True)
    payload = {
        "task_id": task_id,
        "status": "failed",
        "resolved_rate": holdout_rate if local_resolved_rate is None else local_resolved_rate,
        "holdout_resolved_rate": holdout_rate,
        "holdout_cases": holdout_cases,
        "probes_conducted": 20,
        "iterations_used": 2,
        "implementation_metadata": {
            "probe_axis_coverage": {
                "smoke_contract_axis_count": smoke_axes,
                "adaptive_axis_count": adaptive_axes,
                "smoke_contract_axes": [
                    f"fixture.axis_{index}" for index in range(smoke_axes)
                ],
                "adaptive_axes": [
                    f"fixture.axis_{index}" for index in range(adaptive_axes)
                ],
            }
        },
    }
    if secret_marker:
        payload["holdout_failures"] = [{"name": secret_marker, "expected": "secret"}]
        payload["official_eval"] = {"test_results": [{"name": secret_marker}]}
    if official_eval_summary is not None:
        payload["official_eval_summary"] = official_eval_summary
    result_path = target / "result.json"
    result_path.write_text(json.dumps(payload), encoding="utf-8")
    os.utime(result_path, (timestamp, timestamp))
    return result_path


def write_baseline(path, task_id, score, *, secret_marker=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "instance_id": task_id,
        "official": {
            "score": score,
            "pass_rate": score / 100,
            "passed_tests": score,
            "total_tests": 100,
        },
    }
    if secret_marker:
        payload["official"]["hidden_failure_details"] = [{"name": secret_marker}]
    path.write_text(json.dumps(payload), encoding="utf-8")


def official_summary(score, *, passed_tests=None, total_tests=100):
    passed_tests = score if passed_tests is None else passed_tests
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


def test_collect_generalization_risk_blocks_regressed_axis_expansion(tmp_path):
    module = load_module()
    runs = tmp_path / "runs"
    baselines = tmp_path / "baselines"
    write_baseline(baselines / "restore.baseline.json", "task.restore", 8)
    write_result(
        runs / "old",
        "task.restore",
        0.9,
        10,
        timestamp=1_700_000_100,
        official_eval_summary=official_summary(12),
    )
    latest = write_result(
        runs / "new",
        "task.restore",
        0.4,
        12,
        timestamp=1_700_000_200,
        smoke_axes=17,
        adaptive_axes=15,
        official_eval_summary=official_summary(12),
    )

    rows = module.collect_generalization_risks(runs, baselines)

    assert len(rows) == 1
    row = rows[0]
    assert row.task_id == "task.restore"
    assert row.risk_level == "high"
    assert row.block_official_eval is True
    assert row.risk_reason == "new_axis_expansion_regression"
    assert row.latest_result_path == latest
    assert row.required_next_action == "ablate_axis_expansion_before_official_eval"


def test_collect_generalization_risk_allows_gate_ready_non_regression(tmp_path):
    module = load_module()
    runs = tmp_path / "runs"
    baselines = tmp_path / "baselines"
    write_baseline(baselines / "ready.baseline.json", "task.ready", 25)
    latest = write_result(
        runs / "latest",
        "task.ready",
        0.85,
        12,
        timestamp=1_700_000_200,
        smoke_axes=3,
        adaptive_axes=2,
    )

    rows = module.collect_generalization_risks(runs, baselines)

    assert len(rows) == 1
    row = rows[0]
    assert row.task_id == "task.ready"
    assert row.risk_level == "low"
    assert row.block_official_eval is False
    assert row.risk_reason == "latest_reliable_gate_pass"
    assert row.latest_result_path == latest
    assert row.latest_local_resolved_rate == 0.85
    assert row.latest_local_holdout_gap == 0.0


def test_collect_generalization_risk_blocks_gate_ready_local_holdout_gap(tmp_path):
    module = load_module()
    runs = tmp_path / "runs"
    baselines = tmp_path / "baselines"
    write_baseline(baselines / "ready.baseline.json", "task.ready", 25)
    latest = write_result(
        runs / "latest",
        "task.ready",
        0.82,
        12,
        local_resolved_rate=1.0,
        timestamp=1_700_000_200,
        smoke_axes=3,
        adaptive_axes=2,
    )

    rows = module.collect_generalization_risks(
        runs,
        baselines,
        max_local_holdout_gap=0.1,
    )

    assert len(rows) == 1
    row = rows[0]
    assert row.task_id == "task.ready"
    assert row.risk_level == "high"
    assert row.block_official_eval is True
    assert row.risk_reason == "local_holdout_gap_too_high"
    assert row.required_next_action == "expand_unseen_holdout_before_official_eval"
    assert row.latest_result_path == latest
    assert row.latest_local_resolved_rate == 1.0
    assert row.latest_local_holdout_gap == pytest.approx(0.18)


def test_collect_generalization_risk_blocks_ready_candidate_not_above_official_baseline(tmp_path):
    module = load_module()
    runs = tmp_path / "runs"
    baselines = tmp_path / "baselines"
    write_baseline(baselines / "ready.baseline.json", "task.ready", 62)
    latest = write_result(
        runs / "latest",
        "task.ready",
        0.9,
        12,
        timestamp=1_700_000_200,
        smoke_axes=3,
        adaptive_axes=2,
        official_eval_summary=official_summary(62, passed_tests=62, total_tests=100),
    )

    rows = module.collect_generalization_risks(runs, baselines)

    assert len(rows) == 1
    row = rows[0]
    assert row.task_id == "task.ready"
    assert row.risk_level == "high"
    assert row.block_official_eval is True
    assert row.risk_reason == "official_not_above_baseline"
    assert row.required_next_action == "improve_candidate_above_baseline_before_official_eval"
    assert row.latest_result_path == latest


def test_cli_outputs_aggregate_only_risk_table_and_fails_on_high(tmp_path):
    runs = tmp_path / "runs"
    baselines = tmp_path / "baselines"
    write_baseline(
        baselines / "restore.baseline.json",
        "task.restore",
        8,
        secret_marker="hidden-baseline-case",
    )
    write_result(
        runs / "old",
        "task.restore",
        0.9,
        10,
        timestamp=1_700_000_100,
        official_eval_summary=official_summary(12),
        secret_marker="hidden-best-case",
    )
    write_result(
        runs / "new",
        "task.restore",
        0.4,
        12,
        timestamp=1_700_000_200,
        smoke_axes=17,
        adaptive_axes=15,
        official_eval_summary=official_summary(12),
        secret_marker="hidden-latest-case",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/audit_generalization_risk.py",
            "--runs",
            str(runs),
            "--baseline-root",
            str(baselines),
            "--fail-on-risk",
            "high",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "generalization risk" in result.stdout
    assert "task.restore" in result.stdout
    assert "high" in result.stdout
    assert "block_official_eval" in result.stdout
    assert "new_axis_expansion_regression" in result.stdout
    assert "hidden-baseline-case" not in result.stdout
    assert "hidden-best-case" not in result.stdout
    assert "hidden-latest-case" not in result.stdout


def test_cli_outputs_aggregate_only_json_risk_payload_and_fails_on_high(tmp_path):
    runs = tmp_path / "runs"
    baselines = tmp_path / "baselines"
    write_baseline(
        baselines / "restore.baseline.json",
        "task.restore",
        8,
        secret_marker="hidden-baseline-case",
    )
    write_result(
        runs / "old",
        "task.restore",
        0.9,
        10,
        timestamp=1_700_000_100,
        official_eval_summary=official_summary(12),
        secret_marker="hidden-best-case",
    )
    latest = write_result(
        runs / "new",
        "task.restore",
        0.4,
        12,
        timestamp=1_700_000_200,
        smoke_axes=17,
        adaptive_axes=15,
        official_eval_summary=official_summary(12),
        secret_marker="hidden-latest-case",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/audit_generalization_risk.py",
            "--runs",
            str(runs),
            "--baseline-root",
            str(baselines),
            "--fail-on-risk",
            "high",
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "hidden-baseline-case" not in result.stdout
    assert "hidden-best-case" not in result.stdout
    assert "hidden-latest-case" not in result.stdout
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == 1
    assert payload["row_count"] == 1
    assert payload["total_row_count"] == 1
    [row] = payload["rows"]
    assert row["task_id"] == "task.restore"
    assert row["official"] == {
        "score": 8,
        "pass_rate": 0.08,
        "passed_tests": 8,
        "total_tests": 100,
    }
    assert row["risk_level"] == "high"
    assert row["risk_reason"] == "new_axis_expansion_regression"
    assert row["block_official_eval"] is True
    assert row["required_next_action"] == "ablate_axis_expansion_before_official_eval"
    assert row["latest_local_resolved_rate"] == 0.4
    assert row["latest_local_holdout_gap"] == 0.0
    assert row["latest_holdout"] == {"resolved_rate": 0.4, "cases": 12}
    assert row["best_holdout"] == {"resolved_rate": 0.9, "cases": 10}
    assert row["latest_result_path"] == str(latest)


def test_cli_json_can_filter_to_task(tmp_path):
    runs = tmp_path / "runs"
    baselines = tmp_path / "baselines"
    for task_id, baseline_name in (
        ("task.one", "one.baseline.json"),
        ("task.two", "two.baseline.json"),
    ):
        write_baseline(baselines / baseline_name, task_id, 8)
        write_result(
            runs / f"{task_id}_old",
            task_id,
            0.9,
            10,
            timestamp=1_700_000_100,
            official_eval_summary=official_summary(12),
        )
        write_result(
            runs / f"{task_id}_new",
            task_id,
            0.4,
            12,
            timestamp=1_700_000_200,
            smoke_axes=17,
            adaptive_axes=15,
            official_eval_summary=official_summary(12),
        )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/audit_generalization_risk.py",
            "--runs",
            str(runs),
            "--baseline-root",
            str(baselines),
            "--task",
            "task.two",
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["row_count"] == 1
    assert payload["total_row_count"] == 1
    [row] = payload["rows"]
    assert row["task_id"] == "task.two"
