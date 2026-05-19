import importlib
import json
import os
import subprocess
import sys

import pytest


def load_module():
    try:
        return importlib.import_module("scripts.audit_restore_targets")
    except ModuleNotFoundError:
        pytest.fail("scripts.audit_restore_targets is not implemented yet")


def write_result(
    path,
    task_id,
    holdout_rate,
    holdout_cases,
    *,
    timestamp=1_700_000_000,
    secret_marker=None,
    smoke_axes=0,
    adaptive_axes=0,
    smoke_axis_names=None,
    adaptive_axis_names=None,
    static_assets=False,
):
    smoke_axis_names = list(smoke_axis_names or [])
    adaptive_axis_names = list(adaptive_axis_names or [])
    target = path / task_id / "generated" / task_id
    target.mkdir(parents=True)
    payload = {
        "task_id": task_id,
        "status": "failed",
        "resolved_rate": holdout_rate,
        "holdout_resolved_rate": holdout_rate,
        "holdout_cases": holdout_cases,
        "probes_conducted": 12,
        "iterations_used": 2,
        "implementation_metadata": {
            "static_output_assets_enabled": static_assets,
            "probe_axis_coverage": {
                "smoke_contract_axis_count": smoke_axes,
                "adaptive_axis_count": adaptive_axes,
                "smoke_contract_axes": smoke_axis_names,
                "adaptive_axes": adaptive_axis_names,
            },
        },
    }
    if secret_marker:
        payload["holdout_failures"] = [{"name": secret_marker, "expected": "secret"}]
        payload["official_eval"] = {"test_results": [{"name": secret_marker}]}
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


def test_collect_restore_audits_reports_regression_and_gate_reasons(tmp_path):
    module = load_module()
    runs = tmp_path / "runs"
    baselines = tmp_path / "baselines"
    official = tmp_path / "official"
    write_baseline(baselines / "restore.baseline.json", "task.restore", 8)
    best = write_result(
        runs / "old",
        "task.restore",
        0.9,
        10,
        timestamp=1_700_000_100,
        smoke_axes=0,
        adaptive_axes=0,
    )
    latest = write_result(
        runs / "new",
        "task.restore",
        0.4,
        12,
        timestamp=1_700_000_200,
        smoke_axes=17,
        adaptive_axes=15,
    )

    rows = module.collect_restore_target_audits(
        runs,
        baselines,
        official_eval_root=official,
    )

    assert len(rows) == 1
    row = rows[0]
    assert row.task_id == "task.restore"
    assert row.official_score == 8
    assert row.best_result_path == best
    assert row.latest_result_path == latest
    assert row.regression_delta == pytest.approx(-0.5)
    assert row.best_gate_reason == "eligible_baseline_upgrade"
    assert row.latest_gate_reason == "low_holdout_rate"
    assert row.latest_smoke_contract_axis_count == 17
    assert row.latest_adaptive_axis_count == 15
    assert row.best_smoke_contract_axis_count == 0
    assert row.regression_signal == "new_axis_expansion_regression"
    assert row.next_action == "restore_historical_best_then_ablate_latest_changes"


def test_collect_restore_audits_reports_cleanroom_axis_deltas(tmp_path):
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
        smoke_axes=2,
        adaptive_axes=1,
        smoke_axis_names=["csv_table.basic", "csv_table.file_mode"],
        adaptive_axis_names=["csv_table.basic"],
    )
    write_result(
        runs / "new",
        "task.restore",
        0.4,
        12,
        timestamp=1_700_000_200,
        smoke_axes=2,
        adaptive_axes=2,
        smoke_axis_names=["csv_table.basic", "csv_table.quoted_fields"],
        adaptive_axis_names=["csv_table.basic", "json_transform.invalid_json"],
    )

    row = module.collect_restore_target_audits(runs, baselines)[0]

    assert row.added_smoke_contract_axes == ("csv_table.quoted_fields",)
    assert row.removed_smoke_contract_axes == ("csv_table.file_mode",)
    assert row.added_adaptive_axes == ("json_transform.invalid_json",)
    assert row.removed_adaptive_axes == ()
    assert row.added_axis_summary == "+smoke:csv_table.quoted_fields; +adaptive:json_transform.invalid_json"
    assert row.removed_axis_summary == "-smoke:csv_table.file_mode"
    assert row.axis_delta_action == "ablate_added_axis_domains:csv_table,json_transform"


def test_collect_restore_audits_can_filter_specific_tasks(tmp_path):
    module = load_module()
    runs = tmp_path / "runs"
    baselines = tmp_path / "baselines"
    write_baseline(baselines / "keep.baseline.json", "task.keep", 8)
    write_baseline(baselines / "drop.baseline.json", "task.drop", 9)
    write_result(runs / "old", "task.keep", 0.9, 10, timestamp=1_700_000_100)
    write_result(runs / "new", "task.keep", 0.4, 12, timestamp=1_700_000_200)
    write_result(runs / "old", "task.drop", 0.9, 10, timestamp=1_700_000_100)
    write_result(runs / "new", "task.drop", 0.4, 12, timestamp=1_700_000_200)

    rows = module.collect_restore_target_audits(
        runs,
        baselines,
        task_ids=("task.keep",),
    )

    assert len(rows) == 1
    assert rows[0].task_id == "task.keep"


