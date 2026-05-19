import subprocess
import sys
import json


def test_package_submission_script_can_show_help():
    result = subprocess.run(
        [sys.executable, "scripts/package_submission.py", "--help"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Package generated code as ProgramBench submission" in result.stdout


def test_summarize_eval_script_can_show_help():
    result = subprocess.run(
        [sys.executable, "scripts/summarize_programbench_eval.py", "--help"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Summarize ProgramBench eval JSON" in result.stdout


def test_official_strategy_ablation_script_can_show_help():
    result = subprocess.run(
        [sys.executable, "scripts/run_official_strategy_ablation.py", "--help"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Run official ProgramBench strategy ablations" in result.stdout


def test_summarize_eval_script_outputs_raw_and_counted_metrics(tmp_path):
    eval_path = tmp_path / "sample.eval.json"
    eval_path.write_text(
        json.dumps(
            {
                "test_results": [
                    {"name": "kept", "branch": "active", "status": "passed"},
                    {"name": "ignored_case", "branch": "active", "status": "failure"},
                    {"name": "ignored_branch_case", "branch": "ignored", "status": "failure"},
                ],
                "test_branches": ["active", "ignored"],
            }
        ),
        encoding="utf-8",
    )
    tests_dir = (
        tmp_path
        / "programbench_repo"
        / "src"
        / "programbench"
        / "data"
        / "tasks"
        / "owner__repo.abcdef0"
    )
    tests_dir.mkdir(parents=True)
    (tests_dir / "tests.json").write_text(
        json.dumps(
            {
                "branches": {
                    "active": {
                        "ignored": False,
                        "ignored_tests": [{"name": "ignored_case"}],
                    },
                    "ignored": {"ignored": True, "ignored_tests": []},
                }
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/summarize_programbench_eval.py",
            str(eval_path),
            "--instance-id",
            "owner__repo.abcdef0",
            "--programbench-repo",
            str(tmp_path / "programbench_repo"),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "raw_tests=3" in result.stdout
    assert "counted_tests=1" in result.stdout
    assert "counted_score=100" in result.stdout
