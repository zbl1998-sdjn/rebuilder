import json
import math
import os
import subprocess
import sys

import pytest

from scripts.summarize_holdout_trends import (
    build_guarded_rerun_command,
    collect_holdout_trends,
    read_holdout_run,
    recommend_weak_reruns,
)


def write_result(
    path,
    task_id,
    holdout_rate,
    holdout_cases,
    *,
    resolved_rate=0.5,
    timestamp=1_700_000_000,
    secret_marker=None,
):
    target = path / task_id / "generated" / task_id
    target.mkdir(parents=True)
    result_path = target / "result.json"
    payload = {
        "task_id": task_id,
        "status": "failed",
        "resolved_rate": resolved_rate,
        "holdout_resolved_rate": holdout_rate,
        "holdout_cases": holdout_cases,
        "probes_conducted": 50,
        "iterations_used": 3,
    }
    if secret_marker:
        payload["holdout_failures"] = [{"name": secret_marker, "expected": "secret"}]
        payload["official_eval"] = {"test_results": [{"name": secret_marker}]}
    result_path.write_text(json.dumps(payload), encoding="utf-8")
    os.utime(result_path, (timestamp, timestamp))
    return result_path


def test_collect_holdout_trends_reports_best_and_latest_per_task(tmp_path):
    runs = tmp_path / "runs"
    best = write_result(runs / "old", "task.pingu", 7 / 12, 12, timestamp=1_700_000_000)
    latest = write_result(runs / "new", "task.pingu", 4 / 10, 10, timestamp=1_700_000_100)

    rows = collect_holdout_trends(runs)

    assert len(rows) == 1
    row = rows[0]
    assert row.task_id == "task.pingu"
    assert row.best_result_path == best
    assert row.latest_result_path == latest
    assert row.best_holdout_resolved_rate == 7 / 12
    assert row.latest_holdout_resolved_rate == 4 / 10
    assert row.delta_from_best == (4 / 10) - (7 / 12)


def test_collect_holdout_trends_filters_missing_holdout(tmp_path):
    runs = tmp_path / "runs"
    write_result(runs / "missing", "task.no_holdout", None, 0)
    write_result(runs / "valid", "task.valid", 0.8, 10)

    rows = collect_holdout_trends(runs)

    assert [row.task_id for row in rows] == ["task.valid"]


def test_collect_holdout_trends_filters_malformed_holdout_case_count(tmp_path):
    runs = tmp_path / "runs"
    write_result(runs / "malformed", "task.bad_cases", 0.8, "not-an-int")
    write_result(runs / "valid", "task.valid", 0.8, 10)

    rows = collect_holdout_trends(runs)

    assert [row.task_id for row in rows] == ["task.valid"]


def test_collect_holdout_trends_filters_negative_or_fractional_holdout_case_count(tmp_path):
    runs = tmp_path / "runs"
    write_result(runs / "negative", "task.negative_cases", 0.8, -10)
    write_result(runs / "fractional", "task.fractional_cases", 0.8, 10.5)
    write_result(runs / "valid", "task.valid", 0.8, 10)

    rows = collect_holdout_trends(runs)

    assert [row.task_id for row in rows] == ["task.valid"]


def test_collect_holdout_trends_filters_non_finite_holdout_rates(tmp_path):
    runs = tmp_path / "runs"
    write_result(runs / "nan", "task.nan", "nan", 10)
    write_result(runs / "inf", "task.inf", "inf", 10)
    write_result(runs / "valid", "task.valid", 0.8, 10)

    rows = collect_holdout_trends(runs)

    assert [row.task_id for row in rows] == ["task.valid"]


def test_collect_holdout_trends_filters_out_of_range_holdout_rates(tmp_path):
    runs = tmp_path / "runs"
    write_result(runs / "high", "task.high", 1.2, 10)
    write_result(runs / "negative", "task.negative", -0.1, 10)
    write_result(runs / "valid", "task.valid", 0.8, 10)

    rows = collect_holdout_trends(runs)

    assert [row.task_id for row in rows] == ["task.valid"]


def test_collect_holdout_trends_treats_out_of_range_plain_rates_as_zero(tmp_path):
    runs = tmp_path / "runs"
    high = write_result(runs / "high", "task.high", 0.8, 10, resolved_rate=1.2)
    negative = write_result(runs / "negative", "task.negative", 0.8, 10, resolved_rate=-0.1)

    high_run = read_holdout_run(high)
    negative_run = read_holdout_run(negative)

    assert high_run is not None
    assert high_run.resolved_rate == 0.0
    assert negative_run is not None
    assert negative_run.resolved_rate == 0.0


