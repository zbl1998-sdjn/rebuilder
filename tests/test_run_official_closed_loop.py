import argparse
import json

import pytest

from core.experiments import AggregateFeedback, ExperimentRegistry, ExperimentRun, StrategyVariant
from scripts.run_official_closed_loop import (
    apply_strategy_variant,
    build_subprocess_env,
    build_paths,
    build_programbench_eval_command,
    build_rebuilder_command,
    build_package_command,
    record_strategy_experiment,
    main as _run_closed_loop_main,
    run_command,
    run_programbench_eval,
    select_strategy_variant,
    holdout_cases,
    holdout_rate,
    is_local_llm_config,
    parse_args,
    should_retry_near_miss,
    smoke_contract_axis_count,
)


def run_closed_loop_main(argv):
    return _run_closed_loop_main([*argv, "--ack-external-llm-docker"])


def args(**overrides):
    defaults = {
        "instance_id": "owner__repo.abcdef0",
        "runs": "runs/closed_loop",
        "config": "config/settings.yaml",
        "probe_iterations": 10,
        "min_probe_samples": 50,
        "max_repairs": 3,
        "replacement_executor": "wsl",
        "static_output_assets": "disabled",
        "min_holdout_rate": 0.8,
        "min_holdout_cases": 10,
        "min_smoke_contract_axes": 0,
        "required_runtime_smoke_dimensions": (),
        "near_miss_holdout_rate": 0.75,
        "near_miss_max_repairs": 5,
        "programbench_python": "py",
        "programbench_python_version": "3.14",
        "workers": 1,
        "branch_workers": 1,
        "docker_cpus": 4,
        "branch_retries": 1,
        "force": True,
        "adaptive_probes": "config",
        "strategy_registry": "",
        "strategy_variant": "",
        "model": "glm-5.1",
        "require_holdout_improvement": False,
        "min_holdout_improvement_delta": 0.0,
        "holdout_history_root": "runs",
        "holdout_history_exclude_roots": [],
        "max_generalization_risk": None,
        "generalization_risk_root": "runs",
        "baseline_root": "baselines/programbench",
        "official_eval_root": "runs/programbench_official_eval",
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def test_main_requires_external_llm_docker_ack(capsys):
    with pytest.raises(SystemExit) as exc_info:
        _run_closed_loop_main(["owner__repo.abcdef0"])

    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert "--ack-external-llm-docker" in captured.err


def test_local_llm_ack_detection_accepts_only_non_external_configs():
    assert is_local_llm_config("config/smoke_file_bridge.yaml")
    assert is_local_llm_config("config/smoke_local_openai.yaml")
    assert not is_local_llm_config("config/settings.yaml")


def test_build_paths_uses_stable_nested_layout():
    paths = build_paths(
        "owner__repo.abcdef0",
        "runs/closed_loop",
        "runs/programbench_official_eval",
        "submission_owner_repo",
    )

    assert paths.workspace.as_posix() == "runs/closed_loop/owner__repo.abcdef0/workspace"
    assert paths.result.as_posix().endswith(
        "runs/closed_loop/owner__repo.abcdef0/generated/owner__repo.abcdef0/owner__repo.abcdef0/result.json"
    )
    assert paths.eval_json.as_posix().endswith("submission_owner_repo/owner__repo.abcdef0/owner__repo.abcdef0.eval.json")


def test_build_rebuilder_command_uses_cleanroom_image_and_wsl_executor():
    parsed = args()
    paths = build_paths(parsed.instance_id, parsed.runs, "runs/eval")

    command = build_rebuilder_command(parsed, paths, "programbench/owner_1776_repo.abcdef0:task_cleanroom")

    assert "--reference-docker-image" in command
    assert "programbench/owner_1776_repo.abcdef0:task_cleanroom" in command
    assert command[-2:] == ["--static-output-assets", "disabled"]
    assert command[command.index("--probe-iterations") + 1] == "10"
    assert command[command.index("--min-probe-samples") + 1] == "50"
    assert "wsl" in command


def test_build_rebuilder_command_passes_adaptive_probe_toggle():
    parsed = args(adaptive_probes="enabled")
    paths = build_paths(parsed.instance_id, parsed.runs, "runs/eval")

    command = build_rebuilder_command(parsed, paths, "programbench/owner_1776_repo.abcdef0:task_cleanroom")

    assert command[command.index("--adaptive-probes") + 1] == "enabled"


def test_build_rebuilder_command_allows_repair_override():
    parsed = args()
    paths = build_paths(parsed.instance_id, parsed.runs, "runs/eval")

    command = build_rebuilder_command(parsed, paths, "programbench/owner_1776_repo.abcdef0:task_cleanroom", max_repairs=5)

    assert command[command.index("--max-repairs") + 1] == "5"


def test_parse_args_accepts_holdout_history_exclude_roots():
    parsed = parse_args(
        [
            "owner__repo.abcdef0",
            "--holdout-history-exclude-root",
            "runs/restore_ablation",
            "--holdout-history-exclude-root",
            "runs/current_candidate",
        ]
    )

    assert parsed.holdout_history_exclude_roots == ["runs/restore_ablation", "runs/current_candidate"]


def test_build_programbench_eval_command_uses_python_import_entrypoint():
    parsed = args()
    paths = build_paths(parsed.instance_id, parsed.runs, "runs/eval")

    command = build_programbench_eval_command(parsed, paths)

    assert command[:4] == ["py", "-3.14", "-c", "from programbench.cli.main import app; app()"]
    assert "--force" in command
    assert str(paths.submission_root) in command


def test_subprocess_env_forces_utf8_python_output(monkeypatch):
    monkeypatch.setenv("PYTHONIOENCODING", "cp936")

    env = build_subprocess_env()

    assert env["PYTHONUTF8"] == "1"
    assert env["PYTHONIOENCODING"] == "utf-8"


def test_run_command_passes_utf8_env(monkeypatch):
    seen = {}

    def fake_run(command, *, text, check, env):
        seen["command"] = command
        seen["text"] = text
        seen["check"] = check
        seen["env"] = env
        return argparse.Namespace(returncode=0)

    monkeypatch.setattr("scripts.run_official_closed_loop.subprocess.run", fake_run)

    run_command(["py", "-3.14"])

    assert seen["command"] == ["py", "-3.14"]
    assert seen["text"] is True
    assert seen["check"] is False
    assert seen["env"]["PYTHONIOENCODING"] == "utf-8"


def test_run_programbench_eval_continues_when_eval_json_exists(tmp_path, monkeypatch):
    parsed = args()
    paths = build_paths(parsed.instance_id, parsed.runs, tmp_path / "eval", "submission_owner_repo")
    paths.eval_json.parent.mkdir(parents=True)
    paths.eval_json.write_text(json.dumps({"test_results": []}), encoding="utf-8")

    def fake_run_command(_command):
        raise RuntimeError("UnicodeEncodeError")

    monkeypatch.setattr("scripts.run_official_closed_loop.run_command", fake_run_command)

    run_programbench_eval(parsed, paths)


def test_run_programbench_eval_raises_without_eval_json(tmp_path, monkeypatch):
    parsed = args()
    paths = build_paths(parsed.instance_id, parsed.runs, tmp_path / "eval", "submission_owner_repo")

    def fake_run_command(_command):
        raise RuntimeError("failed before eval output")

    monkeypatch.setattr("scripts.run_official_closed_loop.run_command", fake_run_command)

    try:
        run_programbench_eval(parsed, paths)
    except RuntimeError as exc:
        assert "failed before eval output" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_build_package_command_passes_holdout_case_gate():
    parsed = args()
    paths = build_paths(parsed.instance_id, parsed.runs, "runs/eval")

    command = build_package_command(parsed, paths)

    assert command[command.index("--min-holdout-rate") + 1] == "0.8"
    assert command[command.index("--min-holdout-cases") + 1] == "10"


def test_build_package_command_passes_smoke_axis_gate_when_required():
    parsed = args(min_smoke_contract_axes=2)
    paths = build_paths(parsed.instance_id, parsed.runs, "runs/eval")

    command = build_package_command(parsed, paths)

    assert command[command.index("--min-smoke-contract-axes") + 1] == "2"


def test_build_package_command_passes_runtime_smoke_dimension_gate_when_required():
    parsed = args(required_runtime_smoke_dimensions=("args", "input_files"))
    paths = build_paths(parsed.instance_id, parsed.runs, "runs/eval")

    command = build_package_command(parsed, paths)

    assert command[command.index("--require-runtime-smoke-dimensions") + 1] == "args,input_files"


def test_build_package_command_passes_generalization_risk_gate_when_required():
    parsed = args(
        max_generalization_risk="low",
        generalization_risk_root="runs/risk-history",
        baseline_root="baselines/programbench",
        official_eval_root="runs/eval",
    )
    paths = build_paths(parsed.instance_id, parsed.runs, parsed.official_eval_root)

    command = build_package_command(parsed, paths)

    assert command[command.index("--max-generalization-risk") + 1] == "low"
    assert command[command.index("--generalization-risk-root") + 1] == "runs/risk-history"
    assert command[command.index("--baseline-root") + 1] == "baselines/programbench"
    assert command[command.index("--official-eval-root") + 1] == "runs/eval"


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
def test_parse_args_rejects_negative_official_gate_thresholds(flag_and_value):
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
    ],
)
def test_parse_args_rejects_invalid_rate_controls(flag_and_value):
    flag, value = flag_and_value

    with pytest.raises(SystemExit):
        parse_args(["owner__repo.abcdef0", flag, value])


