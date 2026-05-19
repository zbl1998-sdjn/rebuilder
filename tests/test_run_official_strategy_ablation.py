import sys

import pytest

from scripts.run_official_strategy_ablation import (
    CommandFailure,
    DEFAULT_VARIANTS,
    build_subprocess_env,
    build_closed_loop_command,
    history_root_contains_current_ablation,
    main as run_strategy_ablation_main,
    parse_args,
    run_command,
    run_variant_commands,
    warn_if_history_root_contains_current_ablation,
)


def args(**overrides):
    defaults = {
        "instance_id": "owner__repo.abcdef0",
        "catalog": "examples/programbench_samples/samples.json",
        "runs": "runs/strategy_ablation",
        "config": "config/settings.yaml",
        "strategy_registry": "runs/strategy_registry.jsonl",
        "variants": list(DEFAULT_VARIANTS),
        "eval_run_prefix": "ablation",
        "official_eval_root": "runs/programbench_official_eval",
        "probe_iterations": 10,
        "min_probe_samples": 50,
        "max_repairs": 3,
        "near_miss_holdout_rate": 0.75,
        "near_miss_max_repairs": 5,
        "replacement_executor": "wsl",
        "static_output_assets": "disabled",
        "min_holdout_rate": 0.8,
        "min_holdout_cases": 10,
        "min_smoke_contract_axes": 0,
        "required_runtime_smoke_dimensions": (),
        "workers": 1,
        "branch_workers": 1,
        "docker_cpus": 4,
        "branch_retries": 1,
        "programbench_python": "py",
        "programbench_python_version": "3.14",
        "model": "glm-5.1",
        "baseline_output": "baselines/programbench",
        "pull": False,
        "force": False,
        "skip_official_eval": False,
        "require_holdout_improvement": False,
        "min_holdout_improvement_delta": 0.0,
        "holdout_history_root": "runs",
        "holdout_history_exclude_roots": [],
        "max_generalization_risk": None,
        "generalization_risk_root": "runs",
        "baseline_root": "baselines/programbench",
        "keep_going": False,
        "dry_run": False,
        "ack_external_llm_docker": False,
    }
    defaults.update(overrides)
    return type("Args", (), defaults)()


def test_build_closed_loop_command_isolates_variant_run_directories():
    command = build_closed_loop_command(args(), "adaptive_profile")

    assert command[:3] == [sys.executable, "scripts/run_official_closed_loop.py", "owner__repo.abcdef0"]
    assert command[command.index("--strategy-variant") + 1] == "adaptive_profile"
    assert command[command.index("--strategy-registry") + 1] == "runs/strategy_registry.jsonl"
    assert command[command.index("--runs") + 1].endswith("strategy_ablation/adaptive_profile")
    assert command[command.index("--eval-run-name") + 1] == "ablation_adaptive_profile"


def test_build_closed_loop_command_passes_explicit_booleans():
    command = build_closed_loop_command(args(pull=True, force=True, skip_official_eval=True), "baseline_no_adaptive")

    assert "--pull" in command
    assert "--force" in command
    assert "--skip-official-eval" in command


def test_build_closed_loop_command_passes_external_execution_ack():
    command = build_closed_loop_command(args(ack_external_llm_docker=True), "baseline_no_adaptive")

    assert "--ack-external-llm-docker" in command


def test_build_closed_loop_command_passes_holdout_improvement_gate():
    command = build_closed_loop_command(
        args(require_holdout_improvement=True, runs="runs/restore_ablation", holdout_history_root="runs/history"),
        "adaptive_profile",
    )

    assert "--require-holdout-improvement" in command
    assert command[command.index("--holdout-history-root") + 1] == "runs/history"
    assert command[command.index("--holdout-history-exclude-root") + 1] == "runs/restore_ablation"


def test_build_closed_loop_command_passes_holdout_improvement_delta():
    command = build_closed_loop_command(
        args(require_holdout_improvement=True, min_holdout_improvement_delta=0.02),
        "adaptive_profile",
    )

    assert command[command.index("--min-holdout-improvement-delta") + 1] == "0.02"


def test_build_closed_loop_command_passes_smoke_axis_gate():
    command = build_closed_loop_command(args(min_smoke_contract_axes=2), "adaptive_profile")

    assert command[command.index("--min-smoke-contract-axes") + 1] == "2"


def test_build_closed_loop_command_passes_runtime_smoke_dimension_gate():
    command = build_closed_loop_command(
        args(required_runtime_smoke_dimensions=("args", "input_files")),
        "adaptive_profile",
    )

    assert command[command.index("--require-runtime-smoke-dimensions") + 1] == "args,input_files"


def test_build_closed_loop_command_passes_generalization_risk_gate():
    command = build_closed_loop_command(
        args(
            max_generalization_risk="low",
            generalization_risk_root="runs/risk-history",
            baseline_root="baselines/programbench",
            official_eval_root="runs/eval",
        ),
        "adaptive_profile",
    )

    assert command[command.index("--max-generalization-risk") + 1] == "low"
    assert command[command.index("--generalization-risk-root") + 1] == "runs/risk-history"
    assert command[command.index("--baseline-root") + 1] == "baselines/programbench"


