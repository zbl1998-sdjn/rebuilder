import json

import pytest

from core.data_models import TestCase, TestResult
from core.evidence.models import EvidenceRecord, EvidenceSource, test_case_fingerprint
from core.evidence.store import EvidenceStore
from core.probe_engine import ProbeEngine
from tests.test_probe_engine import MockLLMClient


def test_test_case_fingerprint_is_deterministic_for_equivalent_cases():
    first = TestCase(
        name="first",
        args=["--flag", "value"],
        stdin="hello",
        input_files={"b.txt": b"two", "a.txt": b"one"},
        env_vars={"B": "2", "A": "1"},
    )
    second = TestCase(
        name="second",
        args=["--flag", "value"],
        stdin="hello",
        input_files={"a.txt": b"one", "b.txt": b"two"},
        env_vars={"A": "1", "B": "2"},
    )

    assert test_case_fingerprint(first) == test_case_fingerprint(second)


def test_evidence_store_persists_and_loads_records(tmp_path):
    store = EvidenceStore(tmp_path)
    test_case = TestCase(name="help", args=["--help"])
    result = TestResult(stdout="usage\n", exit_code=0)
    record = EvidenceRecord.from_observation(
        source=EvidenceSource.REFERENCE_EXECUTABLE,
        executable_path="/workspace/executable",
        test_case=test_case,
        result=result,
        tags=["cli_discovery"],
    )

    stored = store.append(record)
    loaded = store.get(stored.record_id)

    assert loaded == stored
    assert store.list_records() == [stored]
    index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert index[0]["record_id"] == stored.record_id


def test_evidence_store_persists_binary_inputs_and_outputs(tmp_path):
    store = EvidenceStore(tmp_path)
    test_case = TestCase(
        name="binary",
        input_files={"input.bin": b"\x00\xff\x01"},
    )
    result = TestResult(output_files={"out.bin": b"\x10\x80\xff"}, exit_code=0)
    record = EvidenceRecord.from_observation(
        source=EvidenceSource.REFERENCE_EXECUTABLE,
        executable_path="/workspace/executable",
        test_case=test_case,
        result=result,
        tags=["file_io"],
    )

    stored = store.append(record)
    loaded = store.get(stored.record_id)

    assert loaded == stored
    assert loaded.test_case.input_files["input.bin"] == b"\x00\xff\x01"
    assert loaded.result.output_files["out.bin"] == b"\x10\x80\xff"


@pytest.mark.asyncio
async def test_probe_engine_can_record_reference_evidence(tmp_path):
    script = tmp_path / "program.py"
    script.write_text("print('hello')\n", encoding="utf-8")
    evidence = EvidenceStore(tmp_path / "evidence")
    engine = ProbeEngine(
        executable=script,
        documentation="prints hello",
        llm_client=MockLLMClient(),
        max_iterations=0,
        evidence_store=evidence,
    )

    await engine._run_test(TestCase(name="hello"))

    records = evidence.list_records()
    assert len(records) == 1
    assert records[0].source == EvidenceSource.REFERENCE_EXECUTABLE
    assert records[0].result.stdout.strip() == "hello"