def test_holdout_rate_reads_aggregate_only_value(tmp_path):
    result = tmp_path / "result.json"
    result.write_text(json.dumps({"holdout_resolved_rate": 0.875}), encoding="utf-8")

    assert holdout_rate(json.loads(result.read_text(encoding="utf-8"))) == 0.875


def test_holdout_rate_treats_non_finite_aggregate_value_as_missing(tmp_path):
    result = tmp_path / "result.json"
    result.write_text(json.dumps({"holdout_resolved_rate": "nan"}), encoding="utf-8")

    assert holdout_rate(json.loads(result.read_text(encoding="utf-8"))) is None


def test_holdout_rate_treats_out_of_range_aggregate_value_as_missing(tmp_path):
    result = tmp_path / "result.json"
    result.write_text(json.dumps({"holdout_resolved_rate": 1.2}), encoding="utf-8")
    assert holdout_rate(json.loads(result.read_text(encoding="utf-8"))) is None

    result.write_text(json.dumps({"holdout_resolved_rate": -0.1}), encoding="utf-8")
    assert holdout_rate(json.loads(result.read_text(encoding="utf-8"))) is None


def test_holdout_cases_reads_aggregate_only_value(tmp_path):
    result = tmp_path / "result.json"
    result.write_text(json.dumps({"holdout_cases": 12}), encoding="utf-8")

    assert holdout_cases(json.loads(result.read_text(encoding="utf-8"))) == 12


