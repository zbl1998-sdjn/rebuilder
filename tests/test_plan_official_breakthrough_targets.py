import importlib
import json
import os
import subprocess
import sys

import pytest


def load_module():
    try:
        return importlib.import_module("scripts.plan_official_breakthrough_targets")
    except ModuleNotFoundError:
        pytest.fail("scripts.plan_official_breakthrough_targets is not implemented yet")


def write_result(
    path,
    task_id,
    holdout_rate,
    holdout_cases,
    *,
    timestamp=1_700_000_000,
    smoke_contract_axis_count=0,
    runtime_smoke=None,
):
    target = path / task_id / "generated" / task_id
    target.mkdir(parents=True)
    result_path = target / "result.json"
    metadata = {
        "probe_axis_coverage": {
            "smoke_contract_axis_count": smoke_contract_axis_count,
        },
    }
    if runtime_smoke is not None:
        metadata["runtime_smoke"] = runtime_smoke
    result_path.write_text(
        json.dumps(
            {
                "task_id": task_id,
                "status": "failed",
                "resolved_rate": holdout_rate,
                "holdout_resolved_rate": holdout_rate,
                "holdout_cases": holdout_cases,
                "probes_conducted": 12,
                "iterations_used": 2,
                "implementation_metadata": metadata,
            }
        ),
        encoding="utf-8",
    )
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
        payload["notes"] = f"do not print {secret_marker}"
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_collect_targets_prioritizes_gate_ready_then_restorable_then_weak(tmp_path):
    module = load_module()
    runs = tmp_path / "runs"
    baselines = tmp_path / "baselines"

    write_baseline(baselines / "ready.baseline.json", "task.ready", 25)
    write_result(runs / "ready", "task.ready", 0.85, 12, timestamp=1_700_000_300)

    write_baseline(baselines / "restore.baseline.json", "task.restore", 3)
    write_result(runs / "restore_old", "task.restore", 0.92, 12, timestamp=1_700_000_100)
    write_result(runs / "restore_new", "task.restore", 0.55, 12, timestamp=1_700_000_200)

    write_baseline(baselines / "weak.baseline.json", "task.weak", 0)
    write_result(runs / "weak", "task.weak", 0.20, 10, timestamp=1_700_000_250)

    rows = module.collect_official_breakthrough_targets(runs, baselines)

    assert [(row.task_id, row.target_class) for row in rows[:3]] == [
        ("task.ready", "ready_baseline_gate"),
        ("task.restore", "restore_historical_gate"),
        ("task.weak", "weak_cleanroom_rerun"),
    ]
    assert rows[0].official_score == 25
    assert rows[1].latest_holdout_resolved_rate == 0.55
    assert rows[1].best_holdout_resolved_rate == 0.92


def test_collect_targets_keeps_baseline_tasks_without_reliable_holdout(tmp_path):
    module = load_module()
    runs = tmp_path / "runs"
    baselines = tmp_path / "baselines"
    write_baseline(baselines / "missing.baseline.json", "task.missing", 17)

    rows = module.collect_official_breakthrough_targets(runs, baselines)

    assert [(row.task_id, row.target_class) for row in rows] == [
        ("task.missing", "missing_reliable_holdout")
    ]
    assert rows[0].latest_holdout_resolved_rate is None
    assert rows[0].best_holdout_resolved_rate is None


def test_cli_outputs_aggregate_only_plan_and_guarded_weak_commands(tmp_path):
    runs = tmp_path / "runs"
    baselines = tmp_path / "baselines"
    write_baseline(
        baselines / "weak.baseline.json",
        "task.weak",
        0,
        secret_marker="hidden-case-name",
    )
    write_result(runs / "weak", "task.weak", 0.20, 10)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/plan_official_breakthrough_targets.py",
            "--runs",
            str(runs),
            "--baseline-root",
            str(baselines),
            "--include-next-command",
            "--rerun-root",
            "runs/next",
            "--rerun-require-runtime-smoke-dimensions",
            "args,input_files",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "official score" in result.stdout
    assert "task.weak" in result.stdout
    assert "weak_cleanroom_rerun" in result.stdout
    assert "python scripts/run_weak_task_cleanroom_rerun.py task.weak" in result.stdout
    assert "--runs runs/next/task.weak --dry-run" in result.stdout
    assert "--require-runtime-smoke-dimensions args,input_files" in result.stdout
    assert "hidden-case-name" not in result.stdout


