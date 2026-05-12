"""Write detailed failure reports for exploration-only cleanroom diagnostics."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from core.data_models import DiffReport
from core.repair.clustering import FailureClusterer


@dataclass(frozen=True)
class FailureReportPaths:
    json_path: Path
    markdown_path: Path


class FailureReportWriter:
    """Persist clustered differential failures without exposing holdout details."""

    def write(
        self,
        reports: list[DiffReport],
        output_dir: Path | str,
        task_id: str,
        scope: str = "exploration",
    ) -> FailureReportPaths:
        if scope != "exploration":
            raise ValueError("Detailed failure reports are only allowed for exploration data, not holdout data.")

        target_dir = Path(output_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        safe_task_id = self._safe_name(task_id)
        json_path = target_dir / f"{safe_task_id}.{scope}.failures.json"
        markdown_path = target_dir / f"{safe_task_id}.{scope}.failures.md"

        payload = self._payload(reports=reports, task_id=task_id, scope=scope)
        json_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        markdown_path.write_text(self._markdown(payload), encoding="utf-8")
        return FailureReportPaths(json_path=json_path, markdown_path=markdown_path)

    def _payload(self, reports: list[DiffReport], task_id: str, scope: str) -> dict:
        failures = [report for report in reports if not report.is_equivalent]
        clusters = FailureClusterer().cluster(reports)
        return {
            "task_id": task_id,
            "scope": scope,
            "total_reports": len(reports),
            "total_failures": len(failures),
            "clusters": [
                {
                    "kind": cluster.kind.value,
                    "count": len(cluster.reports),
                    "representative": self._representative(cluster.reports[0]),
                }
                for cluster in clusters
            ],
        }

    def _representative(self, report: DiffReport) -> dict:
        return {
            "test_name": report.test_case.name,
            "args": list(report.test_case.args),
            "original_exit_code": report.original_result.exit_code,
            "replacement_exit_code": report.replacement_result.exit_code,
            "stdout_match": report.stdout_match,
            "stderr_match": report.stderr_match,
            "exit_code_match": report.exit_code_match,
            "file_outputs_match": report.file_outputs_match,
            "original_stdout": self._snippet(report.original_result.stdout),
            "replacement_stdout": self._snippet(report.replacement_result.stdout),
            "original_stderr": self._snippet(report.original_result.stderr),
            "replacement_stderr": self._snippet(report.replacement_result.stderr),
        }

    def _markdown(self, payload: dict) -> str:
        lines = [
            f"# Failure Report: {payload['task_id']}",
            "",
            f"scope: {payload['scope']}",
            f"total reports: {payload['total_reports']}",
            f"total failures: {payload['total_failures']}",
            "",
        ]
        for cluster in payload["clusters"]:
            rep = cluster["representative"]
            lines.extend(
                [
                    f"## {cluster['kind']} ({cluster['count']})",
                    "",
                    f"- test: `{rep['test_name']}`",
                    f"- args: `{rep['args']}`",
                    f"- exit: original `{rep['original_exit_code']}`, replacement `{rep['replacement_exit_code']}`",
                    f"- stdout match: `{rep['stdout_match']}`",
                    f"- stderr match: `{rep['stderr_match']}`",
                    "",
                    "original stdout:",
                    "```text",
                    rep["original_stdout"],
                    "```",
                    "",
                    "replacement stdout:",
                    "```text",
                    rep["replacement_stdout"],
                    "```",
                    "",
                    "replacement stderr:",
                    "```text",
                    rep["replacement_stderr"],
                    "```",
                    "",
                ]
            )
        return "\n".join(lines)

    def _snippet(self, value: str, limit: int = 240) -> str:
        normalized = value.replace("\r\n", "\n")
        return normalized[:limit]

    def _safe_name(self, value: str) -> str:
        return "".join(char if char.isalnum() or char in "._-" else "_" for char in value)