def test_collect_holdout_trends_ignores_non_object_result_payloads(tmp_path):
    runs = tmp_path / "runs"
    malformed = runs / "malformed" / "task.bad" / "generated" / "task.bad"
    malformed.mkdir(parents=True)
    (malformed / "result.json").write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")
    write_result(runs / "valid", "task.valid", 0.8, 10)

    rows = collect_holdout_trends(runs)

    assert [row.task_id for row in rows] == ["task.valid"]


def test_collect_holdout_trends_uses_task_id_tie_breaker(tmp_path):
    runs = tmp_path / "runs"
    write_result(runs / "a_run", "task.z", 0.5, 10)
    write_result(runs / "z_run", "task.a", 0.5, 10)

    rows = collect_holdout_trends(runs)

    assert [row.task_id for row in rows] == ["task.a", "task.z"]


def test_collect_holdout_trends_can_filter_specific_tasks(tmp_path):
    runs = tmp_path / "runs"
    write_result(runs / "keep", "task.keep", 0.8, 10)
    write_result(runs / "also_keep", "task.also_keep", 0.7, 10)
    write_result(runs / "drop", "task.drop", 1.0, 10)

    rows = collect_holdout_trends(runs, task_ids=("task.keep", "task.also_keep"))

    assert [row.task_id for row in rows] == ["task.keep", "task.also_keep"]


def test_collect_holdout_trends_uses_result_path_tie_breaker_within_task(tmp_path):
    runs = tmp_path / "runs"
    first = write_result(runs / "a_run", "task.tie", 0.5, 10, timestamp=1_700_000_000)
    second = write_result(runs / "z_run", "task.tie", 0.5, 10, timestamp=1_700_000_000)

    rows = collect_holdout_trends(runs)

    assert len(rows) == 1
    assert rows[0].best_result_path == second
    assert rows[0].latest_result_path == second
    assert rows[0].best_result_path != first


def test_collect_holdout_trends_ignores_low_sample_best_by_default(tmp_path):
    runs = tmp_path / "runs"
    write_result(runs / "low_sample", "task.pingu", 0.6, 5, timestamp=1_700_000_000)
    reliable_best = write_result(runs / "reliable", "task.pingu", 7 / 12, 12, timestamp=1_700_000_050)
    latest = write_result(runs / "latest", "task.pingu", 4 / 10, 10, timestamp=1_700_000_100)

    rows = collect_holdout_trends(runs)

    assert len(rows) == 1
    assert rows[0].best_result_path == reliable_best
    assert rows[0].latest_result_path == latest
    assert rows[0].best_holdout_resolved_rate == 7 / 12


def test_collect_holdout_trends_ignores_detailed_failure_like_fields(tmp_path):
    runs = tmp_path / "runs"
    result_path = write_result(runs / "latest", "task.cleanroom", 0.8, 10)
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    payload.update(
        {
            "holdout_failures": [{"name": "hidden-like-case", "expected": "secret"}],
            "failure_clusters": [{"stderr": "do not read me"}],
            "official_eval": {"test_results": [{"name": "hidden", "error_details": "secret"}]},
        }
    )
    result_path.write_text(json.dumps(payload), encoding="utf-8")

    rows = collect_holdout_trends(runs)

    assert len(rows) == 1
    assert rows[0].task_id == "task.cleanroom"
    assert rows[0].latest_holdout_resolved_rate == 0.8
    assert rows[0].latest_holdout_cases == 10


def test_recommend_weak_reruns_uses_only_below_gate_historical_best(tmp_path):
    runs = tmp_path / "runs"
    write_result(runs / "pingu_old", "task.pingu", 7 / 12, 12, timestamp=1_700_000_000)
    write_result(runs / "pingu_new", "task.pingu", 3 / 14, 14, timestamp=1_700_000_100)
    write_result(runs / "hexyl", "task.hexyl", 0.2, 10, timestamp=1_700_000_050)
    write_result(runs / "recovered_old", "task.recovered", 1.0, 11, timestamp=1_700_000_000)
    write_result(runs / "recovered_new", "task.recovered", 0.5, 12, timestamp=1_700_000_100)

    rows = collect_holdout_trends(runs)
    recommendations = recommend_weak_reruns(rows, history_root=str(runs))

    assert [row.task_id for row in recommendations] == ["task.hexyl", "task.pingu"]
    assert recommendations[0].reason == "historical_best_below_gate"
    assert recommendations[1].reason == "latest_regressed_and_historical_best_below_gate"
    assert "--skip-official-eval" in recommendations[0].required_flags
    assert "--require-holdout-improvement" in recommendations[0].required_flags
    assert "task.recovered" not in [row.task_id for row in recommendations]