def test_cli_includes_restore_gate_audit_command(tmp_path):
    runs = tmp_path / "runs"
    baselines = tmp_path / "baselines"
    write_baseline(baselines / "restore.baseline.json", "task.restore", 3)
    best = write_result(runs / "restore_old", "task.restore", 0.92, 12, timestamp=1_700_000_100)
    write_result(runs / "restore_new", "task.restore", 0.55, 12, timestamp=1_700_000_200)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/plan_official_breakthrough_targets.py",
            "--runs",
            str(runs),
            "--baseline-root",
            str(baselines),
            "--official-eval-root",
            "runs/official",
            "--include-next-command",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "restore_historical_gate" in result.stdout
    assert "python scripts/audit_official_eval_gate.py" in result.stdout
    assert str(best) in result.stdout
    assert "--official-eval-root runs/official" in result.stdout
    assert "--allow-existing-official" in result.stdout


def test_cli_can_render_guarded_restore_ablation_dry_run_command(tmp_path):
    runs = tmp_path / "runs"
    baselines = tmp_path / "baselines"
    write_baseline(baselines / "restore.baseline.json", "task.restore", 3)
    write_result(runs / "restore_old", "task.restore", 0.92, 12, timestamp=1_700_000_100)
    write_result(runs / "restore_new", "task.restore", 0.55, 12, timestamp=1_700_000_200)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/plan_official_breakthrough_targets.py",
            "--runs",
            str(runs),
            "--baseline-root",
            str(baselines),
            "--include-next-command",
            "--include-restore-ablation-command",
            "--restore-ablation-root",
            "runs/restore_next",
            "--restore-ablation-min-smoke-contract-axes",
            "2",
            "--restore-ablation-require-runtime-smoke-dimensions",
            "args,input_files",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "restore_historical_gate" in result.stdout
    assert "python scripts/run_official_strategy_ablation.py task.restore" in result.stdout
    assert "--runs runs/restore_next/task.restore" in result.stdout
    assert "--variants baseline_no_adaptive adaptive_profile adaptive_deep" in result.stdout
    assert "--skip-official-eval" in result.stdout
    assert "--require-holdout-improvement" in result.stdout
    assert f"--holdout-history-root {runs.as_posix()}" in result.stdout
    assert "--max-generalization-risk low" in result.stdout
    assert f"--generalization-risk-root {runs.as_posix()}" in result.stdout
    assert f"--baseline-root {baselines.as_posix()}" in result.stdout
    assert "--min-smoke-contract-axes 2" in result.stdout
    assert "--require-runtime-smoke-dimensions" in result.stdout
    assert "args,input_files" in result.stdout
    assert "--dry-run" in result.stdout


def test_cli_outputs_cleanroom_json_plan_with_guarded_commands(tmp_path):
    runs = tmp_path / "runs"
    baselines = tmp_path / "baselines"
    write_baseline(baselines / "ready.baseline.json", "task.ready", 25)
    write_result(runs / "ready", "task.ready", 0.85, 12, timestamp=1_700_000_300)
    write_baseline(baselines / "restore.baseline.json", "task.restore", 3)
    write_result(runs / "restore_old", "task.restore", 0.92, 12, timestamp=1_700_000_100)
    write_result(runs / "restore_new", "task.restore", 0.55, 12, timestamp=1_700_000_200)
    write_baseline(
        baselines / "weak.baseline.json",
        "task.weak",
        0,
        secret_marker="hidden-case-name",
    )
    write_result(runs / "weak", "task.weak", 0.20, 10, timestamp=1_700_000_250)
    write_baseline(baselines / "missing.baseline.json", "task.missing", 17)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/plan_official_breakthrough_targets.py",
            "--runs",
            str(runs),
            "--baseline-root",
            str(baselines),
            "--include-next-command",
            "--include-restore-ablation-command",
            "--rerun-root",
            "runs/next",
            "--restore-ablation-root",
            "runs/restore_next",
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "hidden-case-name" not in result.stdout
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == 1
    assert payload["row_count"] == 4
    assert payload["total_row_count"] == 4
    rows = payload["rows"]
    assert [(row["task_id"], row["target_class"]) for row in rows] == [
        ("task.ready", "ready_baseline_gate"),
        ("task.restore", "restore_historical_gate"),
        ("task.weak", "weak_cleanroom_rerun"),
        ("task.missing", "missing_reliable_holdout"),
    ]
    assert rows[0]["official"] == {
        "score": 25,
        "pass_rate": 0.25,
        "passed_tests": 25,
        "total_tests": 100,
    }
    assert rows[1]["latest_holdout"] == {"resolved_rate": 0.55, "cases": 12}
    assert rows[1]["best_holdout"] == {"resolved_rate": 0.92, "cases": 12}
    assert "scripts/run_official_strategy_ablation.py task.restore" in rows[1]["next_command"]
    assert "--skip-official-eval" in rows[1]["next_command"]
    assert "--dry-run" in rows[1]["next_command"]
    assert "scripts/run_weak_task_cleanroom_rerun.py task.weak" in rows[2]["next_command"]
    assert rows[3]["next_command"] is None


