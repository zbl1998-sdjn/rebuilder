import subprocess
import sys


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