def test_cli_outputs_aggregate_only_restore_table(tmp_path):
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
        secret_marker="hidden-best-case",
        smoke_axes=1,
        adaptive_axes=0,
        smoke_axis_names=["csv_table.file_mode"],
    )
    write_result(
        runs / "new",
        "task.restore",
        0.4,
        12,
        timestamp=1_700_000_200,
        secret_marker="hidden-latest-case",
        smoke_axes=2,
        adaptive_axes=1,
        smoke_axis_names=["csv_table.file_mode", "csv_table.quoted_fields"],
        adaptive_axis_names=["json_transform.invalid_json"],
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/audit_restore_targets.py",
            "--runs",
            str(runs),
            "--baseline-root",
            str(baselines),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "restore regression" in result.stdout
    assert "task.restore" in result.stdout
    assert "eligible_baseline_upgrade" in result.stdout
    assert "low_holdout_rate" in result.stdout
    assert "new_axis_expansion_regression" in result.stdout
    assert "2/1" in result.stdout
    assert "1/0" in result.stdout
    assert "+smoke:csv_table.quoted_fields" in result.stdout
    assert "+adaptive:json_transform.invalid_json" in result.stdout
    assert "axis action" in result.stdout
    assert "ablate_added_axis_domains:csv_table,json_transform" in result.stdout
    assert "hidden-baseline-case" not in result.stdout
    assert "hidden-best-case" not in result.stdout
    assert "hidden-latest-case" not in result.stdout


def test_cli_outputs_cleanroom_json_restore_actions(tmp_path):
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
        secret_marker="hidden-best-case",
        smoke_axes=2,
        adaptive_axes=1,
        smoke_axis_names=["csv_table.basic", "csv_table.file_mode"],
        adaptive_axis_names=["csv_table.basic"],
    )
    write_result(
        runs / "new",
        "task.restore",
        0.4,
        12,
        timestamp=1_700_000_200,
        secret_marker="hidden-latest-case",
        smoke_axes=2,
        adaptive_axes=2,
        smoke_axis_names=["csv_table.basic", "csv_table.quoted_fields"],
        adaptive_axis_names=["csv_table.basic", "json_transform.invalid_json"],
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/audit_restore_targets.py",
            "--runs",
            str(runs),
            "--baseline-root",
            str(baselines),
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == 1
    assert payload["row_count"] == 1
    assert payload["regression_signal_counts"] == {"new_axis_expansion_regression": 1}
    assert payload["axis_delta_action_counts"] == {
        "ablate_added_axis_domains:csv_table,json_transform": 1
    }
    row = payload["rows"][0]
    assert row["rank"] == 1
    assert row["task_id"] == "task.restore"
    assert row["official_score"] == 8
    assert row["latest_gate_reason"] == "low_holdout_rate"
    assert row["best_gate_reason"] == "eligible_baseline_upgrade"
    assert row["latest_holdout_resolved_rate"] == pytest.approx(0.4)
    assert row["best_holdout_resolved_rate"] == pytest.approx(0.9)
    assert row["added_smoke_contract_axes"] == ["csv_table.quoted_fields"]
    assert row["added_adaptive_axes"] == ["json_transform.invalid_json"]
    assert row["removed_smoke_contract_axes"] == ["csv_table.file_mode"]
    assert row["removed_adaptive_axes"] == []
    assert row["axis_delta_action"] == "ablate_added_axis_domains:csv_table,json_transform"
    assert row["regression_signal"] == "new_axis_expansion_regression"
    assert "result.json" in row["latest_result_path"]
    assert "result.json" in row["best_result_path"]
    assert "hidden-baseline-case" not in result.stdout
    assert "hidden-best-case" not in result.stdout
    assert "hidden-latest-case" not in result.stdout


def test_cli_json_can_filter_specific_restore_task(tmp_path):
    runs = tmp_path / "runs"
    baselines = tmp_path / "baselines"
    write_baseline(baselines / "keep.baseline.json", "task.keep", 8)
    write_baseline(baselines / "drop.baseline.json", "task.drop", 9)
    write_result(runs / "old", "task.keep", 0.9, 10, timestamp=1_700_000_100)
    write_result(runs / "new", "task.keep", 0.4, 12, timestamp=1_700_000_200)
    write_result(runs / "old", "task.drop", 0.9, 10, timestamp=1_700_000_100)
    write_result(runs / "new", "task.drop", 0.4, 12, timestamp=1_700_000_200)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/audit_restore_targets.py",
            "--runs",
            str(runs),
            "--baseline-root",
            str(baselines),
            "--task",
            "task.keep",
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
    assert payload["rows"][0]["task_id"] == "task.keep"
