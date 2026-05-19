import json
import math
import os
import subprocess
import sys

import pytest

from scripts.audit_holdout_improvement import audit_holdout_improvement


def write_result(path, task_id, holdout_rate, holdout_cases, *, timestamp=1_700_000_000):
    target = path / task_id / "generated" / task_id
    target.mkdir(parents=True)
    result_path = target / "result.json"
    result_path.write_text(
        json.dumps(
            {
                "task_id": task_id,
                "status": "failed",
                "resolved_rate": 0.5,
                "holdout_resolved_rate": holdout_rate,
                "holdout_cases": holdout_cases,
                "probes_conducted": 50,
                "iterations_used": 3,
            }
        ),
        encoding="utf-8",
    )
    os.utime(result_path, (timestamp, timestamp))
    return result_path


def test_audit_holdout_improvement_accepts_result_above_prior_best(tmp_path):
    runs = tmp_path / "runs"
    write_result(runs / "old", "task.pingu", 7 / 12, 12, timestamp=1_700_000_000)
    current = write_result(runs / "new", "task.pingu", 8 / 12, 12, timestamp=1_700_000_100)

    audit = audit_holdout_improvement(current, runs_root=runs, min_holdout_cases=10)

    assert audit["improved"] is True
    assert audit["reason"] == "improved"
    assert audit["task_id"] == "task.pingu"
    assert audit["current_holdout_resolved_rate"] == 8 / 12
    assert audit["best_previous_holdout_resolved_rate"] == 7 / 12


def test_audit_holdout_improvement_blocks_regression(tmp_path):
    runs = tmp_path / "runs"
    best = write_result(runs / "best", "task.pingu", 7 / 12, 12, timestamp=1_700_000_000)
    current = write_result(runs / "latest", "task.pingu", 3 / 14, 14, timestamp=1_700_000_100)

    audit = audit_holdout_improvement(current, runs_root=runs, min_holdout_cases=10)

    assert audit["improved"] is False
    assert audit["reason"] == "not_improved"
    assert audit["best_previous_result_path"] == str(best)


def test_audit_holdout_improvement_reports_delta_below_minimum(tmp_path):
    runs = tmp_path / "runs"
    write_result(runs / "best", "task.pingu", 0.89, 12, timestamp=1_700_000_000)
    current = write_result(runs / "latest", "task.pingu", 0.90, 12, timestamp=1_700_000_100)

    audit = audit_holdout_improvement(current, runs_root=runs, min_holdout_cases=10, min_delta=0.02)

    assert audit["improved"] is False
    assert audit["reason"] == "delta_below_min"
    assert audit["delta_from_best_previous"] == 0.90 - 0.89


def test_audit_holdout_improvement_rejects_negative_thresholds(tmp_path):
    runs = tmp_path / "runs"
    current = write_result(runs / "latest", "task.pingu", 0.90, 12, timestamp=1_700_000_100)

    with pytest.raises(ValueError, match="min_delta must be non-negative"):
        audit_holdout_improvement(current, runs_root=runs, min_delta=-0.01)

    with pytest.raises(ValueError, match="min_delta must be non-negative"):
        audit_holdout_improvement(current, runs_root=runs, min_delta=math.nan)

    with pytest.raises(ValueError, match="min_holdout_cases must be non-negative"):
        audit_holdout_improvement(current, runs_root=runs, min_holdout_cases=-1)

    with pytest.raises(ValueError, match="min_holdout_cases must be"):
        audit_holdout_improvement(current, runs_root=runs, min_holdout_cases=math.nan)

    with pytest.raises(ValueError, match="min_holdout_cases must be"):
        audit_holdout_improvement(current, runs_root=runs, min_holdout_cases=1.5)


def test_audit_holdout_improvement_uses_result_path_tie_breaker_for_previous_best(tmp_path):
    runs = tmp_path / "runs"
    write_result(runs / "a_best", "task.pingu", 0.8, 12, timestamp=1_700_000_000)
    selected_best = write_result(runs / "z_best", "task.pingu", 0.8, 12, timestamp=1_700_000_000)
    current = write_result(runs / "latest", "task.pingu", 0.9, 12, timestamp=1_700_000_100)

    audit = audit_holdout_improvement(current, runs_root=runs, min_holdout_cases=10)

    assert audit["improved"] is True
    assert audit["best_previous_result_path"] == str(selected_best)


def test_audit_holdout_improvement_excludes_current_ablation_root(tmp_path):
    runs = tmp_path / "runs"
    historical_best = write_result(runs / "historical", "task.pingu", 0.7, 12, timestamp=1_700_000_000)
    write_result(runs / "restore_ablation" / "baseline_no_adaptive", "task.pingu", 0.95, 12, timestamp=1_700_000_100)
    current = write_result(runs / "restore_ablation" / "adaptive_profile", "task.pingu", 0.8, 12, timestamp=1_700_000_200)

    audit = audit_holdout_improvement(
        current,
        runs_root=runs,
        min_holdout_cases=10,
        exclude_roots=[runs / "restore_ablation"],
    )

    assert audit["improved"] is True
    assert audit["reason"] == "improved"
    assert audit["best_previous_result_path"] == str(historical_best)


def test_audit_holdout_improvement_cli_returns_nonzero_without_leaking_details(tmp_path):
    runs = tmp_path / "runs"
    write_result(runs / "best", "task.cleanroom", 0.8, 10, timestamp=1_700_000_000)
    current = write_result(runs / "latest", "task.cleanroom", 0.7, 10, timestamp=1_700_000_100)
    payload = json.loads(current.read_text(encoding="utf-8"))
    payload["holdout_failures"] = [{"name": "hidden-like", "expected": "secret"}]
    payload["official_eval"] = {"test_results": [{"name": "hidden", "stderr": "secret"}]}
    current.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/audit_holdout_improvement.py",
            str(current),
            "--runs",
            str(runs),
            "--min-holdout-cases",
            "10",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    audit = json.loads(result.stdout)
    assert result.returncode == 2
    assert audit["reason"] == "not_improved"
    assert "hidden" not in result.stdout.lower()
    assert "secret" not in result.stdout.lower()


def test_audit_holdout_improvement_cli_accepts_exclude_root(tmp_path):
    runs = tmp_path / "runs"
    historical_best = write_result(runs / "historical", "task.cleanroom", 0.7, 10, timestamp=1_700_000_000)
    write_result(runs / "restore_ablation" / "baseline_no_adaptive", "task.cleanroom", 0.95, 10)
    current = write_result(runs / "restore_ablation" / "adaptive_profile", "task.cleanroom", 0.8, 10)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/audit_holdout_improvement.py",
            str(current),
            "--runs",
            str(runs),
            "--exclude-root",
            str(runs / "restore_ablation"),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    audit = json.loads(result.stdout)
    assert result.returncode == 0
    assert audit["reason"] == "improved"
    assert audit["best_previous_result_path"] == str(historical_best)


def test_audit_holdout_improvement_cli_rejects_negative_thresholds(tmp_path):
    runs = tmp_path / "runs"
    current = write_result(runs / "latest", "task.cleanroom", 0.7, 10)

    for flag, value in (("--min-delta", "-0.01"), ("--min-delta", "nan"), ("--min-holdout-cases", "-1")):
        result = subprocess.run(
            [
                sys.executable,
                "scripts/audit_holdout_improvement.py",
                str(current),
                "--runs",
                str(runs),
                flag,
                value,
            ],
            text=True,
            capture_output=True,
            check=False,
        )

        assert result.returncode != 0
        assert "value must be non-negative" in result.stderr
