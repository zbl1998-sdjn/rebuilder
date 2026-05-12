import argparse
import json

from scripts.run_official_closed_loop import (
    build_paths,
    build_programbench_eval_command,
    build_rebuilder_command,
    build_package_command,
    holdout_cases,
    holdout_rate,
    should_retry_near_miss,
)


def args(**overrides):
    defaults = {
        "instance_id": "owner__repo.abcdef0",
        "runs": "runs/closed_loop",
        "config": "config/settings.yaml",
        "probe_iterations": 60,
        "max_repairs": 3,
        "replacement_executor": "wsl",
        "static_output_assets": "disabled",
        "min_holdout_rate": 0.8,
        "min_holdout_cases": 10,
        "near_miss_holdout_rate": 0.75,
        "near_miss_max_repairs": 5,
        "programbench_python": "py",
        "programbench_python_version": "3.14",
        "workers": 1,
        "branch_workers": 1,
        "docker_cpus": 4,
        "branch_retries": 1,
        "force": True,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


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
    assert command[command.index("--probe-iterations") + 1] == "60"
    assert "wsl" in command


def test_build_rebuilder_command_allows_repair_override():
    parsed = args()
    paths = build_paths(parsed.instance_id, parsed.runs, "runs/eval")

    command = build_rebuilder_command(parsed, paths, "programbench/owner_1776_repo.abcdef0:task_cleanroom", max_repairs=5)

    assert command[command.index("--max-repairs") + 1] == "5"


def test_build_programbench_eval_command_uses_python_import_entrypoint():
    parsed = args()
    paths = build_paths(parsed.instance_id, parsed.runs, "runs/eval")

    command = build_programbench_eval_command(parsed, paths)

    assert command[:4] == ["py", "-3.14", "-c", "from programbench.cli.main import app; app()"]
    assert "--force" in command
    assert str(paths.submission_root) in command


def test_build_package_command_passes_holdout_case_gate():
    parsed = args()
    paths = build_paths(parsed.instance_id, parsed.runs, "runs/eval")

    command = build_package_command(parsed, paths)

    assert command[command.index("--min-holdout-rate") + 1] == "0.8"
    assert command[command.index("--min-holdout-cases") + 1] == "10"


def test_holdout_rate_reads_aggregate_only_value(tmp_path):
    result = tmp_path / "result.json"
    result.write_text(json.dumps({"holdout_resolved_rate": 0.875}), encoding="utf-8")

    assert holdout_rate(json.loads(result.read_text(encoding="utf-8"))) == 0.875


def test_holdout_cases_reads_aggregate_only_value(tmp_path):
    result = tmp_path / "result.json"
    result.write_text(json.dumps({"holdout_cases": 12}), encoding="utf-8")

    assert holdout_cases(json.loads(result.read_text(encoding="utf-8"))) == 12


def test_should_retry_near_miss_only_for_close_local_holdout():
    parsed = args()

    assert should_retry_near_miss(parsed, 0.7826)
    assert not should_retry_near_miss(parsed, 0.5)
    assert not should_retry_near_miss(parsed, 0.8)
    assert not should_retry_near_miss(args(max_repairs=5, near_miss_max_repairs=5), 0.7826)
