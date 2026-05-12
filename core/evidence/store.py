"""File-backed evidence storage."""

from __future__ import annotations

import base64
import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, List

from .models import EvidenceRecord


class EvidenceStore:
    """Persist evidence records as individual JSON files plus a compact index."""

    def __init__(self, root_path: Path | str):
        self.root_path = Path(root_path)
        self.records_path = self.root_path / "records"
        self.index_path = self.root_path / "index.json"
        self.records_path.mkdir(parents=True, exist_ok=True)

    def append(self, record: EvidenceRecord) -> EvidenceRecord:
        record_path = self.records_path / f"{record.record_id}.json"
        payload = self._json_safe(record.model_dump())
        record_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self._write_index(self._read_index() + [self._index_entry(record)])
        return record

    def get(self, record_id: str) -> EvidenceRecord:
        record_path = self.records_path / f"{record_id}.json"
        payload = json.loads(record_path.read_text(encoding="utf-8"))
        return EvidenceRecord.model_validate(self._from_json_safe(payload))

    def list_records(self) -> List[EvidenceRecord]:
        return [self.get(item["record_id"]) for item in self._read_index()]

    def _read_index(self) -> List[dict]:
        if not self.index_path.exists():
            return []
        return json.loads(self.index_path.read_text(encoding="utf-8"))

    def _write_index(self, entries: List[dict]) -> None:
        deduped = {entry["record_id"]: entry for entry in entries}
        ordered = sorted(deduped.values(), key=lambda item: item["observed_at"])
        self.index_path.write_text(
            json.dumps(ordered, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _index_entry(self, record: EvidenceRecord) -> dict:
        return {
            "record_id": record.record_id,
            "source": record.source.value,
            "test_name": record.test_case.name,
            "tags": list(record.tags),
            "observed_at": record.observed_at.isoformat(),
        }

    def _json_safe(self, value: Any) -> Any:
        if isinstance(value, bytes):
            return {
                "__type__": "bytes",
                "base64": base64.b64encode(value).decode("ascii"),
            }
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, dict):
            return {key: self._json_safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._json_safe(item) for item in value]
        return value

    def _from_json_safe(self, value: Any) -> Any:
        if isinstance(value, dict):
            if value.get("__type__") == "bytes":
                return base64.b64decode(value["base64"])
            return {key: self._from_json_safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._from_json_safe(item) for item in value]
        return value
