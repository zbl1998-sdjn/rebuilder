import json
import subprocess
import sys

from scripts.audit_official_baseline_candidates import (
    collect_baseline_candidates,
    discover_recorded_baseline_scores,
)


def write_eval(path, task_id, passed, total):
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "test_results": [
                    {"name": f"pass_{index}", "status": "passed"} for index in range(passed)
                ]
                + [
                    {"name": f"fail_{index}", "status": "failed"} for index in range(total - passed)
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


def write_baseline(path, task_id, score):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"instance_id": task_id, "official": {"score": score}}),
        encoding="utf-8",
    )


def test_collect_baseline_candidates_finds_unrecorded_and_upgrade_rows(tmp_path):
    official = tmp_path / "official"
    baselines = tmp_path / "baselines"
    write_eval(official / "run_a" / "task.new" / "task.new.eval.json", "task.new", 2, 4)
    write_eval(official / "run_b" / "task.upgrade" / "task.upgrade.eval.json", "task.upgrade", 3, 4)
    write_eval(official / "run_c" / "task.same" / "task.same.eval.json", "task.same", 1, 4)
    write_baseline(baselines / "task.upgrade.baseline.json", "task.upgrade", 50)
    write_baseline(baselines / "task.same.baseline.json", "task.same", 25)

    rows = collect_baseline_candidates(official, baselines, actionable_only=True)

    assert [(row.task_id, row.status, row.official_score, row.recorded_score) for row in rows] == [
        ("task.upgrade", "baseline_upgrade", 75, 50),
        ("task.new", "unrecorded_official", 50, None),
    ]


def test_collect_baseline_candidates_keeps_best_eval_per_task(tmp_path):
    official = tmp_path / "official"
    baselines = tmp_path / "baselines"
    weaker = write_eval(official / "old" / "task.dupe" / "task.dupe.eval.json", "task.dupe", 1, 4)
    stronger = write_eval(official / "new" / "task.dupe" / "task.dupe.eval.json", "task.dupe", 3, 4)

    rows = collect_baseline_candidates(official, baselines, actionable_only=False)

    assert len(rows) == 1
    assert rows[0].official_score == 75
    assert rows[0].eval_path == stronger
    assert rows[0].eval_path != weaker


def test_discover_recorded_baseline_scores_ignores_invalid_payloads(tmp_path):
    write_baseline(tmp_path / "good.baseline.json", "task.good", 17)
    (tmp_path / "bad_json.baseline.json").write_text("{", encoding="utf-8")
    (tmp_path / "bad_shape.baseline.json").write_text(json.dumps(["bad"]), encoding="utf-8")
    (tmp_path / "bad_score.baseline.json").write_text(
        json.dumps({"instance_id": "task.bad", "official": {"score": "nan"}}),
        encoding="utf-8",
    )

    assert discover_recorded_baseline_scores(tmp_path) == {"task.good": 17}


def test_audit_official_baseline_candidates_cli_outputs_markdown(tmp_path):
    official = tmp_path / "official"
    baselines = tmp_path / "baselines"
    write_eval(official / "run_a" / "task.new" / "task.new.eval.json", "task.new", 2, 4)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/audit_official_baseline_candidates.py",
            "--official-eval-root",
            str(official),
            "--baseline-root",
            str(baselines),
            "--actionable-only",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "unrecorded_official" in result.stdout
    assert "task.new" in result.stdout
    assert "hidden" not in result.stdout.lower()
