import json
import subprocess
import sys

from core.codebase.integrity import CodebaseIntegrityIssue
from core.codebase.runtime_smoke import RuntimeSmokeReport
from core.data_models import TestCase, TestResult
from core.evidence.models import EvidenceRecord, EvidenceSource
from core.evidence.store import EvidenceStore
from scripts import audit_runtime_smoke_replay as replay_module
from scripts.audit_runtime_smoke_replay import audit_runtime_smoke_replay


def write_candidate(root, task_id="task.ready", *, code="print('ok')\n"):
    generated = root / "run" / task_id / "generated" / task_id
    generated.mkdir(parents=True)
    (generated / "main.py").write_text(code, encoding="utf-8")
    result = generated / "result.json"
    result.write_text(
        json.dumps(
            {
                "task_id": task_id,
                "status": "failed",
                "holdout_cases": 12,
                "holdout_resolved_rate": 0.5,
                "implementation_metadata": {
                    "entrypoint_stage_files": ["main.py"],
                },
            }
        ),
        encoding="utf-8",
    )
    return result


def append_evidence(root, task_id, test_case, result=None, tags=None):
    store = EvidenceStore(root / "run" / task_id / "evidence")
    record = EvidenceRecord.from_observation(
        source=EvidenceSource.REFERENCE_EXECUTABLE,
        executable_path="/workspace/executable",
        test_case=test_case,
        result=result or TestResult(stdout="ok\n", exit_code=0),
        tags=tags or [],
    )
    store.append(record)


def test_audit_runtime_smoke_replay_reports_ready_from_evidence_contracts(tmp_path):
    write_candidate(tmp_path, "task.ready")
    append_evidence(
        tmp_path,
        "task.ready",
        TestCase(name="help", args=["--help"]),
        tags=["cli_discovery"],
    )
    append_evidence(
        tmp_path,
        "task.ready",
        TestCase(
            name="file_input",
            args=["--input", "input.txt"],
            input_files={"input.txt": b"alpha\n"},
        ),
        tags=["file_io"],
    )

    rows = audit_runtime_smoke_replay(
        tmp_path,
        required_runtime_smoke_dimensions=("args", "input_files"),
    )

    assert len(rows) == 1
    row = rows[0]
    assert row.status == "ready_for_replay"
    assert row.evidence_contract_count == 2
    assert row.generated_file_count == 1
    assert row.planned_runtime_smoke_status == "planned"
    assert row.planned_runtime_smoke_input_dimensions == ("args", "default", "input_files")
    assert row.missing_required_dimensions == ()


def test_audit_runtime_smoke_replay_reports_missing_contract_artifacts(tmp_path):
    write_candidate(tmp_path, "task.missing")

    rows = audit_runtime_smoke_replay(
        tmp_path,
        required_runtime_smoke_dimensions=("args", "input_files"),
    )

    assert len(rows) == 1
    row = rows[0]
    assert row.status == "insufficient_contract_artifacts"
    assert row.evidence_contract_count == 0
    assert row.planned_runtime_smoke_input_dimensions == ("args", "default")
    assert row.missing_required_dimensions == ("input_files",)


def test_audit_runtime_smoke_replay_can_filter_specific_tasks(tmp_path):
    write_candidate(tmp_path, "task.keep")
    append_evidence(
        tmp_path,
        "task.keep",
        TestCase(
            name="file_input",
            args=["input.txt"],
            input_files={"input.txt": b"alpha\n"},
        ),
        tags=["file_io"],
    )
    write_candidate(tmp_path, "task.drop")
    append_evidence(
        tmp_path,
        "task.drop",
        TestCase(
            name="file_input",
            args=["input.txt"],
            input_files={"input.txt": b"beta\n"},
        ),
        tags=["file_io"],
    )

    rows = audit_runtime_smoke_replay(
        tmp_path,
        required_runtime_smoke_dimensions=("args", "input_files"),
        task_ids=("task.keep",),
    )

    assert len(rows) == 1
    assert rows[0].task_id == "task.keep"
    assert rows[0].status == "ready_for_replay"


def test_audit_runtime_smoke_replay_can_execute_local_smoke(tmp_path):
    write_candidate(tmp_path, "task.execute")
    append_evidence(
        tmp_path,
        "task.execute",
        TestCase(
            name="file_input",
            args=["input.txt"],
            input_files={"input.txt": b"alpha\n"},
        ),
        tags=["file_io"],
    )

    rows = audit_runtime_smoke_replay(
        tmp_path,
        required_runtime_smoke_dimensions=("args", "input_files"),
        execute=True,
    )

    assert len(rows) == 1
    row = rows[0]
    assert row.status == "replay_passed"
    assert row.replay_runtime_smoke_status == "passed"
    assert row.replay_runtime_smoke_input_dimensions == ("args", "default", "input_files")


