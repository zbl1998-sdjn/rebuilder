import io
import json
import math
import os
import subprocess
import sys
from contextlib import redirect_stdout

import pytest

from scripts.rank_programbench_candidates import (
    collect_candidates,
    discover_baseline_task_ids,
    format_rate,
    local_holdout_gap,
    official_gate_blockers,
    official_gate_reason,
    write_markdown,
)


def write_result(
    path,
    task_id,
    resolved,
    holdout,
    *,
    status="failed",
    holdout_cases=10,
    probe_axis_coverage=None,
    runtime_smoke=None,
    official_eval_summary=None,
    secret_marker=None,
):
    target = path / task_id / "generated" / task_id
    target.mkdir(parents=True)
    metadata = {"static_output_assets_enabled": False}
    if probe_axis_coverage is not None:
        metadata["probe_axis_coverage"] = probe_axis_coverage
    if runtime_smoke is not None:
        metadata["runtime_smoke"] = runtime_smoke
    payload = {
        "task_id": task_id,
        "status": status,
        "resolved_rate": resolved,
        "holdout_resolved_rate": holdout,
        "holdout_cases": holdout_cases,
        "probes_conducted": 10,
        "iterations_used": 1,
        "implementation_metadata": metadata,
    }
    if secret_marker:
        payload["holdout_failures"] = [{"name": secret_marker, "expected": "secret"}]
        payload["official_eval"] = {"test_results": [{"name": secret_marker}]}
    if official_eval_summary is not None:
        payload["official_eval_summary"] = official_eval_summary
    (target / "result.json").write_text(json.dumps(payload), encoding="utf-8")
    return target / "result.json"


def write_baseline(path, task_id, *, score, passed_tests=1, total_tests=10):
    path.mkdir(parents=True, exist_ok=True)
    (path / f"{task_id}.baseline.json").write_text(
        json.dumps(
            {
                "instance_id": task_id,
                "official": {
                    "score": score,
                    "passed_tests": passed_tests,
                    "total_tests": total_tests,
                    "pass_rate": passed_tests / total_tests,
                    "fully_resolved": False,
                    "almost_resolved": False,
                },
            }
        ),
        encoding="utf-8",
    )


def write_official_eval_failure_report(runs, run_name, task_id, *, reason):
    report_path = (
        runs
        / f"{run_name}_submission"
        / f"{run_name}_eval"
        / "official_eval_failure_report.json"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "instance_id": task_id,
                "reason": reason,
                "timeout_seconds": 12.5,
                "artifacts": {"eval_json": {"exists": False}},
            }
        ),
        encoding="utf-8",
    )
    return report_path


def official_summary(score, *, passed_tests=2, total_tests=10):
    return {
        "counted": {
            "score": score,
            "passed_tests": passed_tests,
            "total_tests": total_tests,
            "pass_rate": passed_tests / total_tests,
            "fully_resolved": False,
            "almost_resolved": False,
        }
    }


def test_collect_candidates_prioritizes_unofficial_high_holdout(tmp_path):
    runs = tmp_path / "runs"
    official = tmp_path / "official"
    write_result(runs / "run_a", "task.a", 0.9, 0.5)
    write_result(runs / "run_b", "task.b", 0.8, 1.0)
    write_result(runs / "run_c", "task.c", 1.0, 1.0)
    eval_dir = official / "submission" / "task.c"
    eval_dir.mkdir(parents=True)
    (eval_dir / "task.c.eval.json").write_text("{}", encoding="utf-8")

    rows = collect_candidates(runs, official)

    assert [row.task_id for row in rows] == ["task.b", "task.a", "task.c"]
    assert rows[0].holdout_resolved_rate == 1.0
    assert rows[-1].has_official_eval


def test_collect_candidates_prioritizes_reliable_holdout_case_count(tmp_path):
    runs = tmp_path / "runs"
    official = tmp_path / "official"
    write_result(runs / "run_a", "task.a", 0.9, 0.95, holdout_cases=4)
    write_result(runs / "run_b", "task.b", 0.7, 0.6, holdout_cases=12)

    rows = collect_candidates(runs, official, min_holdout_cases=10)

    assert [row.task_id for row in rows] == ["task.b", "task.a"]
    assert rows[0].holdout_cases == 12


def test_collect_candidates_uses_task_id_tie_breaker(tmp_path):
    runs = tmp_path / "runs"
    official = tmp_path / "official"
    z_task = write_result(runs / "a_run", "task.z", 0.8, 0.8, holdout_cases=12)
    a_task = write_result(runs / "z_run", "task.a", 0.8, 0.8, holdout_cases=12)
    os.utime(z_task, (1_700_000_000, 1_700_000_000))
    os.utime(a_task, (1_700_000_000, 1_700_000_000))

    rows = collect_candidates(runs, official)

    assert [row.task_id for row in rows] == ["task.a", "task.z"]


def test_collect_candidates_uses_result_path_tie_breaker_for_same_task(tmp_path):
    runs = tmp_path / "runs"
    official = tmp_path / "official"
    first = write_result(runs / "a_run", "task.tie", 0.8, 0.8, holdout_cases=12)
    selected = write_result(runs / "z_run", "task.tie", 0.8, 0.8, holdout_cases=12)
    os.utime(first, (1_700_000_000, 1_700_000_000))
    os.utime(selected, (1_700_000_000, 1_700_000_000))

    rows = collect_candidates(runs, official)
    latest_rows = collect_candidates(runs, official, latest_per_task=True)

    assert len(rows) == 1
    assert rows[0].result_path == selected
    assert len(latest_rows) == 1
    assert latest_rows[0].result_path == selected


