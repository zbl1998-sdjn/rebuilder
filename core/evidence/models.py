"""Evidence models for traceable ProgramBench behavior observations."""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from core.data_models import TestCase, TestResult


class EvidenceSource(str, Enum):
    """Where an evidence record came from."""

    REFERENCE_EXECUTABLE = "reference_executable"
    CANDIDATE_EXECUTABLE = "candidate_executable"
    BUNDLED_DOCUMENTATION = "bundled_documentation"


def _bytes_sha256(value: bytes | str) -> str:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(raw).hexdigest()


def json_safe_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return {
            "__type__": "bytes",
            "base64": base64.b64encode(value).decode("ascii"),
        }
    if isinstance(value, dict):
        return {key: json_safe_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe_value(item) for item in value]
    return value


def test_case_fingerprint(test_case: TestCase) -> str:
    """Return a stable fingerprint for the executable-visible input."""
    payload = {
        "args": list(test_case.args),
        "stdin": test_case.stdin,
        "input_files": {
            key: _bytes_sha256(value)
            for key, value in sorted(test_case.input_files.items())
        },
        "env_vars": dict(sorted(test_case.env_vars.items())),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


test_case_fingerprint.__test__ = False


def test_case_json_payload(test_case: TestCase) -> dict[str, Any]:
    return json_safe_value(test_case.model_dump())


class EvidenceRecord(BaseModel):
    """A single traceable observation of executable behavior."""

    record_id: str
    source: EvidenceSource
    executable_path: str
    test_case: TestCase
    result: TestResult
    tags: List[str] = Field(default_factory=list)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, str] = Field(default_factory=dict)

    @classmethod
    def from_observation(
        cls,
        source: EvidenceSource,
        executable_path: str,
        test_case: TestCase,
        result: TestResult,
        tags: List[str] | None = None,
        metadata: Dict[str, str] | None = None,
    ) -> "EvidenceRecord":
        fingerprint = test_case_fingerprint(test_case)
        result_payload = {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.exit_code,
            "timeout_triggered": result.timeout_triggered,
            "output_files": {
                key: _bytes_sha256(value)
                for key, value in sorted(result.output_files.items())
            },
        }
        encoded = json.dumps(
            {
                "source": source.value,
                "executable_path": executable_path,
                "test_case": fingerprint,
                "result": result_payload,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        record_id = hashlib.sha256(encoded).hexdigest()
        return cls(
            record_id=record_id,
            source=source,
            executable_path=executable_path,
            test_case=test_case,
            result=result,
            tags=tags or [],
            metadata=metadata or {},
        )
