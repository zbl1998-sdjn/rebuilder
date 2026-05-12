"""Experiment runner scaffolding for ProgramBench ablations."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from core.programbench.samples import ProgramBenchSample
from core.session import RunSession


class ExperimentRunner:
    """Write reproducible experiment metadata without running hidden evaluation."""

    def write_dry_run_report(
        self,
        session: RunSession,
        sample: ProgramBenchSample,
        architecture_variant: str,
    ) -> Path:
        report_path = session.reports_path / "experiment.dry-run.json"
        payload = {
            "instance_id": sample.instance_id,
            "source_project": sample.source_project,
            "architecture_variant": architecture_variant,
            "cleanroom_image": sample.cleanroom_image,
            "task_image": sample.task_image,
            "session": str(session.root_path),
            "uses_hidden_tests": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        report_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return report_path
