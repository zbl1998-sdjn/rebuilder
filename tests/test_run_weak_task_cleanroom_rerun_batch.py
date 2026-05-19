import json
import os
import sys

import pytest

from scripts.run_weak_task_cleanroom_rerun_batch import (
    build_weak_rerun_command,
    main,
    parse_args,
    select_weak_batch_targets,
)


def write_result(path, task_id, holdout_rate, holdout_cases, *, timestamp=1_700_000_000):
    target = path / task_id / "generated" / task_id
    target.mkdir(parents=True)
    result_path = target / "result.json"
    result_path.write_text(
        json.dumps(
            {
                "task_id": task_id,
                "status": "failed",
                "resolved_rate": 0.5,
                "holdout_resolved_rate": holdout_rate,
                "holdout_cases": holdout_cases,
                "probes_conducted": 50,
                "iterations_used": 3,
            }
        ),
        encoding="utf-8",
    )
    os.utime(result_path, (timestamp, timestamp))
    return result_path


def test_selects_weak_recommendations_and_prints_json_dry_run_commands(tmp_path, capsys):
    runs = tmp_path / "runs"
    write_result(runs / "hexyl", "task.hexyl", 0.2, 10)
    write_result(runs / "pingu_old", "task.pingu", 7 / 12, 12, timestamp=1_700_000_000)
    write_result(runs / "pingu_new", "task.pingu", 3 / 14, 14, timestamp=1_700_000_100)
    write_result(runs / "ready", "task.ready", 0.9, 12)

    exit_code = main(
        [
            "--runs",
            str(runs),
            "--output-root",
            "runs/weak_next",
            "--limit",
            "2",
            "--min-smoke-contract-axes",
            "1",
            "--min-holdout-improvement-delta",
            "0.02",
            "--format",
            "json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["schema_version"] == 1
    assert payload["execute"] is False
    assert payload["row_count"] == 2
    assert [row["task_id"] for row in payload["rows"]] == ["task.hexyl", "task.pingu"]
    first_command = payload["rows"][0]["command"]
    assert first_command[:3] == [
        sys.executable,
        "scripts/run_weak_task_cleanroom_rerun.py",
        "task.hexyl",
    ]
    assert "--dry-run" in first_command
    assert "--execute" not in first_command
    assert first_command[first_command.index("--runs") + 1] == "runs/weak_next/task.hexyl"
    assert first_command[first_command.index("--min-smoke-contract-axes") + 1] == "1"
    assert first_command[first_command.index("--min-holdout-improvement-delta") + 1] == "0.02"


def test_build_weak_rerun_command_for_execute_forwards_ack_without_official_eval():
    args = parse_args(
        [
            "--runs",
            "runs/history",
            "--output-root",
            "runs/weak_next",
            "--require-runtime-smoke-dimensions",
            "args,input_files",
            "--execute",
            "--ack-external-llm-docker",
        ]
    )

    command = build_weak_rerun_command("task.hexyl", args)

    assert command[:3] == [sys.executable, "scripts/run_weak_task_cleanroom_rerun.py", "task.hexyl"]
    assert "--execute" in command
    assert "--ack-external-llm-docker" in command
    assert "--dry-run" not in command
    assert "--official-eval-root" not in command
    assert command[command.index("--require-runtime-smoke-dimensions") + 1] == "args,input_files"


def test_execute_mode_requires_external_llm_docker_ack(monkeypatch, capsys, tmp_path):
    runs = tmp_path / "runs"
    write_result(runs / "hexyl", "task.hexyl", 0.2, 10)
    called = False

    def fake_run_command(command, *, timeout_seconds):
        nonlocal called
        called = True
        return 0

    monkeypatch.setattr("scripts.run_weak_task_cleanroom_rerun_batch.run_command", fake_run_command)

    exit_code = main(["--runs", str(runs), "--execute"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert not called
    assert "--ack-external-llm-docker" in captured.err


def test_execute_mode_runs_selected_commands_with_keep_going(monkeypatch, tmp_path):
    runs = tmp_path / "runs"
    write_result(runs / "hexyl", "task.hexyl", 0.2, 10)
    write_result(runs / "pingu", "task.pingu", 0.3, 10)
    seen = []

    def fake_run_command(command, *, timeout_seconds):
        seen.append((command, timeout_seconds))
        return 0

    monkeypatch.setattr("scripts.run_weak_task_cleanroom_rerun_batch.run_command", fake_run_command)

    exit_code = main(
        [
            "--runs",
            str(runs),
            "--limit",
            "2",
            "--execute",
            "--ack-external-llm-docker",
            "--keep-going",
            "--command-timeout-seconds",
            "12",
        ]
    )

    assert exit_code == 0
    assert len(seen) == 2
    assert all("--execute" in command for command, _timeout in seen)
    assert all("--ack-external-llm-docker" in command for command, _timeout in seen)
    assert [timeout for _command, timeout in seen] == [12, 12]


def test_json_format_rejects_real_execute(tmp_path):
    runs = tmp_path / "runs"
    write_result(runs / "hexyl", "task.hexyl", 0.2, 10)

    exit_code = main(
        [
            "--runs",
            str(runs),
            "--execute",
            "--ack-external-llm-docker",
            "--format",
            "json",
        ]
    )

    assert exit_code == 2


def test_parse_args_rejects_invalid_gate_thresholds():
    for flag, value in (
        ("--limit", "0"),
        ("--min-holdout-cases", "-1"),
        ("--min-holdout-rate", "1.2"),
        ("--min-smoke-contract-axes", "-1"),
        ("--min-holdout-improvement-delta", "-0.01"),
        ("--command-timeout-seconds", "0"),
    ):
        with pytest.raises(SystemExit):
            parse_args([flag, value])


def test_select_weak_batch_targets_can_filter_instance_ids(tmp_path):
    runs = tmp_path / "runs"
    write_result(runs / "hexyl", "task.hexyl", 0.2, 10)
    write_result(runs / "pingu", "task.pingu", 0.3, 10)
    args = parse_args(["task.pingu", "--runs", str(runs)])

    rows = select_weak_batch_targets(args)

    assert [row.task_id for row in rows] == ["task.pingu"]
