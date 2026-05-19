"""Tests for scripts/prune_runs.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.prune_runs import (  # noqa: E402
    discover_protected_paths,
    discover_runs,
    main as prune_main,
    select_deletion_candidates,
)


def _write_run(runs_root: Path, run_name: str, task_id: str, mtime: float) -> Path:
    """Create a nested run dir like real ReBuilder layout and return the widened root."""
    run_root_dir = runs_root / run_name / task_id
    nested_result_dir = run_root_dir / "generated" / task_id / task_id
    nested_result_dir.mkdir(parents=True)
    result = nested_result_dir / "result.json"
    result.write_text(json.dumps({"task_id": task_id}), encoding="utf-8")
    (run_root_dir / "evidence.bin").write_bytes(b"x" * 4096)
    (nested_result_dir / "blob.bin").write_bytes(b"x" * 1024)
    import os

    os.utime(result, (mtime, mtime))
    return run_root_dir


def test_select_deletion_candidates_keeps_newest_per_task(tmp_path):
    runs_root = tmp_path / "runs"
    _write_run(runs_root, "r1", "task_a", mtime=1000)
    _write_run(runs_root, "r2", "task_a", mtime=2000)
    newest_a = _write_run(runs_root, "r3", "task_a", mtime=3000)
    only_b = _write_run(runs_root, "rb", "task_b", mtime=500)

    entries = discover_runs(runs_root)
    candidates = select_deletion_candidates(
        entries,
        keep=1,
        protected=set(),
        task_filter=None,
    )
    candidate_dirs = {c.run_dir for c in candidates}

    assert newest_a not in candidate_dirs
    assert only_b not in candidate_dirs
    assert len(candidate_dirs) == 2


def test_protected_paths_block_deletion(tmp_path):
    runs_root = tmp_path / "runs"
    baselines_root = tmp_path / "baselines"
    baselines_root.mkdir()
    protected_run = _write_run(runs_root, "official", "task_a", mtime=100)
    _write_run(runs_root, "newer", "task_a", mtime=2000)
    _write_run(runs_root, "newest", "task_a", mtime=3000)

    submission_path = protected_run / "submission" / "task_a" / "submission.tar.gz"
    submission_path.parent.mkdir(parents=True)
    submission_path.write_bytes(b"")
    baseline_payload = {
        "instance_id": "task_a",
        "submission": {"path": str(submission_path.resolve())},
    }
    (baselines_root / "task_a.baseline.json").write_text(
        json.dumps(baseline_payload), encoding="utf-8"
    )

    entries = discover_runs(runs_root)
    protected = discover_protected_paths(baselines_root)
    candidates = select_deletion_candidates(
        entries,
        keep=1,
        protected=protected,
        task_filter=None,
    )

    assert protected_run not in {c.run_dir for c in candidates}


def test_discover_protected_paths_ignores_non_object_baseline_payload(tmp_path):
    baselines_root = tmp_path / "baselines"
    baselines_root.mkdir()
    protected_path = tmp_path / "runs" / "official" / "task_a" / "submission.tar.gz"
    protected_path.parent.mkdir(parents=True)
    protected_path.write_bytes(b"")
    (baselines_root / "bad.baseline.json").write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")
    (baselines_root / "good.baseline.json").write_text(
        json.dumps({"instance_id": "task_a", "submission": {"path": str(protected_path)}}),
        encoding="utf-8",
    )

    protected = discover_protected_paths(baselines_root)

    assert protected == {protected_path.resolve(strict=False)}


def test_discover_runs_ignores_non_object_result_payload(tmp_path):
    runs_root = tmp_path / "runs"
    bad_result = runs_root / "bad" / "task_bad" / "generated" / "task_bad" / "task_bad" / "result.json"
    bad_result.parent.mkdir(parents=True)
    bad_result.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")
    good_run = _write_run(runs_root, "good", "task_good", mtime=1000)

    entries = discover_runs(runs_root)

    assert [entry.task_id for entry in entries] == ["task_good"]
    assert entries[0].run_dir == good_run.resolve(strict=False)


def test_prune_runs_dry_run_does_not_delete(tmp_path, capsys):
    runs_root = tmp_path / "runs"
    older = _write_run(runs_root, "r1", "task_a", mtime=1000)
    _write_run(runs_root, "r2", "task_a", mtime=2000)

    exit_code = prune_main(
        [
            "--runs",
            str(runs_root),
            "--baselines",
            str(tmp_path / "absent"),
            "--keep",
            "1",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert older.exists()
    assert "WOULD DELETE" in captured.out


def test_prune_runs_apply_actually_deletes(tmp_path, capsys):
    runs_root = tmp_path / "runs"
    older = _write_run(runs_root, "r1", "task_a", mtime=1000)
    newer = _write_run(runs_root, "r2", "task_a", mtime=2000)

    exit_code = prune_main(
        [
            "--runs",
            str(runs_root),
            "--baselines",
            str(tmp_path / "absent"),
            "--keep",
            "1",
            "--apply",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert not older.exists()
    assert newer.exists()
    assert "DELETING" in captured.out
