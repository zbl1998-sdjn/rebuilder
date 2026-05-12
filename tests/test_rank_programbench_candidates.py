import json

from scripts.rank_programbench_candidates import collect_candidates, discover_baseline_task_ids, format_rate


def write_result(path, task_id, resolved, holdout, *, status="failed", holdout_cases=10):
    target = path / task_id / "generated" / task_id
    target.mkdir(parents=True)
    (target / "result.json").write_text(
        json.dumps(
            {
                "task_id": task_id,
                "status": status,
                "resolved_rate": resolved,
                "holdout_resolved_rate": holdout,
                "holdout_cases": holdout_cases,
                "probes_conducted": 10,
                "iterations_used": 1,
                "implementation_metadata": {"static_output_assets_enabled": False},
            }
        ),
        encoding="utf-8",
    )
    return target / "result.json"


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


def test_collect_candidates_prefers_reliable_run_for_same_task(tmp_path):
    runs = tmp_path / "runs"
    official = tmp_path / "official"
    write_result(runs / "run_low_sample", "task.a", 0.9, 0.95, holdout_cases=4)
    write_result(runs / "run_reliable", "task.a", 0.8, 0.7, holdout_cases=12)

    rows = collect_candidates(runs, official, min_holdout_cases=10)

    assert len(rows) == 1
    assert rows[0].holdout_cases == 12


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


def test_format_rate_handles_missing_holdout():
    assert format_rate(None) == "-"
