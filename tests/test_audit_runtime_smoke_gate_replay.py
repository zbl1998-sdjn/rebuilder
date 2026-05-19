import json
import subprocess
import sys
from pathlib import Path

from core.data_models import TestCase, TestResult
from core.evidence.models import EvidenceRecord, EvidenceSource
from core.evidence.store import EvidenceStore
from scripts import audit_runtime_smoke_gate_replay as gate_replay_module
from scripts.audit_runtime_smoke_gate_replay import audit_runtime_smoke_gate_replay
from scripts.audit_runtime_smoke_replay import RuntimeSmokeReplayRow


def _write_candidate(
    root: Path,
    task_id: str,
    *,
    holdout_resolved: int = 12,
    holdout_total: int = 12,
    code: str | None = None,
) -> Path:
    generated_dir = root / "runs" / task_id / "generated" / task_id
    generated_dir.mkdir(parents=True)
    (generated_dir / "main.py").write_text(
        code
        or (
            "import argparse\n"
            "parser = argparse.ArgumentParser()\n"
            "parser.add_argument('path', nargs='?')\n"
            "parser.parse_args()\n"
            "print('ok')\n"
        ),
        encoding="utf-8",
    )
    result_path = generated_dir / "result.json"
    result_path.write_text(
        json.dumps(
            {
                "task_id": task_id,
                "implementation_metadata": {
                    "entrypoint_stage_files": ["main.py"],
                },
                "holdout_resolved_rate": holdout_resolved / holdout_total,
                "holdout_cases": holdout_total,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return result_path


def _write_contract_evidence(root: Path, task_id: str, *, secret: str = "hidden") -> None:
    evidence_dir = root / "runs" / task_id / "evidence"
    store = EvidenceStore(evidence_dir)
    store.append(
        EvidenceRecord.from_observation(
            source=EvidenceSource.REFERENCE_EXECUTABLE,
            executable_path="/workspace/executable",
            test_case=TestCase(name="help", args=["--help"]),
            result=TestResult(stdout="usage\n", exit_code=0),
            tags=["cli_discovery"],
        )
    )
    store.append(
        EvidenceRecord.from_observation(
            source=EvidenceSource.REFERENCE_EXECUTABLE,
            executable_path="/workspace/executable",
            test_case=TestCase(
                name="file_input",
                args=["input.txt"],
                input_files={"input.txt": secret.encode("utf-8")},
            ),
            result=TestResult(stdout="ok\n", exit_code=0),
            tags=["file_io"],
        )
    )


def test_gate_replay_marks_metadata_only_runtime_smoke_blocker(tmp_path: Path) -> None:
    task_id = "owner__tool.abc123"
    _write_candidate(tmp_path, task_id)
    _write_contract_evidence(tmp_path, task_id)

    rows = audit_runtime_smoke_gate_replay(
        runs_root=tmp_path / "runs",
        official_eval_root=tmp_path / "official_eval",
        required_runtime_smoke_dimensions=("args", "input_files"),
        execute_replay=True,
    )

    assert len(rows) == 1
    row = rows[0]
    assert row.task_id == task_id
    assert row.status == "metadata_only_runtime_smoke_blocker"
    assert row.original_blockers == ("runtime_smoke_not_passed",)
    assert row.remaining_blockers_after_replay == ()
    assert row.replay_status == "replay_passed"
    assert row.replay_input_dimensions == ("args", "default", "input_files")


def test_gate_replay_keeps_other_gate_blockers_after_runtime_smoke_passes(
    tmp_path: Path,
) -> None:
    task_id = "owner__weak.abc123"
    _write_candidate(tmp_path, task_id, holdout_resolved=5, holdout_total=12)
    _write_contract_evidence(tmp_path, task_id)

    rows = audit_runtime_smoke_gate_replay(
        runs_root=tmp_path / "runs",
        official_eval_root=tmp_path / "official_eval",
        required_runtime_smoke_dimensions=("args", "input_files"),
        execute_replay=True,
    )

    assert len(rows) == 1
    row = rows[0]
    assert row.status == "replay_resolved_but_other_blockers_remain"
    assert row.replay_status == "replay_passed"
    assert "runtime_smoke_not_passed" in row.original_blockers
    assert row.remaining_blockers_after_replay == ("low_holdout_rate",)


def test_gate_replay_reports_runtime_smoke_failure_kind(tmp_path: Path) -> None:
    task_id = "owner__traceback.abc123"
    _write_candidate(tmp_path, task_id, code="raise RuntimeError('boom')\n")
    _write_contract_evidence(tmp_path, task_id)

    rows = audit_runtime_smoke_gate_replay(
        runs_root=tmp_path / "runs",
        official_eval_root=tmp_path / "official_eval",
        required_runtime_smoke_dimensions=("args", "input_files"),
        execute_replay=True,
    )

    assert len(rows) == 1
    row = rows[0]
    assert row.status == "replay_failed_or_incomplete"
    assert row.replay_status == "replay_failed"
    assert row.replay_failed_issue_kind == "runtime_smoke_traceback"
    assert row.runtime_blockers_resolved is False


def test_gate_replay_separates_executor_permission_environment_blocker(
    tmp_path: Path,
    monkeypatch,
) -> None:
    task_id = "owner__sandbox.abc123"
    result_path = _write_candidate(tmp_path, task_id)
    _write_contract_evidence(tmp_path, task_id)

    def fake_replay(result_path_arg, *, required_runtime_smoke_dimensions, execute):
        assert result_path_arg == result_path
        return RuntimeSmokeReplayRow(
            task_id=task_id,
            result_path=result_path,
            status="replay_failed",
            generated_file_count=1,
            entry_point="main.py",
            evidence_contract_count=2,
            planned_runtime_smoke_status="planned",
            planned_runtime_smoke_input_dimensions=("args", "default", "input_files"),
            replay_runtime_smoke_status="failed",
            replay_runtime_smoke_input_dimensions=("args", "default", "input_files"),
            required_runtime_smoke_dimensions=("args", "input_files"),
            failed_issue_kind="runtime_smoke_executor_permission_denied",
        )

    monkeypatch.setattr(
        gate_replay_module,
        "audit_result_for_runtime_smoke_replay",
        fake_replay,
    )

    rows = audit_runtime_smoke_gate_replay(
        runs_root=tmp_path / "runs",
        official_eval_root=tmp_path / "official_eval",
        required_runtime_smoke_dimensions=("args", "input_files"),
        execute_replay=True,
    )

    assert len(rows) == 1
    row = rows[0]
    assert row.status == "replay_environment_blocked"
    assert row.replay_failed_issue_kind == "runtime_smoke_executor_permission_denied"
    assert row.remaining_blockers_after_replay == ("runtime_smoke_not_passed",)


def test_gate_replay_can_filter_specific_task(tmp_path: Path) -> None:
    keep_task = "owner__keep.abc123"
    drop_task = "owner__drop.abc123"
    _write_candidate(tmp_path, keep_task)
    _write_contract_evidence(tmp_path, keep_task)
    _write_candidate(tmp_path, drop_task)
    _write_contract_evidence(tmp_path, drop_task)

    rows = audit_runtime_smoke_gate_replay(
        runs_root=tmp_path / "runs",
        official_eval_root=tmp_path / "official_eval",
        required_runtime_smoke_dimensions=("args", "input_files"),
        execute_replay=True,
        task_ids=(keep_task,),
    )

    assert len(rows) == 1
    assert rows[0].task_id == keep_task
    assert rows[0].status == "metadata_only_runtime_smoke_blocker"


def test_gate_replay_can_filter_specific_status(tmp_path: Path) -> None:
    keep_task = "owner__keep.abc123"
    drop_task = "owner__drop.abc123"
    _write_candidate(tmp_path, keep_task)
    _write_contract_evidence(tmp_path, keep_task)
    _write_candidate(tmp_path, drop_task, code="raise RuntimeError('boom')\n")
    _write_contract_evidence(tmp_path, drop_task)

    rows = audit_runtime_smoke_gate_replay(
        runs_root=tmp_path / "runs",
        official_eval_root=tmp_path / "official_eval",
        required_runtime_smoke_dimensions=("args", "input_files"),
        execute_replay=True,
        statuses=("metadata_only_runtime_smoke_blocker",),
    )

    assert len(rows) == 1
    assert rows[0].task_id == keep_task
    assert rows[0].status == "metadata_only_runtime_smoke_blocker"


def test_gate_replay_can_filter_replay_failed_issue_kind(tmp_path: Path) -> None:
    keep_task = "owner__traceback.abc123"
    drop_task = "owner__pass.abc123"
    _write_candidate(tmp_path, keep_task, code="raise RuntimeError('boom')\n")
    _write_contract_evidence(tmp_path, keep_task)
    _write_candidate(tmp_path, drop_task)
    _write_contract_evidence(tmp_path, drop_task)

    rows = audit_runtime_smoke_gate_replay(
        runs_root=tmp_path / "runs",
        official_eval_root=tmp_path / "official_eval",
        required_runtime_smoke_dimensions=("args", "input_files"),
        execute_replay=True,
        replay_failed_issue_kinds=("runtime_smoke_traceback",),
    )

    assert len(rows) == 1
    assert rows[0].task_id == keep_task
    assert rows[0].replay_failed_issue_kind == "runtime_smoke_traceback"


def test_cli_json_is_aggregate_only(tmp_path: Path) -> None:
    task_id = "owner__secret.abc123"
    _write_candidate(tmp_path, task_id)
    _write_contract_evidence(tmp_path, task_id, secret="SECRET_INPUT_CONTENT")

    completed = subprocess.run(
        [
            sys.executable,
            str(Path("scripts") / "audit_runtime_smoke_gate_replay.py"),
            "--runs",
            str(tmp_path / "runs"),
            "--official-eval-root",
            str(tmp_path / "official_eval"),
            "--require-runtime-smoke-dimensions",
            "args,input_files",
            "--execute-replay",
            "--format",
            "json",
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )

    assert "SECRET_INPUT_CONTENT" not in completed.stdout
    payload = json.loads(completed.stdout)
    assert payload["row_count"] == 1
    assert payload["status_counts"] == {"metadata_only_runtime_smoke_blocker": 1}
    assert payload["replay_failed_issue_kind_counts"] == {}
    assert payload["rows"][0]["status"] == "metadata_only_runtime_smoke_blocker"


def test_cli_json_can_filter_specific_task(tmp_path: Path) -> None:
    keep_task = "owner__keep.abc123"
    drop_task = "owner__drop.abc123"
    _write_candidate(tmp_path, keep_task)
    _write_contract_evidence(tmp_path, keep_task)
    _write_candidate(tmp_path, drop_task)
    _write_contract_evidence(tmp_path, drop_task)

    completed = subprocess.run(
        [
            sys.executable,
            str(Path("scripts") / "audit_runtime_smoke_gate_replay.py"),
            "--runs",
            str(tmp_path / "runs"),
            "--official-eval-root",
            str(tmp_path / "official_eval"),
            "--require-runtime-smoke-dimensions",
            "args,input_files",
            "--execute-replay",
            "--task",
            keep_task,
            "--format",
            "json",
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )

    payload = json.loads(completed.stdout)
    assert payload["row_count"] == 1
    assert payload["total_row_count"] == 1
    assert payload["rows"][0]["task_id"] == keep_task


def test_cli_json_reports_runtime_smoke_failure_kind_without_details(tmp_path: Path) -> None:
    task_id = "owner__traceback.abc123"
    _write_candidate(tmp_path, task_id, code="raise RuntimeError('SECRET-TRACEBACK')\n")
    _write_contract_evidence(tmp_path, task_id)

    completed = subprocess.run(
        [
            sys.executable,
            str(Path("scripts") / "audit_runtime_smoke_gate_replay.py"),
            "--runs",
            str(tmp_path / "runs"),
            "--official-eval-root",
            str(tmp_path / "official_eval"),
            "--require-runtime-smoke-dimensions",
            "args,input_files",
            "--execute-replay",
            "--format",
            "json",
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )

    assert "SECRET-TRACEBACK" not in completed.stdout
    payload = json.loads(completed.stdout)
    assert payload["status_counts"] == {"replay_failed_or_incomplete": 1}
    assert payload["replay_failed_issue_kind_counts"] == {
        "runtime_smoke_traceback": 1
    }
    assert payload["rows"][0]["replay_failed_issue_kind"] == "runtime_smoke_traceback"


def test_cli_json_can_filter_status_and_replay_failed_issue_kind(
    tmp_path: Path,
) -> None:
    keep_task = "owner__traceback.abc123"
    drop_task = "owner__pass.abc123"
    _write_candidate(
        tmp_path,
        keep_task,
        code="raise RuntimeError('SECRET-TRACEBACK')\n",
    )
    _write_contract_evidence(tmp_path, keep_task)
    _write_candidate(tmp_path, drop_task)
    _write_contract_evidence(tmp_path, drop_task)

    completed = subprocess.run(
        [
            sys.executable,
            str(Path("scripts") / "audit_runtime_smoke_gate_replay.py"),
            "--runs",
            str(tmp_path / "runs"),
            "--official-eval-root",
            str(tmp_path / "official_eval"),
            "--require-runtime-smoke-dimensions",
            "args,input_files",
            "--execute-replay",
            "--status",
            "replay_failed_or_incomplete",
            "--replay-failed-issue-kind",
            "runtime_smoke_traceback",
            "--format",
            "json",
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )

    assert "SECRET-TRACEBACK" not in completed.stdout
    payload = json.loads(completed.stdout)
    assert payload["row_count"] == 1
    assert payload["total_row_count"] == 1
    assert payload["status_counts"] == {"replay_failed_or_incomplete": 1}
    assert payload["replay_failed_issue_kind_counts"] == {
        "runtime_smoke_traceback": 1
    }
    assert payload["rows"][0]["task_id"] == keep_task