@pytest.mark.parametrize("min_holdout_rate", [-0.1, math.nan, 1.2])
def test_recommend_weak_reruns_rejects_invalid_direct_gate(tmp_path, min_holdout_rate):
    runs = tmp_path / "runs"
    write_result(runs / "hexyl", "task.hexyl", 0.2, 10)

    rows = collect_holdout_trends(runs)

    with pytest.raises(ValueError, match="min_holdout_rate must be a finite rate between 0 and 1"):
        recommend_weak_reruns(rows, min_holdout_rate=min_holdout_rate)


def test_summarize_holdout_trends_cli_marks_regression(tmp_path):
    runs = tmp_path / "runs"
    write_result(runs / "old", "task.pingu", 7 / 12, 12, timestamp=1_700_000_000)
    write_result(runs / "new", "task.pingu", 4 / 10, 10, timestamp=1_700_000_100)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/summarize_holdout_trends.py",
            "--runs",
            str(runs),
            "--limit",
            "5",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "task.pingu" in result.stdout
    assert "regressed" in result.stdout


def test_summarize_holdout_trends_cli_prints_weak_rerun_recommendations(tmp_path):
    runs = tmp_path / "runs"
    write_result(runs / "old", "task.pingu", 7 / 12, 12, timestamp=1_700_000_000)
    write_result(runs / "new", "task.pingu", 3 / 14, 14, timestamp=1_700_000_100)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/summarize_holdout_trends.py",
            "--runs",
            str(runs),
            "--recommend-weak-reruns",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "rerun target" in result.stdout
    assert ">= 80.0% and > 58.3%" in result.stdout
    assert "--skip-official-eval --require-holdout-improvement" in result.stdout


def test_summarize_holdout_trends_cli_outputs_aggregate_only_json_with_recommendations(tmp_path):
    runs = tmp_path / "runs"
    best = write_result(runs / "old", "task.pingu", 7 / 12, 12, timestamp=1_700_000_000)
    latest = write_result(
        runs / "new",
        "task.pingu",
        4 / 10,
        10,
        timestamp=1_700_000_100,
        secret_marker="hidden-local-case",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/summarize_holdout_trends.py",
            "--runs",
            str(runs),
            "--limit",
            "5",
            "--recommend-weak-reruns",
            "--include-rerun-command",
            "--rerun-root",
            "runs/next",
            "--rerun-min-smoke-contract-axes",
            "2",
            "--rerun-require-runtime-smoke-dimensions",
            "args,input_files",
            "--rerun-min-holdout-improvement-delta",
            "0.02",
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.lstrip().startswith("{")
    assert "hidden-local-case" not in result.stdout
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == 1
    assert payload["row_count"] == 1
    assert payload["total_row_count"] == 1
    assert payload["limit"] == 5
    assert payload["rows"] == [
        {
            "rank": 1,
            "task_id": "task.pingu",
            "latest_holdout_resolved_rate": 4 / 10,
            "latest_holdout_cases": 10,
            "best_holdout_resolved_rate": 7 / 12,
            "best_holdout_cases": 12,
            "delta_from_best": (4 / 10) - (7 / 12),
            "trend": "regressed",
            "latest_result_path": str(latest),
            "best_result_path": str(best),
        }
    ]
    assert payload["recommendations"]["enabled"] is True
    assert payload["recommendations"]["row_count"] == 1
    [recommendation] = payload["recommendations"]["rows"]
    assert recommendation["task_id"] == "task.pingu"
    assert recommendation["reason"] == "latest_regressed_and_historical_best_below_gate"
    guarded_command = recommendation["guarded_command"]
    assert "--dry-run --min-smoke-contract-axes 2" in guarded_command
    assert "--require-runtime-smoke-dimensions args,input_files" in guarded_command
    assert guarded_command.endswith("--min-holdout-improvement-delta 0.02")


def test_summarize_holdout_trends_cli_json_can_filter_specific_task(tmp_path):
    runs = tmp_path / "runs"
    keep = write_result(runs / "keep", "task.keep", 0.8, 10)
    write_result(runs / "drop", "task.drop", 1.0, 10)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/summarize_holdout_trends.py",
            "--runs",
            str(runs),
            "--task",
            "task.keep",
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
    assert payload["total_row_count"] == 1
    assert payload["rows"][0]["task_id"] == "task.keep"
    assert payload["rows"][0]["latest_result_path"] == str(keep)


def test_guarded_rerun_command_uses_safe_wrapper_and_slug():
    command = build_guarded_rerun_command("owner__repo.name/with space", "runs/weak")

    assert command == (
        "python scripts/run_weak_task_cleanroom_rerun.py 'owner__repo.name/with space' "
        "--runs runs/weak/owner__repo.name_with_space --dry-run"
    )


def test_guarded_rerun_command_can_include_smoke_axis_gate():
    command = build_guarded_rerun_command(
        "task.hexyl",
        "runs/weak",
        min_smoke_contract_axes=2,
    )

    assert command.endswith("--dry-run --min-smoke-contract-axes 2")


def test_guarded_rerun_command_can_include_runtime_smoke_dimension_gate():
    command = build_guarded_rerun_command(
        "task.hexyl",
        "runs/weak",
        required_runtime_smoke_dimensions=("args", "input_files"),
    )

    assert command.endswith("--dry-run --require-runtime-smoke-dimensions args,input_files")


def test_guarded_rerun_command_can_include_config_path():
    command = build_guarded_rerun_command(
        "task.hexyl",
        "runs/weak",
        config="config/smoke_file_bridge.yaml",
    )

    assert "--config config/smoke_file_bridge.yaml" in command
    assert command.endswith("--dry-run")


def test_guarded_rerun_command_can_include_local_llm_ack():
    command = build_guarded_rerun_command(
        "task.hexyl",
        "runs/weak",
        config="config/smoke_file_bridge.yaml",
        ack_local_llm_docker=True,
    )

    assert "--config config/smoke_file_bridge.yaml" in command
    assert command.endswith("--dry-run --ack-local-llm-docker")


def test_guarded_rerun_command_can_include_holdout_improvement_delta():
    command = build_guarded_rerun_command(
        "task.hexyl",
        "runs/weak",
        min_holdout_improvement_delta=0.02,
    )

    assert command.endswith("--dry-run --min-holdout-improvement-delta 0.02")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"min_smoke_contract_axes": -1}, "min_smoke_contract_axes must be non-negative"),
        ({"min_smoke_contract_axes": 1.5}, "min_smoke_contract_axes must be non-negative"),
        (
            {"min_holdout_improvement_delta": -0.01},
            "min_holdout_improvement_delta must be non-negative and finite",
        ),
        (
            {"min_holdout_improvement_delta": math.nan},
            "min_holdout_improvement_delta must be non-negative and finite",
        ),
    ],
)
def test_guarded_rerun_command_rejects_invalid_direct_gate_thresholds(kwargs, message):
    with pytest.raises(ValueError, match=message):
        build_guarded_rerun_command("task.hexyl", "runs/weak", **kwargs)


