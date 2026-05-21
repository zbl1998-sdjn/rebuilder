import importlib
import json
import subprocess
import sys

import pytest


def load_module():
    try:
        return importlib.import_module("scripts.audit_official_generalization_gaps")
    except ModuleNotFoundError:
        pytest.fail("scripts.audit_official_generalization_gaps is not implemented yet")


def write_baseline(
    path,
    task_id,
    score,
    *,
    passed_tests=None,
    hidden_marker=None,
    submission_path=None,
):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "instance_id": task_id,
        "official": {
            "score": score,
            "passed_tests": score if passed_tests is None else passed_tests,
            "total_tests": 100,
            "pass_rate": (score if passed_tests is None else passed_tests) / 100,
            "fully_resolved": False,
            "almost_resolved": False,
        },
    }
    if hidden_marker:
        payload["official"]["hidden_failure_details"] = [{"name": hidden_marker}]
        payload["notes"] = f"do not print {hidden_marker}"
    if submission_path is not None:
        payload["submission"] = {"path": str(submission_path)}
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_eval_json(path, statuses):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "test_results": [
                    {"branch": "main", "name": f"case-{index}", "status": status}
                    for index, status in enumerate(statuses)
                ]
            }
        ),
        encoding="utf-8",
    )


def write_result(
    path,
    task_id,
    *,
    local_rate=1.0,
    holdout_rate=1.0,
    holdout_cases=12,
    official_score=0,
    official_passed=0,
    official_raw_passed=None,
    official_raw_total=100,
    hidden_raw_marker=None,
    runtime_dimensions=("args", "input_files", "stdin"),
    probe_axis_coverage=None,
):
    if probe_axis_coverage is None:
        probe_axis_coverage = {
            "smoke_contract_axis_count": 5,
            "adaptive_axis_count": 5,
        }
    target = path / task_id / "generated" / task_id
    target.mkdir(parents=True)
    result_path = target / "result.json"
    result_path.write_text(
        json.dumps(
            {
                "task_id": task_id,
                "status": "success",
                "resolved_rate": local_rate,
                "holdout_resolved_rate": holdout_rate,
                "holdout_cases": holdout_cases,
                "probes_conducted": 20,
                "iterations_used": 2,
                "implementation_metadata": {
                    "probe_axis_coverage": probe_axis_coverage,
                    "runtime_smoke": {
                        "status": "passed",
                        "case_count": 4,
                        "contract_case_count": 4,
                        "input_dimensions": list(runtime_dimensions),
                    },
                },
                "official_eval_summary": {
                    "counted": {
                        "score": official_score,
                        "passed_tests": official_passed,
                        "total_tests": 100,
                        "pass_rate": official_passed / 100,
                        "fully_resolved": False,
                        "almost_resolved": False,
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    if official_raw_passed is not None:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        raw_summary = {
            "score": round((official_raw_passed / official_raw_total) * 100)
            if official_raw_total
            else 0,
            "passed_tests": official_raw_passed,
            "total_tests": official_raw_total,
            "pass_rate": official_raw_passed / official_raw_total
            if official_raw_total
            else 0.0,
            "fully_resolved": official_raw_total > 0
            and official_raw_passed == official_raw_total,
            "almost_resolved": (
                official_raw_passed / official_raw_total >= 0.95
                if official_raw_total
                else False
            ),
        }
        if hidden_raw_marker:
            raw_summary["hidden_failure_details"] = [{"name": hidden_raw_marker}]
        payload["official_eval_summary"]["raw"] = raw_summary
        result_path.write_text(json.dumps(payload), encoding="utf-8")
    return result_path


def test_collect_generalization_gaps_finds_local_green_official_regression(tmp_path):
    module = load_module()
    runs = tmp_path / "runs"
    baselines = tmp_path / "baselines"
    task_id = "task.local-green"
    write_baseline(baselines / "task.baseline.json", task_id, 13, passed_tests=13)
    write_result(runs, task_id, official_score=0, official_passed=0)

    rows = module.collect_generalization_gaps(
        runs_root=runs,
        official_eval_root=tmp_path / "official",
        baseline_root=baselines,
        required_runtime_smoke_dimensions=("args", "input_files", "stdin"),
    )

    assert len(rows) == 1
    row = rows[0]
    assert row.task_id == task_id
    assert row.gap_kind == "official_regressed"
    assert row.official_score_delta == -13
    assert row.official_passed_delta == -13


def test_json_cli_is_aggregate_only_and_hides_baseline_notes(tmp_path):
    runs = tmp_path / "runs"
    baselines = tmp_path / "baselines"
    task_id = "task.secret"
    write_baseline(
        baselines / "task.baseline.json",
        task_id,
        8,
        passed_tests=8,
        hidden_marker="do-not-leak-this-marker",
    )
    write_result(runs, task_id, official_score=8, official_passed=8)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/audit_official_generalization_gaps.py",
            "--runs",
            str(runs),
            "--official-eval-root",
            str(tmp_path / "official"),
            "--baseline-root",
            str(baselines),
            "--require-runtime-smoke-dimensions",
            "args,input_files,stdin",
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "do-not-leak-this-marker" not in result.stdout
    payload = json.loads(result.stdout)
    assert payload["row_count"] == 1
    row = payload["rows"][0]
    assert row["gap_kind"] == "official_equal_baseline"
    assert row["blocker"] == "official_not_above_baseline"
    assert row["official_eval_allowed"] is False
    assert row["repeat_official_eval_recommended"] is False
    assert row["evidence_boundary"] == "aggregate_official_not_above_baseline"
    assert row["local_holdout_gap"] == pytest.approx(0.0)
    assert row["local_official_pass_rate_gap"] == pytest.approx(0.92)
    assert row["holdout_official_pass_rate_gap"] == pytest.approx(0.92)


def test_json_cli_can_filter_specific_task(tmp_path):
    runs = tmp_path / "runs"
    baselines = tmp_path / "baselines"
    write_baseline(baselines / "one.baseline.json", "task.one", 8, passed_tests=8)
    write_baseline(baselines / "two.baseline.json", "task.two", 9, passed_tests=9)
    write_result(runs, "task.one", official_score=8, official_passed=8)
    write_result(runs, "task.two", official_score=9, official_passed=9)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/audit_official_generalization_gaps.py",
            "--runs",
            str(runs),
            "--official-eval-root",
            str(tmp_path / "official"),
            "--baseline-root",
            str(baselines),
            "--task",
            "task.two",
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["row_count"] == 1
    assert payload["rows"][0]["task_id"] == "task.two"


def test_json_cli_can_emit_safe_task_scoped_recheck_command(tmp_path):
    runs = tmp_path / "runs"
    baselines = tmp_path / "baselines"
    task_id = "task.secret"
    write_baseline(baselines / "task.baseline.json", task_id, 8, passed_tests=8)
    write_result(runs, task_id, official_score=8, official_passed=8)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/audit_official_generalization_gaps.py",
            "--runs",
            str(runs),
            "--official-eval-root",
            str(tmp_path / "official"),
            "--baseline-root",
            str(baselines),
            "--task",
            task_id,
            "--require-runtime-smoke-dimensions",
            "args,input_files,stdin",
            "--latest-per-task",
            "--include-next-command",
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    command = payload["rows"][0]["next_command"]
    assert command.startswith("python scripts/audit_official_generalization_gaps.py")
    assert f"--task {task_id}" in command
    command_parts = command.split()
    dimensions = command_parts[
        command_parts.index("--require-runtime-smoke-dimensions") + 1
    ].split(",")
    assert set(dimensions) == {"args", "input_files", "stdin"}
    assert "--latest-per-task" in command
    assert "--format json" in command
    assert "--official-eval" not in command.split()


def test_json_cli_can_filter_large_local_holdout_gap(tmp_path):
    runs = tmp_path / "runs"
    baselines = tmp_path / "baselines"
    task_id = "task.overfit"
    write_baseline(baselines / "task.baseline.json", task_id, 8, passed_tests=8)
    write_result(
        runs,
        task_id,
        local_rate=1.0,
        holdout_rate=0.85,
        official_score=8,
        official_passed=8,
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/audit_official_generalization_gaps.py",
            "--runs",
            str(runs),
            "--official-eval-root",
            str(tmp_path / "official"),
            "--baseline-root",
            str(baselines),
            "--max-local-holdout-gap",
            "0.1",
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["row_count"] == 0
    assert payload["total_row_count"] == 0


def test_cli_fail_on_gap_exits_nonzero_but_preserves_json(tmp_path):
    runs = tmp_path / "runs"
    baselines = tmp_path / "baselines"
    task_id = "task.blocker"
    write_baseline(baselines / "task.baseline.json", task_id, 8, passed_tests=8)
    write_result(runs, task_id, official_score=8, official_passed=8)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/audit_official_generalization_gaps.py",
            "--runs",
            str(runs),
            "--official-eval-root",
            str(tmp_path / "official"),
            "--baseline-root",
            str(baselines),
            "--fail-on-gap",
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["row_count"] == 1
    assert payload["rows"][0]["blocker"] == "official_not_above_baseline"


def test_json_cli_outputs_counted_total_tests_and_raw_aggregate_only(tmp_path):
    runs = tmp_path / "runs"
    baselines = tmp_path / "baselines"
    official_dir = tmp_path / "official" / "submission" / "task.raw"
    task_id = "task.raw"
    write_eval_json(
        official_dir / f"{task_id}.eval.json",
        ["passed", "passed", "failed", "failed"],
    )
    write_baseline(
        baselines / "task.baseline.json",
        task_id,
        8,
        passed_tests=8,
        submission_path=official_dir / "submission.tar.gz",
        hidden_marker="do-not-leak-baseline-hidden",
    )
    write_result(
        runs,
        task_id,
        official_score=8,
        official_passed=8,
        official_raw_passed=6,
        official_raw_total=10,
        hidden_raw_marker="do-not-leak-candidate-hidden",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/audit_official_generalization_gaps.py",
            "--runs",
            str(runs),
            "--official-eval-root",
            str(tmp_path / "official"),
            "--baseline-root",
            str(baselines),
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "do-not-leak-baseline-hidden" not in result.stdout
    assert "do-not-leak-candidate-hidden" not in result.stdout
    payload = json.loads(result.stdout)
    row = payload["rows"][0]
    assert row["candidate_official"]["total_tests"] == 100
    assert row["recorded_baseline"]["total_tests"] == 100
    assert row["candidate_official_raw"] == {
        "score": 60,
        "passed_tests": 6,
        "total_tests": 10,
        "pass_rate": 0.6,
        "fully_resolved": False,
        "almost_resolved": False,
    }
    assert row["recorded_baseline_raw"] == {
        "score": 50,
        "passed_tests": 2,
        "total_tests": 4,
        "pass_rate": 0.5,
        "fully_resolved": False,
        "almost_resolved": False,
    }
    assert row["official_raw_score_delta"] == 10
    assert row["official_raw_passed_delta"] == 4


def test_json_cli_can_rank_local_green_official_collapse_first(tmp_path):
    runs = tmp_path / "runs"
    baselines = tmp_path / "baselines"
    write_baseline(
        baselines / "collapse.baseline.json",
        "task.collapse",
        3,
        passed_tests=3,
    )
    write_baseline(
        baselines / "regress.baseline.json",
        "task.regress",
        86,
        passed_tests=86,
    )
    write_result(
        runs,
        "task.collapse",
        local_rate=1.0,
        holdout_rate=1.0,
        holdout_cases=31,
        official_score=0,
        official_passed=0,
    )
    write_result(
        runs,
        "task.regress",
        local_rate=0.88,
        holdout_rate=0.86,
        holdout_cases=14,
        official_score=80,
        official_passed=80,
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/audit_official_generalization_gaps.py",
            "--runs",
            str(runs),
            "--official-eval-root",
            str(tmp_path / "official"),
            "--baseline-root",
            str(baselines),
            "--sort-by",
            "diagnostic-priority",
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["rows"][0]["task_id"] == "task.collapse"
    assert payload["rows"][0]["generalization_failure_mode"] == (
        "official_collapse_after_local_green"
    )
    assert payload["rows"][0]["diagnostic_priority"] > payload["rows"][1][
        "diagnostic_priority"
    ]


def test_json_cli_reports_probe_domain_sprawl_without_case_details(tmp_path):
    runs = tmp_path / "runs"
    baselines = tmp_path / "baselines"
    task_id = "task.domain-sprawl"
    write_baseline(baselines / "task.baseline.json", task_id, 3, passed_tests=3)
    write_result(
        runs,
        task_id,
        official_score=0,
        official_passed=0,
        probe_axis_coverage={
            "smoke_contract_axis_count": 6,
            "adaptive_axis_count": 6,
            "smoke_contract_domains": [
                "csv_table",
                "filesystem_tool",
                "html_selector",
                "json_transform",
            ],
            "adaptive_domains": [
                "csv_table",
                "filesystem_tool",
                "html_selector",
                "json_transform",
            ],
        },
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/audit_official_generalization_gaps.py",
            "--runs",
            str(runs),
            "--official-eval-root",
            str(tmp_path / "official"),
            "--baseline-root",
            str(baselines),
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    row = payload["rows"][0]
    assert row["probe_domains"] == [
        "csv_table",
        "filesystem_tool",
        "html_selector",
        "json_transform",
    ]
    assert row["probe_domain_count"] == 4
    assert row["probe_domain_sprawl"] is True
    assert row["probe_domain_warning"] == "probe_domain_sprawl"
