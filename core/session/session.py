"""Run session layout for reproducible reconstruction experiments."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class RunSession:
    """Directory contract for one cleanroom reconstruction attempt."""

    DIRECTORY_NAMES = ("workspace", "evidence", "generated", "reports", "compliance", "logs")

    def __init__(self, root_path: Path, task_id: str, source: str):
        self.root_path = Path(root_path)
        self.task_id = task_id
        self.source = source

    @classmethod
    def create(cls, root_path: Path | str, task_id: str, source: str) -> "RunSession":
        session = cls(Path(root_path) / task_id, task_id=task_id, source=source)
        session.root_path.mkdir(parents=True, exist_ok=True)
        for directory in cls.DIRECTORY_NAMES:
            (session.root_path / directory).mkdir(parents=True, exist_ok=True)
        session._write_manifest()
        return session

    @classmethod
    def load(cls, root_path: Path | str) -> "RunSession":
        root = Path(root_path)
        payload = json.loads((root / "session.json").read_text(encoding="utf-8"))
        return cls(root, task_id=payload["task_id"], source=payload["source"])

    @property
    def manifest_path(self) -> Path:
        return self.root_path / "session.json"

    @property
    def workspace_path(self) -> Path:
        return self.root_path / "workspace"

    @property
    def evidence_path(self) -> Path:
        return self.root_path / "evidence"

    @property
    def generated_path(self) -> Path:
        return self.root_path / "generated"

    @property
    def reports_path(self) -> Path:
        return self.root_path / "reports"

    @property
    def compliance_path(self) -> Path:
        return self.root_path / "compliance"

    @property
    def logs_path(self) -> Path:
        return self.root_path / "logs"

    def _write_manifest(self) -> None:
        payload = {
            "task_id": self.task_id,
            "source": self.source,
            "cleanroom_contract": "programbench",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "directories": {
                name: str(self.root_path / name) for name in self.DIRECTORY_NAMES
            },
        }
        self.manifest_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