def test_summarize_holdout_trends_cli_can_include_guarded_rerun_commands(tmp_path):
    runs = tmp_path / "runs"
    write_result(runs / "latest", "task.hexyl", 0.2, 10)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/summarize_holdout_trends.py",
            "--runs",
            str(runs),
            "--recommend-weak-reruns",
            "--include-rerun-command",
            "--rerun-root",
            "runs/next",
            "--rerun-min-smoke-contract-axes",
            "2",
            "--rerun-require-runtime-smoke-dimensions",
            "args,input_files",
            "--rerun-min-holdout-improvement-delta",
            "0.02",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "guarded command" in result.stdout
    assert "python scripts/run_weak_task_cleanroom_rerun.py task.hexyl" in result.stdout
    assert "--runs runs/next/task.hexyl --dry-run" in result.stdout
    assert "--min-smoke-contract-axes 2" in result.stdout
    assert "--require-runtime-smoke-dimensions args,input_files" in result.stdout
    assert "--min-holdout-improvement-delta 0.02" in result.stdout


def test_summarize_holdout_trends_cli_rejects_negative_rerun_gate_thresholds(tmp_path):
    for flag, value in (
        ("--rerun-min-smoke-contract-axes", "-1"),
        ("--rerun-min-holdout-improvement-delta", "-0.01"),
        ("--rerun-min-holdout-improvement-delta", "nan"),
    ):
        result = subprocess.run(
            [
                sys.executable,
                "scripts/summarize_holdout_trends.py",
                "--runs",
                str(tmp_path / "runs"),
                "--recommend-weak-reruns",
                "--include-rerun-command",
                flag,
                value,
            ],
            text=True,
            capture_output=True,
            check=False,
        )

        assert result.returncode != 0
        assert "value must be non-negative" in result.stderr


def test_summarize_holdout_trends_cli_rejects_out_of_range_holdout_rate(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "scripts/summarize_holdout_trends.py",
            "--runs",
            str(tmp_path / "runs"),
            "--recommend-weak-reruns",
            "--min-holdout-rate",
            "1.2",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "finite rate between 0 and 1" in result.stderr


@pytest.mark.parametrize("limit", ["0", "-1"])
def test_summarize_holdout_trends_cli_rejects_non_positive_limit(tmp_path, limit):
    result = subprocess.run(
        [
            sys.executable,
            "scripts/summarize_holdout_trends.py",
            "--runs",
            str(tmp_path / "runs"),
            "--limit",
            limit,
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "must be positive" in result.stderr
