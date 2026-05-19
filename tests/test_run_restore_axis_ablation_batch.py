import argparse
import importlib
import json
import os


def load_module():
    return importlib.import_module("scripts.run_restore_axis_ablation_batch")


def write_result(
    path,
    task_id,
    holdout_rate,
    holdout_cases,
    *,
    timestamp=1_700_000_000,
    smoke_axes=0,
    adaptive_axes=0,
    smoke_axis_names=None,
    adaptive_axis_names=None,
):
    target = path / task_id / "generated" / task_id
    target.mkdir(parents=True)
    smoke_axis_names = list(smoke_axis_names or [])
    adaptive_axis_names = list(adaptive_axis_names or [])
    result_path = target / "result.json"
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
                "implementation_metadata": {
                    "probe_axis_coverage": {
                        "smoke_contract_axis_count": smoke_axes,
                        "adaptive_axis_count": adaptive_axes,
                        "smoke_contract_axes": smoke_axis_names,
                        "adaptive_axes": adaptive_axis_names,
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    os.utime(result_path, (timestamp, timestamp))
    return result_path


def write_baseline(path, task_id, score):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "instance_id": task_id,
                "official": {
                    "score": score,
                    "pass_rate": score / 100,
                    "passed_tests": score,
                    "total_tests": 100,
                },
            }
        ),
        encoding="utf-8",
    )


def test_select_restore_targets_ignores_ready_and_weak_rows(tmp_path):
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

    rows = module.select_restore_targets(
        argparse.Namespace(
            runs=str(runs),
            baseline_root=str(baselines),
            min_holdout_cases=10,
            min_holdout_rate=0.8,
            instance_ids=[],
            limit=20,
        )
    )

    assert [row.task_id for row in rows] == ["task.restore"]


def test_build_strategy_ablation_command_is_guarded_by_default():
    module = load_module()
    args = argparse.Namespace(
        output_root="runs/restore_axis_ablation_next",
        config="config/settings.yaml",
        variants=["baseline_no_adaptive", "adaptive_profile"],
        runs="runs",
        baseline_root="baselines/programbench",
        min_smoke_contract_axes=1,
        required_runtime_smoke_dimensions=("args", "input_files"),
        max_generalization_risk="low",
        execute=False,
        ack_external_llm_docker=False,
        ack_local_llm_docker=False,
        keep_going=False,
    )

    command = module.build_strategy_ablation_command("task.restore", args)

    assert command[:3] == [module.sys.executable, "scripts/run_official_strategy_ablation.py", "task.restore"]
    assert command[command.index("--runs") + 1] == "runs/restore_axis_ablation_next/task.restore"
    assert command[command.index("--config") + 1] == "config/settings.yaml"
    assert command[command.index("--variants") + 1 : command.index("--variants") + 3] == [
        "baseline_no_adaptive",
        "adaptive_profile",
    ]
    assert "--skip-official-eval" in command
    assert "--require-holdout-improvement" in command
    assert command[command.index("--holdout-history-root") + 1] == "runs"
    assert command[command.index("--max-generalization-risk") + 1] == "low"
    assert command[command.index("--generalization-risk-root") + 1] == "runs"
    assert command[command.index("--baseline-root") + 1] == "baselines/programbench"
    assert command[command.index("--min-smoke-contract-axes") + 1] == "1"
    assert command[command.index("--require-runtime-smoke-dimensions") + 1] == "args,input_files"
    assert "--dry-run" in command


def test_build_strategy_ablation_command_can_forward_local_llm_ack():
    module = load_module()
    args = argparse.Namespace(
        output_root="runs/restore_axis_ablation_next",
        config="config/smoke_file_bridge.yaml",
        variants=["baseline_no_adaptive"],
        runs="runs",
        baseline_root="baselines/programbench",
        min_smoke_contract_axes=1,
        required_runtime_smoke_dimensions=(),
        max_generalization_risk="low",
        execute=True,
        dry_run=False,
        ack_external_llm_docker=False,
        ack_local_llm_docker=True,
        keep_going=False,
    )

    command = module.build_strategy_ablation_command("task.restore", args)

    assert command[command.index("--config") + 1] == "config/smoke_file_bridge.yaml"
    assert "--ack-local-llm-docker" in command
    assert "--ack-external-llm-docker" not in command
    assert "--dry-run" not in command