def test_audit_runtime_smoke_replay_separates_executor_permission_environment_blocker(
    tmp_path, monkeypatch
):
    write_candidate(tmp_path, "task.blocked")
    append_evidence(
        tmp_path,
        "task.blocked",
        TestCase(
            name="file_input",
            args=["input.txt"],
            input_files={"input.txt": b"alpha\n"},
        ),
        tags=["file_io"],
    )

    class PermissionBlockedChecker:
        def plan_metadata(self, contracts):
            return {
                "status": "planned",
                "input_dimensions": ["args", "default", "input_files"],
            }

        async def check(self, codebase, *, entry_point, behavior_contracts):
            return RuntimeSmokeReport(
                [
                    CodebaseIntegrityIssue(
                        kind="runtime_smoke_executor_permission_denied",
                        path="main.py",
                        module="main.py",
                        message="permission denied",
                    )
                ],
                {
                    "status": "failed",
                    "input_dimensions": ["args", "default", "input_files"],
                    "failed_issue_kind": "runtime_smoke_executor_permission_denied",
                },
            )

    monkeypatch.setattr(replay_module, "PythonRuntimeSmokeChecker", PermissionBlockedChecker)

    rows = audit_runtime_smoke_replay(
        tmp_path,
        required_runtime_smoke_dimensions=("args", "input_files"),
        execute=True,
    )

    assert len(rows) == 1
    assert rows[0].status == "replay_environment_blocked"
    assert rows[0].failed_issue_kind == "runtime_smoke_executor_permission_denied"


def test_audit_runtime_smoke_replay_cli_outputs_aggregate_only_json(tmp_path):
    write_candidate(tmp_path, "task.secret")
    append_evidence(
        tmp_path,
        "task.secret",
        TestCase(
            name="file_input",
            args=["--input", "secret.txt"],
            input_files={"secret.txt": b"SECRET-SHOULD-NOT-LEAK\n"},
        ),
        tags=["file_io"],
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/audit_runtime_smoke_replay.py",
            "--runs",
            str(tmp_path),
            "--require-runtime-smoke-dimensions",
            "args,input_files",
            "--format",
            "json",
        ],
        cwd=".",
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "SECRET-SHOULD-NOT-LEAK" not in result.stdout
    payload = json.loads(result.stdout)
    assert payload["row_count"] == 1
    assert payload["status_counts"] == {"ready_for_replay": 1}
    assert payload["failed_issue_kind_counts"] == {}
    assert payload["rows"][0]["status"] == "ready_for_replay"
    assert payload["rows"][0]["planned_runtime_smoke_input_dimensions"] == [
        "args",
        "default",
        "input_files",
    ]


def test_audit_runtime_smoke_replay_cli_can_filter_specific_task(tmp_path):
    write_candidate(tmp_path, "task.keep")
    append_evidence(
        tmp_path,
        "task.keep",
        TestCase(
            name="file_input",
            args=["input.txt"],
            input_files={"input.txt": b"alpha\n"},
        ),
        tags=["file_io"],
    )
    write_candidate(tmp_path, "task.drop")
    append_evidence(
        tmp_path,
        "task.drop",
        TestCase(
            name="file_input",
            args=["input.txt"],
            input_files={"input.txt": b"beta\n"},
        ),
        tags=["file_io"],
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/audit_runtime_smoke_replay.py",
            "--runs",
            str(tmp_path),
            "--task",
            "task.keep",
            "--require-runtime-smoke-dimensions",
            "args,input_files",
            "--format",
            "json",
        ],
        cwd=".",
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["row_count"] == 1
    assert payload["total_row_count"] == 1
    assert payload["rows"][0]["task_id"] == "task.keep"


def test_audit_runtime_smoke_replay_cli_can_filter_status_and_failed_issue_kind(
    tmp_path,
):
    write_candidate(tmp_path, "task.keep", code="def broken(:\n    pass\n")
    append_evidence(
        tmp_path,
        "task.keep",
        TestCase(
            name="file_input",
            args=["input.txt"],
            input_files={"input.txt": b"alpha\n"},
        ),
        tags=["file_io"],
    )
    write_candidate(tmp_path, "task.drop")
    append_evidence(
        tmp_path,
        "task.drop",
        TestCase(
            name="file_input",
            args=["input.txt"],
            input_files={"input.txt": b"beta\n"},
        ),
        tags=["file_io"],
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/audit_runtime_smoke_replay.py",
            "--runs",
            str(tmp_path),
            "--require-runtime-smoke-dimensions",
            "args,input_files",
            "--execute",
            "--status",
            "replay_failed",
            "--failed-issue-kind",
            "runtime_smoke_syntax_error",
            "--format",
            "json",
        ],
        cwd=".",
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["row_count"] == 1
    assert payload["total_row_count"] == 1
    assert payload["status_counts"] == {"replay_failed": 1}
    assert payload["failed_issue_kind_counts"] == {"runtime_smoke_syntax_error": 1}
    assert payload["rows"][0]["task_id"] == "task.keep"
    assert payload["rows"][0]["failed_issue_kind"] == "runtime_smoke_syntax_error"
