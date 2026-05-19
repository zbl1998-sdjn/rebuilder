import sys

import pytest

from scripts.run_missing_holdout_cleanroom_rerun import (
    build_closed_loop_command,
    build_subprocess_env,
    main,
    parse_args,
    run_command,
)


def test_build_closed_loop_command_builds_local_signal_without_improvement_gate():
    args = parse_args(
        [
            "alecthomas__chroma.8d04def",
            "--runs",
            "runs/missing_chroma",
            "--min-smoke-contract-axes",
            "1",
            "--pull",
        ]
    )

    command = build_closed_loop_command(args)

    assert command[:3] == [sys.executable, "scripts/run_official_closed_loop.py", "alecthomas__chroma.8d04def"]
    assert command[command.index("--runs") + 1] == "runs/missing_chroma"
    assert "--skip-official-eval" in command
    assert command[command.index("--min-smoke-contract-axes") + 1] == "1"
    assert "--require-holdout-improvement" not in command
    assert "--official-eval-root" not in command
    assert "--eval-run-name" not in command
    assert "--pull" in command


def test_build_closed_loop_command_passes_runtime_smoke_dimension_gate_without_improvement_gate():
    args = parse_args(
        [
            "alecthomas__chroma.8d04def",
            "--require-runtime-smoke-dimensions",
            "args,input_files",
        ]
    )

    command = build_closed_loop_command(args)

    assert command[command.index("--require-runtime-smoke-dimensions") + 1] == "args,input_files"
    assert "--require-holdout-improvement" not in command
    assert "--official-eval-root" not in command


def test_default_mode_is_dry_run_without_execute(monkeypatch, capsys):
    called = False

    def fake_run_command(command, *, timeout_seconds):
        nonlocal called
        called = True
        return 1

    monkeypatch.setattr("scripts.run_missing_holdout_cleanroom_rerun.run_command", fake_run_command)

    exit_code = main(["rbakbashev__elfcat.52f8cc7"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert not called
    assert "scripts/run_official_closed_loop.py rbakbashev__elfcat.52f8cc7" in output
    assert "--skip-official-eval" in output
    assert "--require-holdout-improvement" not in output


def test_execute_requires_external_llm_docker_ack(monkeypatch, capsys):
    called = False

    def fake_run_command(command, *, timeout_seconds):
        nonlocal called
        called = True
        return 1

    monkeypatch.setattr("scripts.run_missing_holdout_cleanroom_rerun.run_command", fake_run_command)

    exit_code = main(["alecthomas__chroma.8d04def", "--execute"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert not called
    assert "--ack-external-llm-docker" in captured.err


def test_execute_forwards_external_ack(monkeypatch):
    seen = {}

    def fake_run_command(command, *, timeout_seconds):
        seen["command"] = command
        seen["timeout_seconds"] = timeout_seconds
        return 7

    monkeypatch.setattr("scripts.run_missing_holdout_cleanroom_rerun.run_command", fake_run_command)

    exit_code = main(
        [
            "alecthomas__chroma.8d04def",
            "--execute",
            "--ack-external-llm-docker",
            "--command-timeout-seconds",
            "12",
        ]
    )

    assert exit_code == 7
    assert seen["command"][2] == "alecthomas__chroma.8d04def"
    assert "--ack-external-llm-docker" in seen["command"]
    assert seen["timeout_seconds"] == 12


def test_parse_args_rejects_invalid_gates():
    with pytest.raises(SystemExit):
        parse_args(["alecthomas__chroma.8d04def", "--min-holdout-rate", "nan"])

    with pytest.raises(SystemExit):
        parse_args(["alecthomas__chroma.8d04def", "--min-smoke-contract-axes", "-1"])

    with pytest.raises(SystemExit):
        parse_args(["alecthomas__chroma.8d04def", "--workers", "0"])


def test_run_command_uses_utf8_env(monkeypatch):
    seen = {}

    def fake_run(command, *, text, check, timeout, env):
        seen["command"] = command
        seen["text"] = text
        seen["check"] = check
        seen["timeout"] = timeout
        seen["env"] = env
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr("scripts.run_missing_holdout_cleanroom_rerun.subprocess.run", fake_run)

    exit_code = run_command(["py", "-3.14"], timeout_seconds=5)

    assert exit_code == 0
    assert seen["command"] == ["py", "-3.14"]
    assert seen["text"] is True
    assert seen["check"] is False
    assert seen["timeout"] == 5
    assert seen["env"]["PYTHONIOENCODING"] == "utf-8"
    assert build_subprocess_env()["PYTHONUTF8"] == "1"