def test_collect_candidates_prefers_reliable_run_for_same_task(tmp_path):
    runs = tmp_path / "runs"
    official = tmp_path / "official"
    write_result(runs / "run_low_sample", "task.a", 0.9, 0.95, holdout_cases=4)
    write_result(runs / "run_reliable", "task.a", 0.8, 0.7, holdout_cases=12)

    rows = collect_candidates(runs, official, min_holdout_cases=10)

    assert len(rows) == 1
    assert rows[0].holdout_cases == 12


def test_collect_candidates_can_prefer_latest_run_for_same_task(tmp_path):
    runs = tmp_path / "runs"
    official = tmp_path / "official"
    older = write_result(runs / "run_old", "task.a", 0.9, 0.95, holdout_cases=12)
    newer = write_result(runs / "run_new", "task.a", 0.7, 0.6, holdout_cases=12)
    os.utime(older, (1_700_000_000, 1_700_000_000))
    os.utime(newer, (1_700_000_100, 1_700_000_100))

    rows = collect_candidates(runs, official, latest_per_task=True)

    assert len(rows) == 1
    assert rows[0].result_path == newer
    assert rows[0].holdout_resolved_rate == 0.6


def test_collect_candidates_can_filter_official_tasks(tmp_path):
    runs = tmp_path / "runs"
    official = tmp_path / "official"
    write_result(runs / "run_a", "task.a", 0.9, 0.5)
    write_result(runs / "run_b", "task.b", 1.0, 1.0)
    eval_dir = official / "submission" / "task.b"
    eval_dir.mkdir(parents=True)
    (eval_dir / "task.b.eval.json").write_text("{}", encoding="utf-8")

    rows = collect_candidates(runs, official, only_unofficial=True)

    assert [row.task_id for row in rows] == ["task.a"]


def test_collect_candidates_can_filter_to_official_eligible_gate_passes(tmp_path):
    runs = tmp_path / "runs"
    official = tmp_path / "official"
    write_result(runs / "pass", "task.pass", 0.9, 0.85, holdout_cases=12)
    write_result(runs / "low_rate", "task.low_rate", 1.0, 0.75, holdout_cases=12)
    write_result(runs / "few_cases", "task.few_cases", 1.0, 1.0, holdout_cases=4)
    write_result(runs / "already_official", "task.official", 1.0, 1.0, holdout_cases=12)
    eval_dir = official / "submission" / "task.official"
    eval_dir.mkdir(parents=True)
    (eval_dir / "task.official.eval.json").write_text("{}", encoding="utf-8")

    rows = collect_candidates(
        runs,
        official,
        official_eligible_only=True,
        min_holdout_rate=0.8,
        min_holdout_cases=10,
    )

    assert [row.task_id for row in rows] == ["task.pass"]


def test_collect_candidates_requires_embedded_official_summary_for_existing_official_upgrade(tmp_path):
    runs = tmp_path / "runs"
    official = tmp_path / "official"
    write_result(runs / "new_candidate", "task.official", 0.9, 0.85, holdout_cases=12)
    eval_dir = official / "submission" / "task.official"
    eval_dir.mkdir(parents=True)
    (eval_dir / "task.official.eval.json").write_text("{}", encoding="utf-8")

    default_rows = collect_candidates(
        runs,
        official,
        official_eligible_only=True,
        min_holdout_rate=0.8,
        min_holdout_cases=10,
    )
    blocked_rows = collect_candidates(
        runs,
        official,
        official_eligible_only=True,
        allow_existing_official=True,
        min_holdout_rate=0.8,
        min_holdout_cases=10,
    )

    assert default_rows == []
    assert blocked_rows == []

    all_rows = collect_candidates(runs, official)
    assert (
        official_gate_reason(
            all_rows[0],
            allow_existing_official=True,
            min_holdout_rate=0.8,
            min_holdout_cases=10,
        )
        == "missing_official_candidate_summary"
    )


def test_collect_candidates_surfaces_official_eval_failure_report(tmp_path):
    runs = tmp_path / "runs"
    official = tmp_path / "official"
    task_id = "task.official-timeout"
    report_path = write_official_eval_failure_report(
        runs,
        "timed_out_candidate",
        task_id,
        reason="official_eval_failed_without_eval_json",
    )
    write_result(
        runs / "timed_out_candidate",
        task_id,
        1.0,
        1.0,
        holdout_cases=12,
    )

    [row] = collect_candidates(runs, official)

    assert row.has_official_eval is True
    assert row.official_eval_failure_reason == "official_eval_failed_without_eval_json"
    assert row.official_eval_failure_report_path == report_path
    assert (
        official_gate_reason(
            row,
            allow_existing_official=True,
            min_holdout_rate=0.8,
            min_holdout_cases=10,
        )
        == "official_eval_failed_without_eval_json"
    )
    assert official_gate_blockers(
        row,
        allow_existing_official=True,
        min_holdout_rate=0.8,
        min_holdout_cases=10,
    ) == ["official_eval_failed_without_eval_json"]