@pytest.mark.parametrize(
    "flag_and_value",
    [
        ("--min-holdout-rate", "-0.1"),
        ("--min-holdout-rate", "nan"),
        ("--min-holdout-cases", "-1"),
        ("--min-smoke-contract-axes", "-1"),
        ("--min-holdout-improvement-delta", "-0.01"),
        ("--min-holdout-improvement-delta", "nan"),
    ],
)
def test_parse_args_rejects_negative_gate_thresholds(flag_and_value):
    flag, value = flag_and_value

    with pytest.raises(SystemExit):
        parse_args(["owner__repo.abcdef0", flag, value])


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
        parse_args(["owner__repo.abcdef0", flag, value])


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
        parse_args(["owner__repo.abcdef0", flag, value])


def test_history_root_warning_detects_current_ablation_root(tmp_path, capsys):
    run_root = tmp_path / "runs" / "strategy_ablation"
    history_root = tmp_path / "runs"
    assert history_root_contains_current_ablation(
        args(
            require_holdout_improvement=True,
            runs=str(run_root),
            holdout_history_root=str(history_root),
        )
    )

    warn_if_history_root_contains_current_ablation(
        args(
            require_holdout_improvement=True,
            runs=str(run_root),
            holdout_history_root=str(history_root),
        )
    )

    captured = capsys.readouterr()
    assert "child variants will pass --holdout-history-exclude-root" in captured.err


def test_history_root_warning_ignores_separate_history_root(tmp_path, capsys):
    assert not history_root_contains_current_ablation(
        args(
            require_holdout_improvement=True,
            runs=str(tmp_path / "runs" / "strategy_ablation"),
            holdout_history_root=str(tmp_path / "history"),
        )
    )

    warn_if_history_root_contains_current_ablation(
        args(
            require_holdout_improvement=True,
            runs=str(tmp_path / "runs" / "strategy_ablation"),
            holdout_history_root=str(tmp_path / "history"),
        )
    )

    captured = capsys.readouterr()
    assert captured.err == ""


def test_run_variant_commands_stops_on_first_failure():
    calls = []

    def fake_run(command):
        calls.append(command)
        if command[-1] == "adaptive_profile":
            raise RuntimeError("failed")

    with pytest.raises(RuntimeError, match="failed"):
        run_variant_commands(
            args(variants=["baseline_no_adaptive", "adaptive_profile", "adaptive_deep"]),
            runner=fake_run,
        )

    assert [call[-1] for call in calls] == ["baseline_no_adaptive", "adaptive_profile"]


def test_run_variant_commands_keep_going_collects_failures():
    calls = []

    def fake_run(command):
        calls.append(command)
        if command[-1] == "adaptive_profile":
            raise RuntimeError("failed")

    failures = run_variant_commands(
        args(variants=["baseline_no_adaptive", "adaptive_profile", "adaptive_deep"], keep_going=True),
        runner=fake_run,
    )

    assert failures == [("adaptive_profile", "failed")]
    assert [call[-1] for call in calls] == ["baseline_no_adaptive", "adaptive_profile", "adaptive_deep"]


def test_run_variant_commands_treats_holdout_gate_skip_as_nonfatal_with_keep_going():
    calls = []

    def fake_run(command):
        calls.append(command)
        if command[-1] == "adaptive_profile":
            raise CommandFailure(3, command)

    failures = run_variant_commands(
        args(variants=["baseline_no_adaptive", "adaptive_profile", "adaptive_deep"], keep_going=True),
        runner=fake_run,
    )

    assert failures == []
    assert [call[-1] for call in calls] == ["baseline_no_adaptive", "adaptive_profile", "adaptive_deep"]


def test_run_variant_commands_dry_run_prints_without_calling_runner(capsys):
    calls = []

    def fake_run(command):
        calls.append(command)
        raise AssertionError("dry-run should not execute child commands")

    failures = run_variant_commands(
        args(variants=["baseline_no_adaptive", "adaptive_profile"], dry_run=True),
        runner=fake_run,
    )

    captured = capsys.readouterr()
    assert failures == []
    assert calls == []
    assert "DRY-RUN strategy variant: baseline_no_adaptive" in captured.out
    assert "scripts/run_official_closed_loop.py" in captured.out
    assert "--strategy-variant baseline_no_adaptive" in captured.out
    assert "--strategy-variant adaptive_profile" in captured.out


def test_main_requires_external_llm_docker_ack(monkeypatch, capsys):
    called = False

    def fake_run(command, *, timeout_seconds):
        nonlocal called
        called = True
        raise AssertionError("missing ack should stop before running variants")

    monkeypatch.setattr("scripts.run_official_strategy_ablation.run_command", fake_run)

    with pytest.raises(SystemExit) as exc_info:
        run_strategy_ablation_main(["owner__repo.abcdef0"])

    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert not called
    assert "--ack-external-llm-docker" in captured.err


def test_subprocess_env_forces_utf8_python_output(monkeypatch):
    monkeypatch.setenv("PYTHONIOENCODING", "cp936")

    env = build_subprocess_env()

    assert env["PYTHONUTF8"] == "1"
    assert env["PYTHONIOENCODING"] == "utf-8"


def test_run_command_passes_utf8_env(monkeypatch):
    seen = {}

    def fake_run(command, *, text, check, timeout, env):
        seen["command"] = command
        seen["text"] = text
        seen["check"] = check
        seen["timeout"] = timeout
        seen["env"] = env
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr("scripts.run_official_strategy_ablation.subprocess.run", fake_run)

    run_command(["py", "-3.14"], timeout_seconds=12)

    assert seen["command"] == ["py", "-3.14"]
    assert seen["text"] is True
    assert seen["check"] is False
    assert seen["timeout"] == 12
    assert seen["env"]["PYTHONIOENCODING"] == "utf-8"
