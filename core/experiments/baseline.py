"""Record aggregate ProgramBench baselines without hidden-test details."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

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
        local_payload = json.loads(Path(local_result_path).read_text(encoding="utf-8"))
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
                "resolved_rate": local_payload.get("resolved_rate", 0.0),
                "holdout_resolved_rate": local_payload.get("holdout_resolved_rate"),
                "probes_conducted": local_payload.get("probes_conducted", 0),
                "iterations_used": local_payload.get("iterations_used", 0),
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
        record_path.write_text(
            json.dumps(record, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return record_path

    def _load_official_summary(self, instance_id: str, official_eval_path: Path | str):
        return ProgramBenchEvalParser().parse(official_eval_path, instance_id=instance_id)

    def _sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