def test_collect_candidates_ignores_stale_official_eval_failure_report(tmp_path):
    runs = tmp_path / "runs"
    official = tmp_path / "official"
    task_id = "task.official-timeout"
    stale_report_path = official / "old_eval" / "official_eval_failure_report.json"
    stale_report_path.parent.mkdir(parents=True)
    stale_report_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "instance_id": task_id,
                "reason": "official_eval_failed_without_eval_json",
                "artifacts": {
                    "submission_root": {"path": str(official / "old_eval")}
                },
            }
        ),
        encoding="utf-8",
    )
    write_result(
        runs / "new_candidate",
        task_id,
        1.0,
        1.0,
        holdout_cases=12,
    )

    [row] = collect_candidates(runs, official)

    assert row.has_official_eval is False
    assert row.official_eval_failure_reason is None
    assert row.official_eval_failure_report_path is None


def test_collect_candidates_ignores_failure_report_when_official_summary_is_valid(tmp_path):
    runs = tmp_path / "runs"
    official = tmp_path / "official"
    task_id = "task.valid-after-timeout"
    write_official_eval_failure_report(
        runs,
        "recovered_candidate",
        task_id,
        reason="official_eval_failed_without_eval_json",
    )
    write_result(
        runs / "recovered_candidate",
        task_id,
        1.0,
        1.0,
        holdout_cases=12,
        official_eval_summary=official_summary(7, passed_tests=7, total_tests=20),
    )

    [row] = collect_candidates(runs, official)

    assert row.has_official_eval is True
    assert row.embedded_official_rank is not None
    assert row.official_eval_failure_reason is None
    assert row.official_eval_failure_report_path is None


def test_collect_candidates_routes_invalid_embedded_official_summary_as_failure(tmp_path):
    runs = tmp_path / "runs"
    official = tmp_path / "official"
    baselines = tmp_path / "baselines"
    task_id = "task.official-timeout"
    write_baseline(baselines, task_id, score=62, passed_tests=62, total_tests=100)
    write_result(
        runs / "new_candidate",
        task_id,
        1.0,
        1.0,
        holdout_cases=12,
        official_eval_summary={
            "counted": {
                "score": 0,
                "passed_tests": 0,
                "total_tests": 0,
                "pass_rate": 0.0,
                "fully_resolved": False,
                "almost_resolved": False,
                "error_code": "invalid_eval_payload",
            }
        },
    )

    [row] = collect_candidates(runs, official, baseline_root=baselines)

    assert row.has_official_eval is True
    assert row.embedded_official_rank is None
    assert row.official_eval_failure_reason == "official_eval_invalid_aggregate"
    assert row.official_eval_failure_report_path is None
    assert (
        official_gate_reason(
            row,
            allow_existing_official=True,
            min_holdout_rate=0.8,
            min_holdout_cases=10,
        )
        == "official_eval_invalid_aggregate"
    )


def test_collect_candidates_routes_results_read_error_summary_as_failure(tmp_path):
    runs = tmp_path / "runs"
    official = tmp_path / "official"
    task_id = "task.results-read"
    write_result(
        runs / "new_candidate",
        task_id,
        1.0,
        1.0,
        holdout_cases=12,
        official_eval_summary={
            "counted": {
                "score": 0,
                "passed_tests": 0,
                "total_tests": 100,
                "pass_rate": 0.0,
                "fully_resolved": False,
                "almost_resolved": False,
                "error_code": "results_read_failed",
            }
        },
    )

    [row] = collect_candidates(runs, official)

    assert row.has_official_eval is True
    assert row.embedded_official_rank is None
    assert row.official_eval_failure_reason == "official_eval_results_read_failed"
    assert row.official_eval_failure_report_path is None


def test_collect_candidates_can_include_existing_official_when_candidate_beats_baseline(tmp_path):
    runs = tmp_path / "runs"
    baselines = tmp_path / "baselines"
    write_baseline(baselines, "task.official", score=10, passed_tests=10, total_tests=100)
    write_result(
        runs / "new_candidate",
        "task.official",
        0.9,
        0.85,
        holdout_cases=12,
        official_eval_summary=official_summary(12, passed_tests=12, total_tests=100),
    )

    upgrade_rows = collect_candidates(
        runs,
        tmp_path / "official",
        baseline_root=baselines,
        official_eligible_only=True,
        allow_existing_official=True,
        min_holdout_rate=0.8,
        min_holdout_cases=10,
    )

    assert [row.task_id for row in upgrade_rows] == ["task.official"]
    assert (
        official_gate_reason(
            upgrade_rows[0],
            allow_existing_official=True,
            min_holdout_rate=0.8,
            min_holdout_cases=10,
        )
        == "eligible_baseline_upgrade"
    )


