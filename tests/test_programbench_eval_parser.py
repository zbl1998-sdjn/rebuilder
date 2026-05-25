import json

from core.evaluation.programbench import ProgramBenchEvalParser


def test_programbench_eval_parser_computes_pass_rate(tmp_path):
    path = tmp_path / "sample.eval.json"
    path.write_text(
        json.dumps(
            {
                "test_results": [
                    {"name": "a", "status": "passed"},
                    {"name": "b", "status": "failure"},
                    {"name": "c", "status": "passed"},
                ],
                "error_code": None,
                "warnings": ["w"],
            }
        ),
        encoding="utf-8",
    )

    summary = ProgramBenchEvalParser().parse(path)

    assert summary.total_tests == 3
    assert summary.passed_tests == 2
    assert summary.pass_rate == 2 / 3
    assert not summary.fully_resolved
    assert summary.warnings == ["w"]


def test_programbench_eval_parser_marks_empty_error_run():
    summary = ProgramBenchEvalParser().from_payload(
        {"test_results": [], "error_code": "build_failed", "error_details": "no compile"}
    )

    assert summary.total_tests == 0
    assert summary.pass_rate == 0.0
    assert summary.error_code == "build_failed"


def test_programbench_eval_parser_surfaces_branch_read_errors():
    summary = ProgramBenchEvalParser().from_payload(
        {
            "test_results": [
                {
                    "name": "case",
                    "branch": "active",
                    "status": "not_run",
                    "extra": {"error_code": "results_read_failed"},
                }
            ],
            "test_branch_errors": {
                "active": [
                    {
                        "error_code": "results_read_failed",
                        "error_details": "cat: eval/results.xml: No such file or directory",
                    }
                ]
            },
        }
    )

    assert summary.total_tests == 1
    assert summary.passed_tests == 0
    assert summary.error_code == "results_read_failed"
    assert "eval/results.xml" in (summary.error_details or "")


def test_programbench_eval_parser_counts_malformed_result_items_as_failures():
    summary = ProgramBenchEvalParser().from_payload(
        {
            "test_results": [
                {"name": "passed", "status": "passed"},
                "not-a-result-object",
                None,
                {"name": "failed", "status": "failure"},
            ]
        }
    )

    assert summary.total_tests == 4
    assert summary.passed_tests == 1
    assert summary.pass_rate == 0.25
    assert not summary.fully_resolved


def test_programbench_eval_parser_treats_invalid_payload_as_error_summary(tmp_path):
    path = tmp_path / "sample.eval.json"
    path.write_text("{", encoding="utf-8")

    summary = ProgramBenchEvalParser().parse(path)

    assert summary.total_tests == 0
    assert summary.passed_tests == 0
    assert summary.pass_rate == 0.0
    assert summary.error_code == "invalid_eval_payload"


def test_programbench_eval_parser_treats_malformed_warnings_as_empty():
    summary = ProgramBenchEvalParser().from_payload({"test_results": [], "warnings": "not-a-list"})

    assert summary.warnings == []


def test_programbench_eval_parser_filters_ignored_branches_and_tests(tmp_path):
    eval_path = tmp_path / "sample.eval.json"
    eval_path.write_text(
        json.dumps(
            {
                "test_results": [
                    {"name": "kept_pass", "branch": "active", "status": "passed"},
                    {"name": "ignored_case", "branch": "active", "status": "failure"},
                    {"name": "ignored_branch_case", "branch": "ignored", "status": "failure"},
                ],
                "test_branches": ["active", "ignored"],
                "warnings": ["branch ignored was flaky"],
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
                    "ignored": {
                        "ignored": True,
                        "ignored_tests": [],
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    summary = ProgramBenchEvalParser().parse(
        eval_path,
        instance_id="owner__repo.abcdef0",
        programbench_repo=tmp_path / "programbench_repo",
    )

    assert summary.total_tests == 1
    assert summary.passed_tests == 1
    assert summary.pass_rate == 1.0
    assert summary.score == 1.0
    assert summary.warnings == []


def test_programbench_eval_parser_ignores_inactive_branch_errors_when_filtering(tmp_path):
    eval_path = tmp_path / "sample.eval.json"
    eval_path.write_text(
        json.dumps(
            {
                "test_results": [
                    {"name": "kept_pass", "branch": "active", "status": "passed"},
                    {"name": "ignored_case", "branch": "ignored", "status": "not_run"},
                ],
                "test_branches": ["active", "ignored"],
                "test_branch_errors": {
                    "ignored": [
                        {
                            "error_code": "results_read_failed",
                            "error_details": "ignored branch output missing",
                        }
                    ]
                },
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
                    "active": {"ignored": False, "ignored_tests": []},
                    "ignored": {"ignored": True, "ignored_tests": []},
                }
            }
        ),
        encoding="utf-8",
    )

    summary = ProgramBenchEvalParser().parse(
        eval_path,
        instance_id="owner__repo.abcdef0",
        programbench_repo=tmp_path / "programbench_repo",
    )

    assert summary.total_tests == 1
    assert summary.passed_tests == 1
    assert summary.error_code is None


def test_programbench_eval_parser_filters_malformed_result_items(tmp_path):
    eval_path = tmp_path / "sample.eval.json"
    eval_path.write_text(
        json.dumps(
            {
                "test_results": [
                    {"name": "kept_pass", "branch": "active", "status": "passed"},
                    "not-a-result-object",
                    {"name": "kept_fail", "branch": "active", "status": "failure"},
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
                    "active": {"ignored": False, "ignored_tests": []},
                    "ignored": {"ignored": True, "ignored_tests": []},
                }
            }
        ),
        encoding="utf-8",
    )

    summary = ProgramBenchEvalParser().parse(
        eval_path,
        instance_id="owner__repo.abcdef0",
        programbench_repo=tmp_path / "programbench_repo",
    )

    assert summary.total_tests == 2
    assert summary.passed_tests == 1
    assert summary.pass_rate == 0.5
