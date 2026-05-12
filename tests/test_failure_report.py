import json

import pytest

from core.data_models import DiffReport, TestCase, TestResult
from core.evaluation.failure_report import FailureReportWriter


def report(
    name: str,
    stdout_match: bool = True,
    stderr_match: bool = True,
    exit_code_match: bool = True,
) -> DiffReport:
    return DiffReport(
        test_case=TestCase(name=name, args=["--help"]),
        original_result=TestResult(stdout="expected output\n", stderr="", exit_code=0),
        replacement_result=TestResult(stdout="actual output\n", stderr="wrong\n", exit_code=2),
        stdout_match=stdout_match,
        stderr_match=stderr_match,
        exit_code_match=exit_code_match,
        file_outputs_match=True,
    )


def test_failure_report_writer_outputs_clustered_exploration_reports(tmp_path):
    writer = FailureReportWriter()

    paths = writer.write(
        reports=[
            report("help", stdout_match=False),
            report("bad_args", stdout_match=False, exit_code_match=False),
        ],
        output_dir=tmp_path,
        task_id="sample.task",
        scope="exploration",
    )

    payload = json.loads(paths.json_path.read_text(encoding="utf-8"))
    markdown = paths.markdown_path.read_text(encoding="utf-8")

    assert payload["task_id"] == "sample.task"
    assert payload["scope"] == "exploration"
    assert payload["total_failures"] == 2
    assert {cluster["kind"] for cluster in payload["clusters"]} == {"stdout", "multiple"}
    assert payload["clusters"][0]["representative"]["test_name"]
    assert "Failure Report: sample.task" in markdown
    assert "scope: exploration" in markdown
    assert "bad_args" in markdown


def test_failure_report_writer_rejects_detailed_holdout_reports(tmp_path):
    writer = FailureReportWriter()

    with pytest.raises(ValueError, match="holdout"):
        writer.write(
            reports=[report("held_out", stdout_match=False)],
            output_dir=tmp_path,
            task_id="sample.task",
            scope="holdout",
        )