def test_collect_candidates_blocks_existing_official_when_candidate_does_not_beat_baseline(tmp_path):
    runs = tmp_path / "runs"
    baselines = tmp_path / "baselines"
    write_baseline(baselines, "task.official", score=12, passed_tests=12, total_tests=100)
    write_result(
        runs / "new_candidate",
        "task.official",
        0.9,
        0.85,
        holdout_cases=12,
        official_eval_summary=official_summary(10, passed_tests=10, total_tests=100),
    )

    upgrade_rows = collect_candidates(
        runs,
        tmp_path / "official",
        baseline_root=baselines,
        official_eligible_only=True,
        allow_existing_official=True,
        min_holdout_rate=0.8,
        min_holdout_cases=10,
    )
    [row] = collect_candidates(runs, tmp_path / "official", baseline_root=baselines)

    assert upgrade_rows == []
    assert (
        official_gate_reason(
            row,
            allow_existing_official=True,
            min_holdout_rate=0.8,
            min_holdout_cases=10,
        )
        == "official_not_above_baseline"
    )


@pytest.mark.parametrize(
    ("threshold_kwargs", "message"),
    [
        ({"min_holdout_rate": -0.1}, "min_holdout_rate must be a finite rate between 0 and 1"),
        ({"min_holdout_rate": math.nan}, "min_holdout_rate must be a finite rate between 0 and 1"),
        ({"min_holdout_rate": 1.2}, "min_holdout_rate must be a finite rate between 0 and 1"),
        ({"min_holdout_cases": -1}, "min_holdout_cases must be non-negative"),
        ({"min_holdout_cases": math.nan}, "min_holdout_cases must be"),
        ({"min_holdout_cases": 1.5}, "min_holdout_cases must be"),
        ({"min_smoke_contract_axes": -1}, "min_smoke_contract_axes must be non-negative"),
        ({"min_smoke_contract_axes": math.nan}, "min_smoke_contract_axes must be"),
        ({"min_smoke_contract_axes": 1.5}, "min_smoke_contract_axes must be"),
        ({"min_holdout_improvement_delta": -0.01}, "min_holdout_improvement_delta must be non-negative"),
        ({"min_holdout_improvement_delta": math.nan}, "min_holdout_improvement_delta must be non-negative"),
    ],
)
def test_collect_candidates_rejects_negative_gate_thresholds(tmp_path, threshold_kwargs, message):
    runs = tmp_path / "runs"
    official = tmp_path / "official"
    write_result(runs / "pass", "task.pass", 0.9, 0.85, holdout_cases=12)

    with pytest.raises(ValueError, match=message):
        collect_candidates(runs, official, **threshold_kwargs)


@pytest.mark.parametrize(
    ("threshold_kwargs", "message"),
    [
        ({"min_holdout_rate": -0.1}, "min_holdout_rate must be a finite rate between 0 and 1"),
        ({"min_holdout_rate": math.nan}, "min_holdout_rate must be a finite rate between 0 and 1"),
        ({"min_holdout_rate": 1.2}, "min_holdout_rate must be a finite rate between 0 and 1"),
        ({"min_holdout_cases": -1}, "min_holdout_cases must be non-negative"),
        ({"min_holdout_cases": math.nan}, "min_holdout_cases must be"),
        ({"min_holdout_cases": 1.5}, "min_holdout_cases must be"),
        ({"min_smoke_contract_axes": -1}, "min_smoke_contract_axes must be non-negative"),
        ({"min_smoke_contract_axes": math.nan}, "min_smoke_contract_axes must be"),
        ({"min_smoke_contract_axes": 1.5}, "min_smoke_contract_axes must be"),
        ({"min_holdout_improvement_delta": -0.01}, "min_holdout_improvement_delta must be non-negative"),
        ({"min_holdout_improvement_delta": math.nan}, "min_holdout_improvement_delta must be non-negative"),
        ({"max_local_holdout_gap": -0.01}, "max_local_holdout_gap must be"),
        ({"max_local_holdout_gap": math.nan}, "max_local_holdout_gap must be"),
    ],
)
def test_official_gate_reason_rejects_negative_gate_thresholds(tmp_path, threshold_kwargs, message):
    runs = tmp_path / "runs"
    official = tmp_path / "official"
    write_result(runs / "pass", "task.pass", 0.9, 0.85, holdout_cases=12)
    row = collect_candidates(runs, official)[0]

    with pytest.raises(ValueError, match=message):
        official_gate_reason(row, **threshold_kwargs)