def test_holdout_cases_treats_negative_or_fractional_aggregate_value_as_zero(tmp_path):
    result = tmp_path / "result.json"
    result.write_text(json.dumps({"holdout_cases": -12}), encoding="utf-8")
    assert holdout_cases(json.loads(result.read_text(encoding="utf-8"))) == 0

    result.write_text(json.dumps({"holdout_cases": 12.5}), encoding="utf-8")
    assert holdout_cases(json.loads(result.read_text(encoding="utf-8"))) == 0


def test_smoke_contract_axis_count_treats_negative_or_fractional_value_as_zero(tmp_path):
    result = tmp_path / "result.json"
    result.write_text(
        json.dumps(
            {
                "implementation_metadata": {
                    "probe_axis_coverage": {"smoke_contract_axis_count": -1},
                }
            }
        ),
        encoding="utf-8",
    )
    assert smoke_contract_axis_count(json.loads(result.read_text(encoding="utf-8"))) == 0

    result.write_text(
        json.dumps(
            {
                "implementation_metadata": {
                    "probe_axis_coverage": {"smoke_contract_axis_count": 1.5},
                }
            }
        ),
        encoding="utf-8",
    )
    assert smoke_contract_axis_count(json.loads(result.read_text(encoding="utf-8"))) == 0


