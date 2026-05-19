import sys

import pytest

from scripts.run_weak_task_cleanroom_rerun import (
    DEFAULT_PROGRAMBENCH_CATALOG,
    build_closed_loop_command,
    build_subprocess_env,
    main,
    parse_args,
    run_command,
)


def test_build_closed_loop_command_forces_local_only_improvement_gate():
    args = parse_args(
        [
            "sharkdp__hexyl.2e26437",
            "--runs",
            "runs/weak_hexyl",
            "--holdout-history-root",
            "runs/history",
            "--pull",
        ]
    )

    command = build_closed_loop_command(args)

    assert command[:3] == [sys.executable, "scripts/run_official_closed_loop.py", "sharkdp__hexyl.2e26437"]
    assert command[command.index("--catalog") + 1] == DEFAULT_PROGRAMBENCH_CATALOG
    assert command[command.index("--runs") + 1] == "runs/weak_hexyl"
    assert "--skip-official-eval" in command
    assert "--require-holdout-improvement" in command
    assert command[command.index("--holdout-history-root") + 1] == "runs/history"
    assert "--pull" in command
    assert "--eval-run-name" not in command
    assert "--official-eval-root" not in command


def test_build_closed_loop_command_passes_strategy_variant_without_enabling_official_eval():
    args = parse_args(
        [
            "sheepla__pingu.926d475",
            "--strategy-registry",
            "runs/registry.jsonl",
            "--strategy-variant",
            "adaptive_profile",
        ]
    )

    command = build_closed_loop_command(args)

    assert command[command.index("--strategy-registry") + 1] == "runs/registry.jsonl"
    assert command[command.index("--strategy-variant") + 1] == "adaptive_profile"
    assert "--skip-official-eval" in command


def test_build_closed_loop_command_passes_holdout_improvement_delta_without_enabling_official_eval():
    args = parse_args(
        [
            "sharkdp__hexyl.2e26437",
            "--min-holdout-improvement-delta",
            "0.02",
        ]
    )

    command = build_closed_loop_command(args)

    assert command[command.index("--min-holdout-improvement-delta") + 1] == "0.02"
    assert "--skip-official-eval" in command
    assert "--official-eval-root" not in command


def test_build_closed_loop_command_passes_smoke_axis_gate_without_enabling_official_eval():
    args = parse_args(
        [
            "sharkdp__hexyl.2e26437",
            "--min-smoke-contract-axes",
            "2",
        ]
    )

    command = build_closed_loop_command(args)

    assert command[command.index("--min-smoke-contract-axes") + 1] == "2"
    assert "--skip-official-eval" in command
    assert "--official-eval-root" not in command


def test_build_closed_loop_command_passes_runtime_smoke_dimension_gate_without_enabling_official_eval():
    args = parse_args(
        [
            "sharkdp__hexyl.2e26437",
            "--require-runtime-smoke-dimensions",
            "args,input_files",
        ]
    )

    command = build_closed_loop_command(args)

    assert command[command.index("--require-runtime-smoke-dimensions") + 1] == "args,input_files"
    assert "--skip-official-eval" in command
    assert "--official-eval-root" not in command


def test_parse_args_rejects_negative_gate_thresholds():
    with pytest.raises(SystemExit):
        parse_args(["sharkdp__hexyl.2e26437", "--min-holdout-rate", "nan"])

    with pytest.raises(SystemExit):
        parse_args(["sharkdp__hexyl.2e26437", "--min-smoke-contract-axes", "-1"])

    with pytest.raises(SystemExit):
        parse_args(["sharkdp__hexyl.2e26437", "--min-holdout-improvement-delta", "-0.01"])

    with pytest.raises(SystemExit):
        parse_args(["sharkdp__hexyl.2e26437", "--min-holdout-improvement-delta", "nan"])