def test_main_default_dry_run_prints_without_runner(tmp_path, monkeypatch, capsys):
    module = load_module()
    runs = tmp_path / "runs"
    baselines = tmp_path / "baselines"
    write_baseline(baselines / "restore.baseline.json", "task.restore", 3)
    write_result(runs / "restore_old", "task.restore", 0.92, 12, timestamp=1_700_000_100)
    write_result(runs / "restore_new", "task.restore", 0.55, 12, timestamp=1_700_000_200)
    calls = []

    monkeypatch.setattr(module, "run_command", lambda command, timeout_seconds: calls.append(command) or 0)

    exit_code = module.main(
        [
            "--runs",
            str(runs),
            "--baseline-root",
            str(baselines),
            "--output-root",
            "runs/restore_next",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert calls == []
    assert "DRY-RUN restore-axis ablation: task.restore" in captured.out
    assert "--dry-run" in captured.out


def test_main_execute_runs_selected_commands(tmp_path, monkeypatch):
    module = load_module()
    runs = tmp_path / "runs"
    baselines = tmp_path / "baselines"
    write_baseline(baselines / "restore.baseline.json", "task.restore", 3)
    write_result(runs / "restore_old", "task.restore", 0.92, 12, timestamp=1_700_000_100)
    write_result(runs / "restore_new", "task.restore", 0.55, 12, timestamp=1_700_000_200)
    calls = []

    monkeypatch.setattr(module, "run_command", lambda command, timeout_seconds: calls.append(command) or 0)

    exit_code = module.main(
        [
            "task.restore",
            "--runs",
            str(runs),
            "--baseline-root",
            str(baselines),
            "--execute",
            "--ack-external-llm-docker",
        ]
    )

    assert exit_code == 0
    assert len(calls) == 1
    assert "--dry-run" not in calls[0]
    assert "--ack-external-llm-docker" in calls[0]


def test_main_execute_requires_external_llm_docker_ack(tmp_path, monkeypatch, capsys):
    module = load_module()
    runs = tmp_path / "runs"
    baselines = tmp_path / "baselines"
    write_baseline(baselines / "restore.baseline.json", "task.restore", 3)
    write_result(runs / "restore_old", "task.restore", 0.92, 12, timestamp=1_700_000_100)
    write_result(runs / "restore_new", "task.restore", 0.55, 12, timestamp=1_700_000_200)
    calls = []

    monkeypatch.setattr(module, "run_command", lambda command, timeout_seconds: calls.append(command) or 0)

    exit_code = module.main(
        [
            "task.restore",
            "--runs",
            str(runs),
            "--baseline-root",
            str(baselines),
            "--execute",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert calls == []
    assert "--ack-external-llm-docker" in captured.err


def test_main_execute_accepts_local_llm_ack_for_file_bridge_config(tmp_path, monkeypatch):
    module = load_module()
    runs = tmp_path / "runs"
    baselines = tmp_path / "baselines"
    write_baseline(baselines / "restore.baseline.json", "task.restore", 3)
    write_result(runs / "restore_old", "task.restore", 0.92, 12, timestamp=1_700_000_100)
    write_result(runs / "restore_new", "task.restore", 0.55, 12, timestamp=1_700_000_200)
    calls = []

    monkeypatch.setattr(module, "run_command", lambda command, timeout_seconds: calls.append(command) or 0)

    exit_code = module.main(
        [
            "task.restore",
            "--runs",
            str(runs),
            "--baseline-root",
            str(baselines),
            "--config",
            "config/smoke_file_bridge.yaml",
            "--execute",
            "--ack-local-llm-docker",
        ]
    )

    assert exit_code == 0
    assert len(calls) == 1
    assert "--ack-local-llm-docker" in calls[0]
    assert "--ack-external-llm-docker" not in calls[0]


def test_main_execute_rejects_local_ack_for_external_config(tmp_path, monkeypatch, capsys):
    module = load_module()
    runs = tmp_path / "runs"
    baselines = tmp_path / "baselines"
    write_baseline(baselines / "restore.baseline.json", "task.restore", 3)
    write_result(runs / "restore_old", "task.restore", 0.92, 12, timestamp=1_700_000_100)
    write_result(runs / "restore_new", "task.restore", 0.55, 12, timestamp=1_700_000_200)
    calls = []

    monkeypatch.setattr(module, "run_command", lambda command, timeout_seconds: calls.append(command) or 0)

    exit_code = module.main(
        [
            "task.restore",
            "--runs",
            str(runs),
            "--baseline-root",
            str(baselines),
            "--config",
            "config/settings.yaml",
            "--execute",
            "--ack-local-llm-docker",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert calls == []
    assert "--ack-local-llm-docker" in captured.err


def test_main_filters_restore_targets_by_axis_action_domain(tmp_path, monkeypatch, capsys):
    module = load_module()
    runs = tmp_path / "runs"
    baselines = tmp_path / "baselines"
    write_baseline(baselines / "csv.baseline.json", "task.csv", 3)
    write_result(runs / "csv_old", "task.csv", 0.92, 12, timestamp=1_700_000_100)
    write_result(
        runs / "csv_new",
        "task.csv",
        0.55,
        12,
        timestamp=1_700_000_200,
        smoke_axes=1,
        adaptive_axes=1,
        smoke_axis_names=["csv_table.quoted_fields"],
        adaptive_axis_names=["csv_table.quoted_fields"],
    )
    write_baseline(baselines / "html.baseline.json", "task.html", 4)
    write_result(runs / "html_old", "task.html", 0.91, 11, timestamp=1_700_000_100)
    write_result(
        runs / "html_new",
        "task.html",
        0.50,
        12,
        timestamp=1_700_000_200,
        smoke_axes=1,
        adaptive_axes=1,
        smoke_axis_names=["html_selector.basic_selector"],
        adaptive_axis_names=["html_selector.basic_selector"],
    )
    calls = []

    monkeypatch.setattr(module, "run_command", lambda command, timeout_seconds: calls.append(command) or 0)

    exit_code = module.main(
        [
            "--runs",
            str(runs),
            "--baseline-root",
            str(baselines),
            "--axis-action-domain",
            "csv_table",
            "--show-axis-action",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert calls == []
    assert "DRY-RUN restore-axis ablation: task.csv" in captured.out
    assert "axis_action=ablate_added_axis_domains:csv_table" in captured.out
    assert "task.html" not in captured.out


def test_main_outputs_restore_batch_json_command_plan(tmp_path, monkeypatch, capsys):
    module = load_module()
    runs = tmp_path / "runs"
    baselines = tmp_path / "baselines"
    write_baseline(baselines / "csv.baseline.json", "task.csv", 3)
    write_result(runs / "csv_old", "task.csv", 0.92, 12, timestamp=1_700_000_100)
    write_result(
        runs / "csv_new",
        "task.csv",
        0.55,
        12,
        timestamp=1_700_000_200,
        smoke_axes=1,
        adaptive_axes=1,
        smoke_axis_names=["csv_table.quoted_fields"],
        adaptive_axis_names=["csv_table.quoted_fields"],
    )
    calls = []

    monkeypatch.setattr(module, "run_command", lambda command, timeout_seconds: calls.append(command) or 0)

    exit_code = module.main(
        [
            "--runs",
            str(runs),
            "--baseline-root",
            str(baselines),
            "--axis-action-domain",
            "csv_table",
            "--show-axis-action",
            "--format",
            "json",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert calls == []
    payload = json.loads(captured.out)
    assert payload["schema_version"] == 1
    assert payload["execute"] is False
    assert payload["row_count"] == 1
    row = payload["rows"][0]
    assert row["rank"] == 1
    assert row["task_id"] == "task.csv"
    assert row["axis_delta_action"] == "ablate_added_axis_domains:csv_table"
    assert row["command"][0] == module.sys.executable
    assert "scripts/run_official_strategy_ablation.py" in row["command"]
    assert "--dry-run" in row["command"]
    assert "--skip-official-eval" in row["command"]
    assert "DRY-RUN restore-axis ablation" not in captured.out