def test_main_min_smoke_axis_gate_blocks_package(tmp_path, monkeypatch):
    commands = []

    monkeypatch.setattr("scripts.run_official_closed_loop.load_sample_catalog", lambda _path: [])
    monkeypatch.setattr(
        "scripts.run_official_closed_loop.select_sample",
        lambda _catalog, _instance_id: argparse.Namespace(
            cleanroom_image="programbench/owner_1776_repo.abcdef0:task_cleanroom"
        ),
    )

    def fake_run_command(command):
        commands.append(command)
        if "main.py" in command:
            output_root = command[command.index("--output") + 1]
            target = tmp_path / "runs" / "owner__repo.abcdef0" / "generated" / "owner__repo.abcdef0" / "owner__repo.abcdef0"
            assert output_root == str(target.parent)
            target.mkdir(parents=True)
            (target / "result.json").write_text(
                json.dumps(
                    {
                        "task_id": "owner__repo.abcdef0",
                        "holdout_cases": 12,
                        "holdout_resolved_rate": 1.0,
                        "implementation_metadata": {
                            "probe_axis_coverage": {
                                "smoke_contract_axis_count": 1,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

    monkeypatch.setattr("scripts.run_official_closed_loop.run_command", fake_run_command)

    try:
        run_closed_loop_main(
            [
                "owner__repo.abcdef0",
                "--catalog",
                "fake.json",
                "--runs",
                str(tmp_path / "runs"),
                "--official-eval-root",
                str(tmp_path / "eval"),
                "--min-smoke-contract-axes",
                "2",
                "--skip-official-eval",
            ]
        )
    except SystemExit as exc:
        assert exc.code == 3
    else:
        raise AssertionError("expected smoke-axis gate SystemExit")

    assert not any("scripts/package_submission.py" in command for command in commands)
    assert not any("eval" in command for command in commands)


def test_main_runtime_smoke_dimension_gate_blocks_package(tmp_path, monkeypatch):
    commands = []

    monkeypatch.setattr("scripts.run_official_closed_loop.load_sample_catalog", lambda _path: [])
    monkeypatch.setattr(
        "scripts.run_official_closed_loop.select_sample",
        lambda _catalog, _instance_id: argparse.Namespace(
            cleanroom_image="programbench/owner_1776_repo.abcdef0:task_cleanroom"
        ),
    )

    def fake_run_command(command):
        commands.append(command)
        if "main.py" in command:
            output_root = command[command.index("--output") + 1]
            target = tmp_path / "runs" / "owner__repo.abcdef0" / "generated" / "owner__repo.abcdef0" / "owner__repo.abcdef0"
            assert output_root == str(target.parent)
            target.mkdir(parents=True)
            (target / "result.json").write_text(
                json.dumps(
                    {
                        "task_id": "owner__repo.abcdef0",
                        "holdout_cases": 12,
                        "holdout_resolved_rate": 1.0,
                        "implementation_metadata": {
                            "probe_axis_coverage": {
                                "smoke_contract_axis_count": 2,
                            },
                            "runtime_smoke": {
                                "status": "passed",
                                "input_dimensions": ["args"],
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

    monkeypatch.setattr("scripts.run_official_closed_loop.run_command", fake_run_command)

    try:
        run_closed_loop_main(
            [
                "owner__repo.abcdef0",
                "--catalog",
                "fake.json",
                "--runs",
                str(tmp_path / "runs"),
                "--official-eval-root",
                str(tmp_path / "eval"),
                "--require-runtime-smoke-dimensions",
                "args,input_files",
                "--skip-official-eval",
            ]
        )
    except SystemExit as exc:
        assert exc.code == 3
    else:
        raise AssertionError("expected runtime-smoke dimension gate SystemExit")

    assert not any("scripts/package_submission.py" in command for command in commands)
    assert not any("eval" in command for command in commands)


def test_main_invalid_result_json_blocks_package(tmp_path, monkeypatch):
    commands = []

    monkeypatch.setattr("scripts.run_official_closed_loop.load_sample_catalog", lambda _path: [])
    monkeypatch.setattr(
        "scripts.run_official_closed_loop.select_sample",
        lambda _catalog, _instance_id: argparse.Namespace(
            cleanroom_image="programbench/owner_1776_repo.abcdef0:task_cleanroom"
        ),
    )

    def fake_run_command(command):
        commands.append(command)
        if "main.py" in command:
            target = tmp_path / "runs" / "owner__repo.abcdef0" / "generated" / "owner__repo.abcdef0" / "owner__repo.abcdef0"
            target.mkdir(parents=True)
            (target / "result.json").write_text("{", encoding="utf-8")

    monkeypatch.setattr("scripts.run_official_closed_loop.run_command", fake_run_command)

    try:
        run_closed_loop_main(
            [
                "owner__repo.abcdef0",
                "--catalog",
                "fake.json",
                "--runs",
                str(tmp_path / "runs"),
                "--official-eval-root",
                str(tmp_path / "eval"),
            ]
        )
    except SystemExit as exc:
        assert exc.code == 3
    else:
        raise AssertionError("expected invalid result payload gate SystemExit")

    assert not any("scripts/package_submission.py" in command for command in commands)
    assert not any("eval" in command for command in commands)


def test_main_malformed_result_aggregate_values_block_package(tmp_path, monkeypatch):
    commands = []

    monkeypatch.setattr("scripts.run_official_closed_loop.load_sample_catalog", lambda _path: [])
    monkeypatch.setattr(
        "scripts.run_official_closed_loop.select_sample",
        lambda _catalog, _instance_id: argparse.Namespace(
            cleanroom_image="programbench/owner_1776_repo.abcdef0:task_cleanroom"
        ),
    )

    def fake_run_command(command):
        commands.append(command)
        if "main.py" in command:
            target = tmp_path / "runs" / "owner__repo.abcdef0" / "generated" / "owner__repo.abcdef0" / "owner__repo.abcdef0"
            target.mkdir(parents=True)
            (target / "result.json").write_text(
                json.dumps(
                    {
                        "task_id": "owner__repo.abcdef0",
                        "holdout_cases": "many",
                        "holdout_resolved_rate": "complete",
                        "implementation_metadata": {
                            "probe_axis_coverage": {
                                "smoke_contract_axis_count": "enough",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

    monkeypatch.setattr("scripts.run_official_closed_loop.run_command", fake_run_command)

    try:
        run_closed_loop_main(
            [
                "owner__repo.abcdef0",
                "--catalog",
                "fake.json",
                "--runs",
                str(tmp_path / "runs"),
                "--official-eval-root",
                str(tmp_path / "eval"),
            ]
        )
    except SystemExit as exc:
        assert exc.code == 3
    else:
        raise AssertionError("expected malformed result aggregate gate SystemExit")

    assert not any("scripts/package_submission.py" in command for command in commands)
    assert not any("eval" in command for command in commands)


def test_should_retry_near_miss_only_for_close_local_holdout():
    parsed = args()

    assert should_retry_near_miss(parsed, 0.7826)
    assert not should_retry_near_miss(parsed, 0.5)
    assert not should_retry_near_miss(parsed, 0.8)
    assert not should_retry_near_miss(args(max_repairs=5, near_miss_max_repairs=5), 0.7826)


def test_apply_strategy_variant_maps_safe_params_to_closed_loop_args():
    parsed = args(probe_iterations=10, min_probe_samples=50, max_repairs=3, adaptive_probes="disabled")
    variant = StrategyVariant(
        variant_id="adaptive_deep",
        strategy="closed_loop",
        params={
            "use_adaptive_probes": True,
            "probe_budget": 24,
            "min_samples": 80,
            "max_repair_attempts": 5,
        },
    )

    apply_strategy_variant(parsed, variant)

    assert parsed.adaptive_probes == "enabled"
    assert parsed.probe_iterations == 24
    assert parsed.min_probe_samples == 80
    assert parsed.max_repairs == 5


def test_select_strategy_variant_uses_registry_history(tmp_path):
    registry_path = tmp_path / "experiments.jsonl"
    ExperimentRegistry(registry_path).append(
        ExperimentRun(
            run_id="baseline-1",
            instance_id="owner__repo.abcdef0",
            variant=StrategyVariant(
                variant_id="baseline_no_adaptive",
                strategy="closed_loop",
                params={"use_adaptive_probes": False},
            ),
            official=AggregateFeedback(score=0.9, passed_tests=9, total_tests=10, pass_rate=0.9),
            holdout_cases=10,
        )
    )

    selected = select_strategy_variant(args(strategy_registry=str(registry_path)))

    assert selected.variant_id == "baseline_no_adaptive"


def test_record_strategy_experiment_writes_aggregate_only_registry(tmp_path):
    parsed = args(
        runs=str(tmp_path / "runs"),
        strategy_registry=str(tmp_path / "experiments.jsonl"),
    )
    paths = build_paths(parsed.instance_id, parsed.runs, tmp_path / "eval", "submission_owner_repo")
    paths.result.parent.mkdir(parents=True)
    paths.result.write_text(json.dumps({"holdout_cases": 12}), encoding="utf-8")
    paths.eval_json.parent.mkdir(parents=True)
    paths.eval_json.write_text(
        json.dumps(
            {
                "test_results": [
                    {"name": "hidden_case_a", "branch": "hidden", "status": "passed", "stdout": "secret"},
                    {"name": "hidden_case_b", "branch": "hidden", "status": "failure", "stderr": "secret"},
                ],
                "error_code": None,
                "error_details": "do not store this",
                "warnings": ["do not store warning text"],
            }
        ),
        encoding="utf-8",
    )

    path = record_strategy_experiment(
        args=parsed,
        paths=paths,
        variant=StrategyVariant(
            variant_id="adaptive_profile",
            strategy="closed_loop",
            params={"use_adaptive_probes": True},
        ),
    )

    assert path == tmp_path / "experiments.jsonl"
    rows = ExperimentRegistry(path).load()
    assert len(rows) == 1
    assert rows[0].official.passed_tests == 1
    assert rows[0].official.total_tests == 2
    assert rows[0].official.warning_count == 1
    serialized = path.read_text(encoding="utf-8")
    assert "hidden_case" not in serialized
    assert "secret" not in serialized
    assert "do not store" not in serialized


def test_main_applies_selected_strategy_before_rebuilder_and_skip_eval_does_not_append(tmp_path, monkeypatch):
    registry_path = tmp_path / "experiments.jsonl"
    ExperimentRegistry(registry_path).append(
        ExperimentRun(
            run_id="baseline-1",
            instance_id="owner__repo.abcdef0",
            variant=StrategyVariant(
                variant_id="baseline_no_adaptive",
                strategy="closed_loop",
                params={"use_adaptive_probes": False},
            ),
            official=AggregateFeedback(score=0.9, passed_tests=9, total_tests=10, pass_rate=0.9),
            holdout_cases=10,
        )
    )
    commands = []

    monkeypatch.setattr("scripts.run_official_closed_loop.load_sample_catalog", lambda _path: [])
    monkeypatch.setattr(
        "scripts.run_official_closed_loop.select_sample",
        lambda _catalog, _instance_id: argparse.Namespace(
            cleanroom_image="programbench/owner_1776_repo.abcdef0:task_cleanroom"
        ),
    )

    def fake_run_command(command):
        commands.append(command)
        if "main.py" in command:
            output_root = command[command.index("--output") + 1]
            result_path = tmp_path / "runs" / "owner__repo.abcdef0" / "generated" / "owner__repo.abcdef0"
            assert output_root == str(result_path)
            target = result_path / "owner__repo.abcdef0"
            target.mkdir(parents=True)
            (target / "result.json").write_text(
                json.dumps({"holdout_cases": 12, "holdout_resolved_rate": 1.0}),
                encoding="utf-8",
            )

    monkeypatch.setattr("scripts.run_official_closed_loop.run_command", fake_run_command)

    run_closed_loop_main(
        [
            "owner__repo.abcdef0",
            "--catalog",
            "fake.json",
            "--runs",
            str(tmp_path / "runs"),
            "--official-eval-root",
            str(tmp_path / "eval"),
            "--strategy-registry",
            str(registry_path),
            "--skip-official-eval",
        ]
    )

    rebuilder_command = next(command for command in commands if "main.py" in command)
    assert rebuilder_command[rebuilder_command.index("--adaptive-probes") + 1] == "disabled"
    assert any("scripts/package_submission.py" in command for command in commands)
    assert not any("eval" in command for command in commands)
    assert len(ExperimentRegistry(registry_path).load()) == 1


def test_main_does_not_append_strategy_registry_when_holdout_gate_blocks(tmp_path, monkeypatch):
    registry_path = tmp_path / "experiments.jsonl"
    ExperimentRegistry(registry_path).append(
        ExperimentRun(
            run_id="adaptive-1",
            instance_id="owner__repo.abcdef0",
            variant=StrategyVariant(
                variant_id="adaptive_profile",
                strategy="closed_loop",
                params={"use_adaptive_probes": True},
            ),
            official=AggregateFeedback(score=0.8, passed_tests=8, total_tests=10, pass_rate=0.8),
            holdout_cases=10,
        )
    )
    commands = []

    monkeypatch.setattr("scripts.run_official_closed_loop.load_sample_catalog", lambda _path: [])
    monkeypatch.setattr(
        "scripts.run_official_closed_loop.select_sample",
        lambda _catalog, _instance_id: argparse.Namespace(
            cleanroom_image="programbench/owner_1776_repo.abcdef0:task_cleanroom"
        ),
    )

    def fake_run_command(command):
        commands.append(command)
        if "main.py" in command:
            output_root = command[command.index("--output") + 1]
            target = tmp_path / "runs" / "owner__repo.abcdef0" / "generated" / "owner__repo.abcdef0" / "owner__repo.abcdef0"
            assert output_root == str(target.parent)
            target.mkdir(parents=True)
            (target / "result.json").write_text(
                json.dumps({"holdout_cases": 12, "holdout_resolved_rate": 0.4}),
                encoding="utf-8",
            )

    monkeypatch.setattr("scripts.run_official_closed_loop.run_command", fake_run_command)

    try:
        run_closed_loop_main(
            [
                "owner__repo.abcdef0",
                "--catalog",
                "fake.json",
                "--runs",
                str(tmp_path / "runs"),
                "--official-eval-root",
                str(tmp_path / "eval"),
                "--strategy-registry",
                str(registry_path),
            ]
        )
    except SystemExit as exc:
        assert exc.code == 3
    else:
        raise AssertionError("expected holdout gate SystemExit")

    assert not any("scripts/package_submission.py" in command for command in commands)
    assert not any("eval" in command for command in commands)
    assert len(ExperimentRegistry(registry_path).load()) == 1


def test_main_require_holdout_improvement_blocks_package_for_regression(tmp_path, monkeypatch):
    history = tmp_path / "history"
    best = history / "old" / "owner__repo.abcdef0" / "generated" / "owner__repo.abcdef0" / "result.json"
    best.parent.mkdir(parents=True)
    best.write_text(
        json.dumps(
            {
                "task_id": "owner__repo.abcdef0",
                "holdout_cases": 12,
                "holdout_resolved_rate": 0.95,
            }
        ),
        encoding="utf-8",
    )
    commands = []

    monkeypatch.setattr("scripts.run_official_closed_loop.load_sample_catalog", lambda _path: [])
    monkeypatch.setattr(
        "scripts.run_official_closed_loop.select_sample",
        lambda _catalog, _instance_id: argparse.Namespace(
            cleanroom_image="programbench/owner_1776_repo.abcdef0:task_cleanroom"
        ),
    )

    def fake_run_command(command):
        commands.append(command)
        if "main.py" in command:
            output_root = command[command.index("--output") + 1]
            target = tmp_path / "runs" / "owner__repo.abcdef0" / "generated" / "owner__repo.abcdef0" / "owner__repo.abcdef0"
            assert output_root == str(target.parent)
            target.mkdir(parents=True)
            (target / "result.json").write_text(
                json.dumps(
                    {
                        "task_id": "owner__repo.abcdef0",
                        "holdout_cases": 12,
                        "holdout_resolved_rate": 0.9,
                    }
                ),
                encoding="utf-8",
            )

    monkeypatch.setattr("scripts.run_official_closed_loop.run_command", fake_run_command)

    try:
        run_closed_loop_main(
            [
                "owner__repo.abcdef0",
                "--catalog",
                "fake.json",
                "--runs",
                str(tmp_path / "runs"),
                "--official-eval-root",
                str(tmp_path / "eval"),
                "--require-holdout-improvement",
                "--holdout-history-root",
                str(history),
            ]
        )
    except SystemExit as exc:
        assert exc.code == 3
    else:
        raise AssertionError("expected holdout improvement gate SystemExit")

    assert not any("scripts/package_submission.py" in command for command in commands)
    assert not any("eval" in command for command in commands)


def test_main_require_holdout_improvement_blocks_small_delta(tmp_path, monkeypatch):
    history = tmp_path / "history"
    best = history / "old" / "owner__repo.abcdef0" / "generated" / "owner__repo.abcdef0" / "result.json"
    best.parent.mkdir(parents=True)
    best.write_text(
        json.dumps(
            {
                "task_id": "owner__repo.abcdef0",
                "holdout_cases": 12,
                "holdout_resolved_rate": 0.89,
            }
        ),
        encoding="utf-8",
    )
    commands = []

    monkeypatch.setattr("scripts.run_official_closed_loop.load_sample_catalog", lambda _path: [])
    monkeypatch.setattr(
        "scripts.run_official_closed_loop.select_sample",
        lambda _catalog, _instance_id: argparse.Namespace(
            cleanroom_image="programbench/owner_1776_repo.abcdef0:task_cleanroom"
        ),
    )

    def fake_run_command(command):
        commands.append(command)
        if "main.py" in command:
            output_root = command[command.index("--output") + 1]
            target = tmp_path / "runs" / "owner__repo.abcdef0" / "generated" / "owner__repo.abcdef0" / "owner__repo.abcdef0"
            assert output_root == str(target.parent)
            target.mkdir(parents=True)
            (target / "result.json").write_text(
                json.dumps(
                    {
                        "task_id": "owner__repo.abcdef0",
                        "holdout_cases": 12,
                        "holdout_resolved_rate": 0.9,
                    }
                ),
                encoding="utf-8",
            )

    monkeypatch.setattr("scripts.run_official_closed_loop.run_command", fake_run_command)

    try:
        run_closed_loop_main(
            [
                "owner__repo.abcdef0",
                "--catalog",
                "fake.json",
                "--runs",
                str(tmp_path / "runs"),
                "--official-eval-root",
                str(tmp_path / "eval"),
                "--require-holdout-improvement",
                "--min-holdout-improvement-delta",
                "0.02",
                "--holdout-history-root",
                str(history),
            ]
        )
    except SystemExit as exc:
        assert exc.code == 3
    else:
        raise AssertionError("expected holdout improvement delta gate SystemExit")

    assert not any("scripts/package_submission.py" in command for command in commands)
    assert not any("eval" in command for command in commands)


def test_main_require_holdout_improvement_allows_package_for_new_best(tmp_path, monkeypatch):
    history = tmp_path / "history"
    best = history / "old" / "owner__repo.abcdef0" / "generated" / "owner__repo.abcdef0" / "result.json"
    best.parent.mkdir(parents=True)
    best.write_text(
        json.dumps(
            {
                "task_id": "owner__repo.abcdef0",
                "holdout_cases": 12,
                "holdout_resolved_rate": 0.85,
            }
        ),
        encoding="utf-8",
    )
    commands = []

    monkeypatch.setattr("scripts.run_official_closed_loop.load_sample_catalog", lambda _path: [])
    monkeypatch.setattr(
        "scripts.run_official_closed_loop.select_sample",
        lambda _catalog, _instance_id: argparse.Namespace(
            cleanroom_image="programbench/owner_1776_repo.abcdef0:task_cleanroom"
        ),
    )

    def fake_run_command(command):
        commands.append(command)
        if "main.py" in command:
            output_root = command[command.index("--output") + 1]
            target = tmp_path / "runs" / "owner__repo.abcdef0" / "generated" / "owner__repo.abcdef0" / "owner__repo.abcdef0"
            assert output_root == str(target.parent)
            target.mkdir(parents=True)
            (target / "result.json").write_text(
                json.dumps(
                    {
                        "task_id": "owner__repo.abcdef0",
                        "holdout_cases": 12,
                        "holdout_resolved_rate": 0.9,
                    }
                ),
                encoding="utf-8",
            )

    monkeypatch.setattr("scripts.run_official_closed_loop.run_command", fake_run_command)

    run_closed_loop_main(
        [
            "owner__repo.abcdef0",
            "--catalog",
            "fake.json",
            "--runs",
            str(tmp_path / "runs"),
            "--official-eval-root",
            str(tmp_path / "eval"),
            "--require-holdout-improvement",
            "--holdout-history-root",
            str(history),
            "--skip-official-eval",
        ]
    )

    assert any("scripts/package_submission.py" in command for command in commands)
    assert not any("eval" in command for command in commands)