@pytest.mark.parametrize(
    ("flag_and_value", "message"),
    [
        (("--min-holdout-rate", "-0.1"), "finite rate between 0 and 1"),
        (("--min-holdout-rate", "nan"), "finite rate between 0 and 1"),
        (("--min-holdout-rate", "1.2"), "finite rate between 0 and 1"),
        (("--min-holdout-cases", "-1"), "must be non-negative"),
        (("--min-smoke-contract-axes", "-1"), "must be non-negative"),
        (("--min-holdout-improvement-delta", "-0.01"), "must be non-negative"),
        (("--min-holdout-improvement-delta", "nan"), "must be non-negative"),
        (("--max-local-holdout-gap", "-0.01"), "finite rate between 0 and 1"),
        (("--max-local-holdout-gap", "nan"), "finite rate between 0 and 1"),
    ],
)
def test_rank_programbench_candidates_cli_rejects_negative_gate_thresholds(tmp_path, flag_and_value, message):
    flag, value = flag_and_value

    result = subprocess.run(
        [
            sys.executable,
            "scripts/rank_programbench_candidates.py",
            "--runs",
            str(tmp_path / "runs"),
            "--official-eval-root",
            str(tmp_path / "official"),
            flag,
            value,
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert message in result.stderr


@pytest.mark.parametrize("limit", ["0", "-1"])
def test_rank_programbench_candidates_cli_rejects_non_positive_limit(tmp_path, limit):
    result = subprocess.run(
        [
            sys.executable,
            "scripts/rank_programbench_candidates.py",
            "--runs",
            str(tmp_path / "runs"),
            "--official-eval-root",
            str(tmp_path / "official"),
            "--limit",
            limit,
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "must be positive" in result.stderr


def test_rank_programbench_candidates_cli_outputs_aggregate_only_json(tmp_path):
    runs = tmp_path / "runs"
    official = tmp_path / "official"
    result_path = write_result(
        runs / "pass",
        "task.pass",
        0.9,
        0.85,
        holdout_cases=12,
        probe_axis_coverage={
            "smoke_contract_axis_count": 2,
            "adaptive_axis_count": 3,
        },
        secret_marker="hidden-local-case",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/rank_programbench_candidates.py",
            "--runs",
            str(runs),
            "--official-eval-root",
            str(official),
            "--min-smoke-contract-axes",
            "1",
            "--limit",
            "5",
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "hidden-local-case" not in result.stdout
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == 1
    assert payload["row_count"] == 1
    assert payload["total_row_count"] == 1
    assert payload["limit"] == 5
    [row] = payload["rows"]
    assert row == {
        "rank": 1,
        "task_id": "task.pass",
        "local_resolved_rate": 0.9,
        "holdout_resolved_rate": 0.85,
        "local_holdout_gap": 0.050000000000000044,
        "holdout_cases": 12,
        "smoke_contract_axis_count": 2,
        "adaptive_axis_count": 3,
        "runtime_smoke_status": "missing",
        "runtime_smoke_case_count": 0,
        "runtime_smoke_contract_case_count": 0,
        "runtime_smoke_input_dimensions": [],
        "official_gate": "eligible",
        "official_gate_blockers": [],
        "status": "failed",
        "probes_conducted": 10,
        "iterations_used": 1,
        "static_output_assets_enabled": False,
        "has_official_eval": False,
        "official_eval_failure_reason": None,
        "official_eval_failure_report_path": None,
        "result_path": str(result_path),
    }


def test_collect_candidates_reads_probe_axis_coverage(tmp_path):
    runs = tmp_path / "runs"
    official = tmp_path / "official"
    write_result(
        runs / "run_a",
        "task.a",
        0.9,
        0.85,
        holdout_cases=12,
        probe_axis_coverage={
            "smoke_contract_axis_count": 3,
            "adaptive_axis_count": 4,
        },
    )

    rows = collect_candidates(runs, official)

    assert rows[0].smoke_contract_axis_count == 3
    assert rows[0].adaptive_axis_count == 4


def test_collect_candidates_treats_malformed_probe_metadata_as_empty(tmp_path):
    runs = tmp_path / "runs"
    official = tmp_path / "official"
    result_path = write_result(runs / "run_a", "task.a", 0.9, 0.85, holdout_cases=12)
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    payload["implementation_metadata"] = {"probe_axis_coverage": ["not", "a", "dict"]}
    result_path.write_text(json.dumps(payload), encoding="utf-8")

    rows = collect_candidates(runs, official)

    assert rows[0].smoke_contract_axis_count == 0
    assert rows[0].adaptive_axis_count == 0


def test_collect_candidates_treats_malformed_numeric_aggregate_fields_as_zero(tmp_path):
    runs = tmp_path / "runs"
    official = tmp_path / "official"
    result_path = write_result(runs / "run_a", "task.a", 0.9, 0.85, holdout_cases=12)
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    payload["holdout_cases"] = "not-an-int"
    payload["probes_conducted"] = ["not", "an", "int"]
    payload["iterations_used"] = {"not": "an-int"}
    result_path.write_text(json.dumps(payload), encoding="utf-8")

    rows = collect_candidates(runs, official)

    assert rows[0].holdout_cases == 0
    assert rows[0].probes_conducted == 0
    assert rows[0].iterations_used == 0
    assert official_gate_reason(rows[0], min_holdout_rate=0.8, min_holdout_cases=10) == "too_few_holdout_cases"


def test_collect_candidates_treats_negative_or_fractional_aggregate_counts_as_zero(tmp_path):
    runs = tmp_path / "runs"
    official = tmp_path / "official"
    result_path = write_result(
        runs / "run_a",
        "task.a",
        0.9,
        0.85,
        holdout_cases=12,
        probe_axis_coverage={
            "smoke_contract_axis_count": -1,
            "adaptive_axis_count": 1.5,
        },
    )
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    payload["holdout_cases"] = -12
    payload["probes_conducted"] = -3
    payload["iterations_used"] = 2.5
    result_path.write_text(json.dumps(payload), encoding="utf-8")

    rows = collect_candidates(runs, official)

    assert rows[0].holdout_cases == 0
    assert rows[0].probes_conducted == 0
    assert rows[0].iterations_used == 0
    assert rows[0].smoke_contract_axis_count == 0
    assert rows[0].adaptive_axis_count == 0
    assert official_gate_reason(rows[0], min_holdout_rate=0.8, min_holdout_cases=10) == "too_few_holdout_cases"


def test_collect_candidates_treats_non_finite_aggregate_rates_as_missing(tmp_path):
    runs = tmp_path / "runs"
    official = tmp_path / "official"
    result_path = write_result(runs / "run_a", "task.a", 0.9, 0.85, holdout_cases=12)
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    payload["resolved_rate"] = "nan"
    payload["holdout_resolved_rate"] = "inf"
    result_path.write_text(json.dumps(payload), encoding="utf-8")

    rows = collect_candidates(runs, official)

    assert rows[0].resolved_rate == 0.0
    assert rows[0].holdout_resolved_rate is None
    assert official_gate_reason(rows[0], min_holdout_rate=0.8, min_holdout_cases=10) == "missing_holdout"


def test_collect_candidates_treats_out_of_range_aggregate_rates_as_malformed(tmp_path):
    runs = tmp_path / "runs"
    official = tmp_path / "official"
    high_path = write_result(runs / "run_high", "task.high", 0.9, 0.85, holdout_cases=12)
    high_payload = json.loads(high_path.read_text(encoding="utf-8"))
    high_payload["resolved_rate"] = 1.5
    high_payload["holdout_resolved_rate"] = 1.2
    high_path.write_text(json.dumps(high_payload), encoding="utf-8")
    negative_path = write_result(runs / "run_negative", "task.negative", 0.9, 0.85, holdout_cases=12)
    negative_payload = json.loads(negative_path.read_text(encoding="utf-8"))
    negative_payload["resolved_rate"] = -0.1
    negative_payload["holdout_resolved_rate"] = -0.2
    negative_path.write_text(json.dumps(negative_payload), encoding="utf-8")

    rows = {row.task_id: row for row in collect_candidates(runs, official)}

    assert rows["task.high"].resolved_rate == 0.0
    assert rows["task.high"].holdout_resolved_rate is None
    assert official_gate_reason(rows["task.high"], min_holdout_rate=0.8, min_holdout_cases=10) == "missing_holdout"
    assert rows["task.negative"].resolved_rate == 0.0
    assert rows["task.negative"].holdout_resolved_rate is None
    assert official_gate_reason(rows["task.negative"], min_holdout_rate=0.8, min_holdout_cases=10) == "missing_holdout"


def test_collect_candidates_ignores_non_object_result_payloads(tmp_path):
    runs = tmp_path / "runs"
    official = tmp_path / "official"
    malformed = runs / "malformed" / "task.bad" / "generated" / "task.bad"
    malformed.mkdir(parents=True)
    (malformed / "result.json").write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")
    write_result(runs / "valid", "task.valid", 0.9, 0.85, holdout_cases=12)

    rows = collect_candidates(runs, official)

    assert [row.task_id for row in rows] == ["task.valid"]


def test_collect_candidates_can_filter_to_smoke_axis_gate_passes(tmp_path):
    runs = tmp_path / "runs"
    official = tmp_path / "official"
    write_result(
        runs / "pass",
        "task.pass",
        0.9,
        0.85,
        holdout_cases=12,
        probe_axis_coverage={"smoke_contract_axis_count": 3},
    )
    write_result(
        runs / "low_smoke",
        "task.low_smoke",
        0.9,
        0.85,
        holdout_cases=12,
        probe_axis_coverage={"smoke_contract_axis_count": 1},
    )
    write_result(runs / "missing_smoke", "task.missing_smoke", 0.9, 0.85, holdout_cases=12)

    rows = collect_candidates(
        runs,
        official,
        official_eligible_only=True,
        min_holdout_rate=0.8,
        min_holdout_cases=10,
        min_smoke_contract_axes=2,
    )

    assert [row.task_id for row in rows] == ["task.pass"]
    all_rows = {row.task_id: row for row in collect_candidates(runs, official)}
    assert (
        official_gate_reason(
            all_rows["task.low_smoke"],
            min_holdout_rate=0.8,
            min_holdout_cases=10,
            min_smoke_contract_axes=2,
        )
        == "insufficient_smoke_contract_axes"
    )
    assert (
        official_gate_reason(
            all_rows["task.missing_smoke"],
            min_holdout_rate=0.8,
            min_holdout_cases=10,
            min_smoke_contract_axes=2,
        )
        == "insufficient_smoke_contract_axes"
    )


def test_collect_candidates_can_filter_to_runtime_smoke_dimension_gate_passes(tmp_path):
    runs = tmp_path / "runs"
    official = tmp_path / "official"
    write_result(
        runs / "pass",
        "task.pass",
        0.9,
        0.85,
        holdout_cases=12,
        runtime_smoke={
            "status": "passed",
            "case_count": 3,
            "contract_case_count": 1,
            "input_dimensions": ["args", "input_files", "env_vars"],
        },
    )
    write_result(
        runs / "missing_dimension",
        "task.missing_dimension",
        0.9,
        0.85,
        holdout_cases=12,
        runtime_smoke={
            "status": "passed",
            "case_count": 3,
            "contract_case_count": 1,
            "input_dimensions": ["args"],
        },
    )
    write_result(
        runs / "failed_smoke",
        "task.failed_smoke",
        0.9,
        0.85,
        holdout_cases=12,
        runtime_smoke={
            "status": "failed",
            "case_count": 3,
            "contract_case_count": 1,
            "input_dimensions": ["args", "input_files", "env_vars"],
        },
    )

    rows = collect_candidates(
        runs,
        official,
        official_eligible_only=True,
        min_holdout_rate=0.8,
        min_holdout_cases=10,
        required_runtime_smoke_dimensions=("args", "input_files", "env_vars"),
    )

    assert [row.task_id for row in rows] == ["task.pass"]
    all_rows = {row.task_id: row for row in collect_candidates(runs, official)}
    assert (
        official_gate_reason(
            all_rows["task.missing_dimension"],
            min_holdout_rate=0.8,
            min_holdout_cases=10,
            required_runtime_smoke_dimensions=("args", "input_files", "env_vars"),
        )
        == "insufficient_runtime_smoke_dimensions"
    )
    assert (
        official_gate_reason(
            all_rows["task.failed_smoke"],
            min_holdout_rate=0.8,
            min_holdout_cases=10,
            required_runtime_smoke_dimensions=("args", "input_files", "env_vars"),
        )
        == "runtime_smoke_not_passed"
    )


def test_official_gate_blockers_report_multiple_aggregate_reasons(tmp_path):
    runs = tmp_path / "runs"
    official = tmp_path / "official"
    write_result(
        runs / "candidate",
        "task.blocked",
        0.9,
        0.5,
        holdout_cases=5,
        probe_axis_coverage={"smoke_contract_axis_count": 0},
    )

    [row] = collect_candidates(runs, official)

    assert official_gate_blockers(
        row,
        min_holdout_rate=0.8,
        min_holdout_cases=10,
        min_smoke_contract_axes=1,
        required_runtime_smoke_dimensions=("args", "input_files"),
    ) == [
        "too_few_holdout_cases",
        "low_holdout_rate",
        "insufficient_smoke_contract_axes",
        "runtime_smoke_not_passed",
    ]
    assert (
        official_gate_reason(
            row,
            min_holdout_rate=0.8,
            min_holdout_cases=10,
            min_smoke_contract_axes=1,
            required_runtime_smoke_dimensions=("args", "input_files"),
        )
        == "too_few_holdout_cases"
    )


def test_official_gate_blocks_gate_ready_local_holdout_gap(tmp_path):
    runs = tmp_path / "runs"
    official = tmp_path / "official"
    write_result(runs / "overfit", "task.overfit", 1.0, 0.82, holdout_cases=12)

    [row] = collect_candidates(runs, official)

    assert local_holdout_gap(row) == pytest.approx(0.18)
    assert official_gate_blockers(
        row,
        min_holdout_rate=0.8,
        min_holdout_cases=10,
        max_local_holdout_gap=0.1,
    ) == ["local_holdout_gap_too_high"]
    assert (
        official_gate_reason(
            row,
            min_holdout_rate=0.8,
            min_holdout_cases=10,
            max_local_holdout_gap=0.1,
        )
        == "local_holdout_gap_too_high"
    )


def test_official_gate_does_not_duplicate_low_holdout_with_gap_blocker(tmp_path):
    runs = tmp_path / "runs"
    official = tmp_path / "official"
    write_result(runs / "low", "task.low", 1.0, 0.57, holdout_cases=14)

    [row] = collect_candidates(runs, official)

    assert official_gate_blockers(
        row,
        min_holdout_rate=0.8,
        min_holdout_cases=10,
        max_local_holdout_gap=0.1,
    ) == ["low_holdout_rate"]


def test_collect_candidates_can_filter_to_holdout_improvement_gate_passes(tmp_path):
    runs = tmp_path / "runs"
    official = tmp_path / "official"
    old_pass = write_result(runs / "old_pass", "task.pass", 0.8, 0.8, holdout_cases=12)
    new_pass = write_result(runs / "new_pass", "task.pass", 0.9, 0.85, holdout_cases=12)
    old_regress = write_result(runs / "old_regress", "task.regress", 0.8, 0.8, holdout_cases=12)
    new_regress = write_result(runs / "new_regress", "task.regress", 0.9, 0.75, holdout_cases=12)
    old_delta = write_result(runs / "old_delta", "task.delta", 0.8, 0.80, holdout_cases=12)
    new_delta = write_result(runs / "new_delta", "task.delta", 0.9, 0.81, holdout_cases=12)
    os.utime(old_pass, (1_700_000_000, 1_700_000_000))
    os.utime(new_pass, (1_700_000_100, 1_700_000_100))
    os.utime(old_regress, (1_700_000_000, 1_700_000_000))
    os.utime(new_regress, (1_700_000_100, 1_700_000_100))
    os.utime(old_delta, (1_700_000_000, 1_700_000_000))
    os.utime(new_delta, (1_700_000_100, 1_700_000_100))

    rows = collect_candidates(
        runs,
        official,
        official_eligible_only=True,
        latest_per_task=True,
        min_holdout_rate=0.7,
        min_holdout_cases=10,
        require_holdout_improvement=True,
        holdout_history_root=runs,
        min_holdout_improvement_delta=0.02,
    )

    assert [row.task_id for row in rows] == ["task.pass"]
    all_rows = {row.task_id: row for row in collect_candidates(runs, official, latest_per_task=True)}
    assert (
        official_gate_reason(
            all_rows["task.regress"],
            min_holdout_rate=0.7,
            min_holdout_cases=10,
            require_holdout_improvement=True,
            holdout_history_root=runs,
            min_holdout_improvement_delta=0.02,
        )
        == "holdout_not_improved"
    )
    assert (
        official_gate_reason(
            all_rows["task.delta"],
            min_holdout_rate=0.7,
            min_holdout_cases=10,
            require_holdout_improvement=True,
            holdout_history_root=runs,
            min_holdout_improvement_delta=0.02,
        )
        == "holdout_delta_below_min"
    )


def test_official_eligible_latest_per_task_ignores_stale_passing_run(tmp_path):
    runs = tmp_path / "runs"
    official = tmp_path / "official"
    older = write_result(runs / "old_pass", "task.pingu", 0.9, 0.9, holdout_cases=12)
    newer = write_result(runs / "new_fail", "task.pingu", 0.7, 0.4, holdout_cases=12)
    os.utime(older, (1_700_000_000, 1_700_000_000))
    os.utime(newer, (1_700_000_100, 1_700_000_100))

    rows = collect_candidates(
        runs,
        official,
        official_eligible_only=True,
        latest_per_task=True,
        min_holdout_rate=0.8,
        min_holdout_cases=10,
    )

    assert rows == []


def test_official_gate_reason_explains_aggregate_blockers(tmp_path):
    runs = tmp_path / "runs"
    official = tmp_path / "official"
    write_result(runs / "pass", "task.pass", 0.9, 0.85, holdout_cases=12)
    write_result(runs / "missing", "task.missing", 0.9, None, holdout_cases=12)
    write_result(runs / "few_cases", "task.few_cases", 0.9, 1.0, holdout_cases=4)
    write_result(runs / "low_rate", "task.low_rate", 0.9, 0.75, holdout_cases=12)
    write_result(runs / "official_run", "task.official", 0.9, 1.0, holdout_cases=12)
    eval_dir = official / "submission" / "task.official"
    eval_dir.mkdir(parents=True)
    (eval_dir / "task.official.eval.json").write_text("{}", encoding="utf-8")
    rows = {row.task_id: row for row in collect_candidates(runs, official)}

    assert official_gate_reason(rows["task.pass"], min_holdout_rate=0.8, min_holdout_cases=10) == "eligible"
    assert official_gate_reason(rows["task.missing"], min_holdout_rate=0.8, min_holdout_cases=10) == "missing_holdout"
    assert (
        official_gate_reason(rows["task.few_cases"], min_holdout_rate=0.8, min_holdout_cases=10)
        == "too_few_holdout_cases"
    )
    assert official_gate_reason(rows["task.low_rate"], min_holdout_rate=0.8, min_holdout_cases=10) == "low_holdout_rate"
    assert official_gate_reason(rows["task.official"], min_holdout_rate=0.8, min_holdout_cases=10) == "already_official"
    assert (
        official_gate_reason(
            rows["task.official"],
            allow_existing_official=True,
            min_holdout_rate=0.8,
            min_holdout_cases=10,
        )
        == "missing_official_candidate_summary"
    )


def test_write_markdown_includes_official_gate_reason(tmp_path):
    runs = tmp_path / "runs"
    official = tmp_path / "official"
    write_result(
        runs / "run_a",
        "task.a",
        0.9,
        0.75,
        holdout_cases=12,
        probe_axis_coverage={
            "smoke_contract_axis_count": 2,
            "adaptive_axis_count": 3,
        },
    )
    rows = collect_candidates(runs, official)

    output = io.StringIO()
    with redirect_stdout(output):
        write_markdown(rows, limit=5, min_holdout_rate=0.8, min_holdout_cases=10)

    rendered = output.getvalue()
    assert "official gate" in rendered
    assert "low_holdout_rate" in rendered
    assert "smoke axes" in rendered
    assert "| 2 | 3 |" in rendered


def test_collect_candidates_treats_recorded_baseline_as_official(tmp_path):
    runs = tmp_path / "runs"
    baselines = tmp_path / "baselines"
    write_result(runs / "run_a", "task.a", 0.9, 0.5)
    write_result(runs / "run_b", "task.b", 1.0, 1.0)
    baselines.mkdir()
    (baselines / "task.b.baseline.json").write_text(
        json.dumps({"instance_id": "task.b"}),
        encoding="utf-8",
    )

    rows = collect_candidates(runs, tmp_path / "official", baseline_root=baselines)

    assert [row.task_id for row in rows] == ["task.a", "task.b"]
    assert rows[-1].has_official_eval


def test_discover_baseline_task_ids_ignores_invalid_json(tmp_path):
    (tmp_path / "bad.baseline.json").write_text("{", encoding="utf-8")
    (tmp_path / "good.baseline.json").write_text(
        json.dumps({"instance_id": "task.good"}),
        encoding="utf-8",
    )

    assert discover_baseline_task_ids(tmp_path) == {"task.good"}


def test_discover_baseline_task_ids_ignores_non_object_payload(tmp_path):
    (tmp_path / "bad.baseline.json").write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")
    (tmp_path / "good.baseline.json").write_text(
        json.dumps({"instance_id": "task.good"}),
        encoding="utf-8",
    )

    assert discover_baseline_task_ids(tmp_path) == {"task.good"}


def test_format_rate_handles_missing_holdout():
    assert format_rate(None) == "-"