def test_cli_can_render_missing_holdout_dry_run_command(tmp_path):
    runs = tmp_path / "runs"
    baselines = tmp_path / "baselines"
    write_baseline(baselines / "missing.baseline.json", "task.missing", 17)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/plan_official_breakthrough_targets.py",
            "--runs",
            str(runs),
            "--baseline-root",
            str(baselines),
            "--include-next-command",
            "--include-missing-holdout-command",
            "--missing-holdout-rerun-root",
            "runs/missing_next",
            "--missing-holdout-min-smoke-contract-axes",
            "2",
            "--missing-holdout-require-runtime-smoke-dimensions",
            "args,input_files",
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    [row] = payload["rows"]
    assert row["target_class"] == "missing_reliable_holdout"
    assert "python scripts/run_missing_holdout_cleanroom_rerun.py task.missing" in row["next_command"]
    assert "--runs runs/missing_next/task.missing" in row["next_command"]
    assert "--min-smoke-contract-axes 2" in row["next_command"]
    assert "--require-runtime-smoke-dimensions" in row["next_command"]
    assert "args,input_files" in row["next_command"]
    assert "--dry-run" in row["next_command"]
    assert "--require-holdout-improvement" not in row["next_command"]
    assert "--official-eval-root" not in row["next_command"]


def test_cli_can_render_strict_ready_baseline_upgrade_command(tmp_path):
    runs = tmp_path / "runs"
    baselines = tmp_path / "baselines"
    write_baseline(baselines / "ready.baseline.json", "task.ready", 25)
    write_result(runs / "ready", "task.ready", 0.85, 12)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/plan_official_breakthrough_targets.py",
            "--runs",
            str(runs),
            "--baseline-root",
            str(baselines),
            "--include-next-command",
            "--baseline-upgrade-min-smoke-contract-axes",
            "1",
            "--baseline-upgrade-require-holdout-improvement",
            "--baseline-upgrade-min-holdout-improvement-delta",
            "0.02",
            "--baseline-upgrade-require-runtime-smoke-dimensions",
            "args,input_files",
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    [row] = payload["rows"]
    assert row["target_class"] == "ready_baseline_gate"
    assert "python scripts/rank_programbench_candidates.py" in row["next_command"]
    assert "--official-eligible-only" in row["next_command"]
    assert "--allow-existing-official" in row["next_command"]
    assert "--latest-per-task" in row["next_command"]
    assert "--min-smoke-contract-axes 1" in row["next_command"]
    assert "--require-runtime-smoke-dimensions" in row["next_command"]
    assert "args,input_files" in row["next_command"]
    assert "--require-holdout-improvement" in row["next_command"]
    assert "--min-holdout-improvement-delta 0.02" in row["next_command"]


def test_json_ready_rows_expose_strict_baseline_gate_blockers(tmp_path):
    runs = tmp_path / "runs"
    baselines = tmp_path / "baselines"
    runtime_smoke = {
        "status": "passed",
        "case_count": 4,
        "contract_case_count": 4,
        "input_dimensions": ["args", "input_files"],
    }
    write_baseline(baselines / "ready.baseline.json", "task.ready", 25)
    write_result(
        runs / "ready_old",
        "task.ready",
        0.90,
        12,
        timestamp=1_700_000_100,
        smoke_contract_axis_count=2,
        runtime_smoke=runtime_smoke,
    )
    write_result(
        runs / "ready_new",
        "task.ready",
        0.85,
        12,
        timestamp=1_700_000_300,
        smoke_contract_axis_count=2,
        runtime_smoke=runtime_smoke,
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/plan_official_breakthrough_targets.py",
            "--runs",
            str(runs),
            "--baseline-root",
            str(baselines),
            "--include-next-command",
            "--baseline-upgrade-min-smoke-contract-axes",
            "1",
            "--baseline-upgrade-require-holdout-improvement",
            "--baseline-upgrade-min-holdout-improvement-delta",
            "0.02",
            "--baseline-upgrade-require-runtime-smoke-dimensions",
            "args,input_files",
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    [row] = payload["rows"]
    assert row["target_class"] == "ready_baseline_gate"
    gate = row["baseline_upgrade_gate"]
    assert gate["checked"] is True
    assert gate["eligible"] is False
    assert gate["reason"] == "holdout_not_improved"
    assert gate["blockers"] == ["holdout_not_improved"]
    assert gate["required_runtime_smoke_dimensions"] == ["args", "input_files"]
    assert gate["candidate"]["runtime_smoke_status"] == "passed"
    assert gate["candidate"]["runtime_smoke_input_dimensions"] == ["args", "input_files"]
