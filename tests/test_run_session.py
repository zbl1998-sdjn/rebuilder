import json

from core.session import RunSession


def test_run_session_creates_expected_directory_contract(tmp_path):
    session = RunSession.create(
        root_path=tmp_path / "runs",
        task_id="owner__repo.abcdef0",
        source="programbench_cleanroom",
    )

    assert session.root_path == tmp_path / "runs" / "owner__repo.abcdef0"
    assert session.workspace_path.exists()
    assert session.evidence_path.exists()
    assert session.generated_path.exists()
    assert session.reports_path.exists()
    assert session.compliance_path.exists()
    assert session.logs_path.exists()

    manifest = json.loads(session.manifest_path.read_text(encoding="utf-8"))
    assert manifest["task_id"] == "owner__repo.abcdef0"
    assert manifest["source"] == "programbench_cleanroom"
    assert manifest["cleanroom_contract"] == "programbench"


def test_run_session_can_be_loaded_from_manifest(tmp_path):
    created = RunSession.create(
        root_path=tmp_path / "runs",
        task_id="owner__repo.abcdef0",
        source="programbench_cleanroom",
    )

    loaded = RunSession.load(created.root_path)

    assert loaded.task_id == created.task_id
    assert loaded.evidence_path == created.evidence_path
    assert loaded.generated_path == created.generated_path