@pytest.mark.parametrize(
    "flag_and_value",
    [
        ("--probe-iterations", "-1"),
        ("--min-probe-samples", "-1"),
        ("--max-repairs", "-1"),
        ("--near-miss-max-repairs", "-1"),
        ("--branch-retries", "-1"),
        ("--workers", "0"),
        ("--branch-workers", "0"),
        ("--docker-cpus", "0"),
    ],
)
def test_parse_args_rejects_invalid_execution_controls(flag_and_value):
    flag, value = flag_and_value

    with pytest.raises(SystemExit):
        parse_args(["sharkdp__hexyl.2e26437", flag, value])


@pytest.mark.parametrize(
    "flag_and_value",
    [
        ("--min-holdout-rate", "1.2"),
        ("--near-miss-holdout-rate", "-0.1"),
        ("--near-miss-holdout-rate", "nan"),
        ("--near-miss-holdout-rate", "1.2"),
        ("--command-timeout-seconds", "0"),
        ("--command-timeout-seconds", "nan"),
    ],
)
def test_parse_args_rejects_invalid_rate_and_timeout_controls(flag_and_value):
    flag, value = flag_and_value

    with pytest.raises(SystemExit):
        parse_args(["sharkdp__hexyl.2e26437", flag, value])


def test_dry_run_prints_command_without_running(monkeypatch, capsys):
    called = False

    def fake_run_command(command, *, timeout_seconds):
        nonlocal called
        called = True
        return 1

    monkeypatch.setattr("scripts.run_weak_task_cleanroom_rerun.run_command", fake_run_command)

    exit_code = main(["sharkdp__hexyl.2e26437", "--dry-run"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert not called
    assert "scripts/run_official_closed_loop.py sharkdp__hexyl.2e26437" in output
    assert "--skip-official-eval" in output
    assert "--require-holdout-improvement" in output


def test_default_mode_is_dry_run_without_execute(monkeypatch, capsys):
    called = False

    def fake_run_command(command, *, timeout_seconds):
        nonlocal called
        called = True
        return 1

    monkeypatch.setattr("scripts.run_weak_task_cleanroom_rerun.run_command", fake_run_command)

    exit_code = main(["sharkdp__hexyl.2e26437"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert not called
    assert "scripts/run_official_closed_loop.py sharkdp__hexyl.2e26437" in output


def test_execute_mode_runs_command(monkeypatch):
    seen = {}

    def fake_run_command(command, *, timeout_seconds):
        seen["command"] = command
        seen["timeout_seconds"] = timeout_seconds
        return 7

    monkeypatch.setattr("scripts.run_weak_task_cleanroom_rerun.run_command", fake_run_command)

    exit_code = main(
        [
            "sharkdp__hexyl.2e26437",
            "--execute",
            "--ack-external-llm-docker",
            "--command-timeout-seconds",
            "12",
        ]
    )

    assert exit_code == 7
    assert seen["command"][2] == "sharkdp__hexyl.2e26437"
    assert "--ack-external-llm-docker" in seen["command"]
    assert seen["timeout_seconds"] == 12


def test_execute_mode_requires_external_llm_docker_ack(monkeypatch, capsys):
    called = False

    def fake_run_command(command, *, timeout_seconds):
        nonlocal called
        called = True
        return 1

    monkeypatch.setattr("scripts.run_weak_task_cleanroom_rerun.run_command", fake_run_command)

    exit_code = main(["sharkdp__hexyl.2e26437", "--execute"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert not called
    assert "--ack-external-llm-docker" in captured.err


def test_run_command_uses_utf8_env(monkeypatch):
    seen = {}

    def fake_run(command, *, text, check, timeout, env):
        seen["command"] = command
        seen["text"] = text
        seen["check"] = check
        seen["timeout"] = timeout
        seen["env"] = env
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr("scripts.run_weak_task_cleanroom_rerun.subprocess.run", fake_run)

    exit_code = run_command(["py", "-3.14"], timeout_seconds=5)

    assert exit_code == 0
    assert seen["command"] == ["py", "-3.14"]
    assert seen["text"] is True
    assert seen["check"] is False
    assert seen["timeout"] == 5
    assert seen["env"]["PYTHONIOENCODING"] == "utf-8"
    assert build_subprocess_env()["PYTHONUTF8"] == "1"
