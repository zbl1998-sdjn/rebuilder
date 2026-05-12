import argparse
import json

from scripts.run_official_closed_loop import (
    build_paths,
    build_programbench_eval_command,
    build_rebuilder_command,
    holdout_rate,
)


def args(**overrides):
    defaults = {
        "instance_id": "owner__repo.abcdef0",
        "runs": "runs/closed_loop",
        "config": "config/settings.yaml",
        "max_repairs": 3,
        "replacement_executor": "wsl",
        "static_output_assets": "disabled",
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
    assert "wsl" in command


def test_build_programbench_eval_command_uses_python_import_entrypoint():
    parsed = args()
    paths = build_paths(parsed.instance_id, parsed.runs, "runs/eval")

    command = build_programbench_eval_command(parsed, paths)

    assert command[:4] == ["py", "-3.14", "-c", "from programbench.cli.main import app; app()"]
    assert "--force" in command
    assert str(paths.submission_root) in command


def test_holdout_rate_reads_aggregate_only_value(tmp_path):
    result = tmp_path / "result.json"
    result.write_text(json.dumps({"holdout_resolved_rate": 0.875}), encoding="utf-8")

    assert holdout_rate(json.loads(result.read_text(encoding="utf-8"))) == 0.875
