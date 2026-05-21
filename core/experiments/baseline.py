"""Record aggregate ProgramBench baselines without hidden-test details."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from core.evaluation import ProgramBenchEvalParser


class BaselineRecorder:
    """Freeze local and official aggregate metrics for a reconstruction run."""

    def record(
        self,
        instance_id: str,
        local_result_path: Path | str,
        official_eval_path: Path | str,
        submission_archive_path: Path | str,
        output_dir: Path | str,
        model: str,
        config_path: str,
        notes: str = "",
    ) -> Path:
        local_payload = self._load_local_payload(Path(local_result_path), instance_id)
        official = self._load_official_summary(instance_id, official_eval_path)
        archive = Path(submission_archive_path)
        record = {
            "schema_version": 1,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "instance_id": instance_id,
            "model": model,
            "config_path": config_path,
            "notes": notes,
            "local": {
                "status": local_payload.get("status"),
                "resolved_rate": self._as_float(local_payload.get("resolved_rate")),
                "holdout_resolved_rate": self._as_optional_float(local_payload.get("holdout_resolved_rate")),
                "probes_conducted": self._as_int(local_payload.get("probes_conducted")),
                "iterations_used": self._as_int(local_payload.get("iterations_used")),
            },
            "official": {
                "passed_tests": official.passed_tests,
                "total_tests": official.total_tests,
                "pass_rate": official.pass_rate,
                "score": round(official.score * 100),
                "fully_resolved": official.fully_resolved,
                "almost_resolved": official.almost_resolved,
                "error_code": official.error_code,
                "warning_count": len(official.warnings),
            },
            "submission": {
                "path": str(archive),
                "sha256": self._sha256(archive),
            },
        }
        target = Path(output_dir)
        target.mkdir(parents=True, exist_ok=True)
        record_path = target / f"{instance_id}.baseline.json"
        if record_path.exists() and not self._candidate_beats_existing_record(record_path, record):
            return record_path
        record_path.write_text(
            json.dumps(record, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return record_path

    def _load_local_payload(self, path: Path, instance_id: str) -> dict[str, object]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"task_id": instance_id, "status": "invalid_result"}
        if not isinstance(payload, dict):
            return {"task_id": instance_id, "status": "invalid_result"}
        return payload

    def _as_float(self, value: object) -> float:
        if value is None:
            value = 0.0
        try:
            parsed = float(cast(Any, value))
        except (TypeError, ValueError):
            return 0.0
        return parsed if math.isfinite(parsed) and 0.0 <= parsed <= 1.0 else 0.0

    def _as_optional_float(self, value: object) -> float | None:
        if value is None:
            return None
        try:
            parsed = float(cast(Any, value))
        except (TypeError, ValueError):
            return None
        return parsed if math.isfinite(parsed) and 0.0 <= parsed <= 1.0 else None

    def _as_int(self, value: object) -> int:
        if isinstance(value, bool):
            return 0
        if value is None:
            value = 0
        try:
            parsed = float(cast(Any, value))
        except (TypeError, ValueError):
            return 0
        if not math.isfinite(parsed) or parsed < 0 or not parsed.is_integer():
            return 0
        return int(parsed)

    def _load_official_summary(self, instance_id: str, official_eval_path: Path | str):
        return ProgramBenchEvalParser().parse(official_eval_path, instance_id=instance_id)

    def _candidate_beats_existing_record(self, existing_path: Path, candidate: dict[str, object]) -> bool:
        try:
            existing = json.loads(existing_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return True
        if not isinstance(existing, dict):
            return True
        return self._official_rank(candidate) > self._official_rank(existing)

    def _official_rank(self, record: dict[str, object]) -> tuple[int, int, int, int, float]:
        official = record.get("official")
        if not isinstance(official, dict):
            return (0, 0, 0, 0, 0.0)
        fully_resolved = 1 if official.get("fully_resolved") is True else 0
        almost_resolved = 1 if official.get("almost_resolved") is True else 0
        score = self._as_int(official.get("score"))
        passed_tests = self._as_int(official.get("passed_tests"))
        pass_rate = self._as_float(official.get("pass_rate"))
        return (fully_resolved, almost_resolved, score, passed_tests, pass_rate)

    def _sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
