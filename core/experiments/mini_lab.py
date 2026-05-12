"""ProgramBench mini-lab batch experiment helpers."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from core.programbench.samples import ProgramBenchSample


class MiniLabRow(BaseModel):
    task_id: str
    status: str
    resolved_rate: float = 0.0
    holdout_resolved_rate: float | None = None
    probes_conducted: int = 0
    iterations_used: int = 0
    exploration_cases: int = 0
    holdout_cases: int = 0
    files_generated: int | None = None
    static_output_assets_enabled: bool | None = None
    contract_asset_status: str | None = None
    result_path: Path


class MiniLabReport(BaseModel):
    rows: list[MiniLabRow] = Field(default_factory=list)

    @property
    def task_count(self) -> int:
        return len(self.rows)

    @property
    def average_resolved_rate(self) -> float:
        if not self.rows:
            return 0.0
        return sum(row.resolved_rate for row in self.rows) / len(self.rows)

    @property
    def average_holdout_resolved_rate(self) -> float | None:
        rates = [row.holdout_resolved_rate for row in self.rows if row.holdout_resolved_rate is not None]
        if not rates:
            return None
        return sum(rates) / len(rates)

    def to_payload(self) -> dict[str, Any]:
        return {
            "task_count": self.task_count,
            "average_resolved_rate": self.average_resolved_rate,
            "average_holdout_resolved_rate": self.average_holdout_resolved_rate,
            "rows": [
                row.model_dump(mode="json")
                for row in self.rows
            ],
        }


@dataclass(frozen=True)
class MiniLabReportPaths:
    json_path: Path
    markdown_path: Path


class MiniLabResultCollector:
    """Collect aggregate-only result metadata from completed cleanroom runs."""

    def collect(self, run_root: Path | str, instance_ids: list[str]) -> MiniLabReport:
        root = Path(run_root)
        rows = [self._read_row(root, instance_id) for instance_id in instance_ids]
        return MiniLabReport(rows=rows)

    def _read_row(self, run_root: Path, instance_id: str) -> MiniLabRow:
        result_path = run_root / instance_id / "generated" / instance_id / "result.json"
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        implementation_metadata = payload.get("implementation_metadata", {}) or {}
        return MiniLabRow(
            task_id=payload.get("task_id", instance_id),
            status=payload.get("status", "unknown"),
            resolved_rate=float(payload.get("resolved_rate", 0.0) or 0.0),
            holdout_resolved_rate=payload.get("holdout_resolved_rate"),
            probes_conducted=int(payload.get("probes_conducted", 0) or 0),
            iterations_used=int(payload.get("iterations_used", 0) or 0),
            exploration_cases=int(payload.get("exploration_cases", 0) or 0),
            holdout_cases=int(payload.get("holdout_cases", 0) or 0),
            files_generated=self._files_generated(run_root, instance_id),
            static_output_assets_enabled=implementation_metadata.get("static_output_assets_enabled"),
            contract_asset_status=implementation_metadata.get("contract_asset_status"),
            result_path=result_path,
        )

    def _files_generated(self, run_root: Path, instance_id: str) -> int | None:
        generated = run_root / instance_id / "generated" / instance_id
        if not generated.exists():
            return None
        return sum(1 for path in generated.rglob("*") if path.is_file() and path.name != "result.json")


class MiniLabReportWriter:
    """Write aggregate mini-lab reports."""

    def write(self, report: MiniLabReport, output_dir: Path | str) -> MiniLabReportPaths:
        target = Path(output_dir)
        target.mkdir(parents=True, exist_ok=True)
        json_path = target / "mini_lab_summary.json"
        markdown_path = target / "mini_lab_summary.md"
        payload = report.to_payload()
        json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        markdown_path.write_text(self._markdown(report), encoding="utf-8")
        return MiniLabReportPaths(json_path=json_path, markdown_path=markdown_path)

    def _markdown(self, report: MiniLabReport) -> str:
        lines = [
            "# ProgramBench Mini-Lab Summary",
            "",
            f"- tasks: {report.task_count}",
            f"- average resolved rate: {report.average_resolved_rate:.1%}",
        ]
        if report.average_holdout_resolved_rate is not None:
            lines.append(f"- average holdout rate: {report.average_holdout_resolved_rate:.1%}")
        lines.extend(
            [
                "",
                "| task | status | resolved | holdout | probes | repairs | files | assets |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
            ]
        )
        for row in report.rows:
            holdout = "-" if row.holdout_resolved_rate is None else f"{row.holdout_resolved_rate:.1%}"
            files = "-" if row.files_generated is None else str(row.files_generated)
            assets = self._asset_label(row)
            lines.append(
                f"| {row.task_id} | {row.status} | {row.resolved_rate:.1%} | "
                f"{holdout} | {row.probes_conducted} | {row.iterations_used} | {files} | {assets} |"
            )
        return "\n".join(lines) + "\n"

    def _asset_label(self, row: MiniLabRow) -> str:
        if row.static_output_assets_enabled is None:
            return "-"
        label = "enabled" if row.static_output_assets_enabled else "disabled"
        if row.contract_asset_status:
            return f"{label}/{row.contract_asset_status}"
        return label


class MiniLabCommandBuilder:
    """Build cleanroom-safe ReBuilder commands for ProgramBench samples."""

    def __init__(self, python_executable: str | None = None, main_path: str = "main.py"):
        self.python_executable = python_executable or sys.executable
        self.main_path = main_path

    def build_rebuilder_command(
        self,
        sample: ProgramBenchSample,
        workspace_path: Path | str,
        config_path: Path | str,
        max_repairs: int | None = None,
        static_output_assets: Literal["config", "enabled", "disabled"] = "config",
    ) -> list[str]:
        if not sample.cleanroom_image.endswith(":task_cleanroom"):
            raise ValueError(f"Mini-lab can only use task_cleanroom images: {sample.cleanroom_image}")
        command = [
            self.python_executable,
            self.main_path,
            "--task",
            str(workspace_path),
            "--config",
            str(config_path),
            "--reference-docker-image",
            sample.cleanroom_image,
        ]
        if max_repairs is not None:
            command.extend(["--max-repairs", str(max_repairs)])
        if static_output_assets != "config":
            command.extend(["--static-output-assets", static_output_assets])
        return command
