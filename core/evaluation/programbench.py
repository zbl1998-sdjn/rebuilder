"""Parse official ProgramBench evaluation JSON summaries."""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROGRAMBENCH_REPO = ROOT / "runs" / "official_breakthrough_loop" / "programbench_repo_gh"


class ProgramBenchEvalSummary(BaseModel):
    total_tests: int = 0
    passed_tests: int = 0
    pass_rate: float = 0.0
    score: float = 0.0
    fully_resolved: bool = False
    almost_resolved: bool = False
    error_code: str | None = None
    error_details: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ProgramBenchEvalParser:
    """Summarize ProgramBench eval JSON without feeding it into repair."""

    def parse(
        self,
        path: Path | str,
        *,
        instance_id: str | None = None,
        programbench_repo: Path | str | None = None,
    ) -> ProgramBenchEvalSummary:
        eval_path = Path(path)
        payload = self._load_eval_payload(eval_path)
        if instance_id:
            filtered = self._filtered_summary(
                payload,
                instance_id=instance_id,
                programbench_repo=Path(programbench_repo) if programbench_repo else DEFAULT_PROGRAMBENCH_REPO,
            )
            if filtered is not None:
                return filtered
        return self.from_payload(payload)

    def _load_eval_payload(self, path: Path) -> dict:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"test_results": [], "error_code": "invalid_eval_payload"}
        if not isinstance(payload, dict):
            return {"test_results": [], "error_code": "invalid_eval_payload"}
        return payload

    def from_payload(self, payload: dict) -> ProgramBenchEvalSummary:
        results = payload.get("test_results") or []
        if not isinstance(results, list):
            results = []
        total = len(results)
        passed = sum(1 for item in results if isinstance(item, dict) and item.get("status") == "passed")
        pass_rate = passed / total if total else 0.0
        return ProgramBenchEvalSummary(
            total_tests=total,
            passed_tests=passed,
            pass_rate=pass_rate,
            score=pass_rate,
            fully_resolved=total > 0 and passed == total,
            almost_resolved=pass_rate >= 0.95 if total else False,
            error_code=payload.get("error_code"),
            error_details=payload.get("error_details"),
            warnings=self._warnings(payload),
        )

    def _filtered_summary(
        self,
        payload: dict,
        *,
        instance_id: str,
        programbench_repo: Path,
    ) -> ProgramBenchEvalSummary | None:
        tests_path = programbench_repo / "src" / "programbench" / "data" / "tasks" / instance_id / "tests.json"
        if not tests_path.exists():
            return None
        try:
            tests_payload = self._load_json_lenient(tests_path)
        except Exception:
            return None
        branches = tests_payload.get("branches") or {}
        if not isinstance(branches, dict):
            return None
        active_branches = {
            name
            for name, info in branches.items()
            if isinstance(info, dict) and not info.get("ignored")
        }
        if not active_branches:
            return None
        ignored_tests = {
            f"{branch}/{item['name']}"
            for branch, info in branches.items()
            if isinstance(info, dict)
            for item in (info.get("ignored_tests") or [])
            if isinstance(item, dict) and item.get("name")
        }
        raw_results = payload.get("test_results") or []
        if not isinstance(raw_results, list):
            raw_results = []
        filtered_results = [
            item
            for item in raw_results
            if isinstance(item, dict)
            and item.get("branch") in active_branches
            and f"{item.get('branch')}/{item.get('name')}" not in ignored_tests
        ]
        test_branches = payload.get("test_branches") or []
        if not isinstance(test_branches, list):
            test_branches = []
        ignored_branches = {branch for branch in test_branches if branch not in active_branches}
        warnings = self._warnings(payload)
        if ignored_branches:
            warnings = [w for w in warnings if not any(f"branch {branch}" in w for branch in ignored_branches)]

        total = len(filtered_results)
        passed = sum(1 for item in filtered_results if item.get("status") == "passed")
        score = passed / total if total else 0.0
        return ProgramBenchEvalSummary(
            total_tests=total,
            passed_tests=passed,
            pass_rate=score,
            score=score,
            fully_resolved=total > 0 and passed == total,
            almost_resolved=score >= 0.95 if total else False,
            error_code=payload.get("error_code"),
            error_details=payload.get("error_details"),
            warnings=warnings,
        )

    def _warnings(self, payload: dict) -> list[str]:
        warnings = payload.get("warnings") or []
        if not isinstance(warnings, list):
            return []
        return [warning for warning in warnings if isinstance(warning, str)]

    def _load_json_lenient(self, path: Path) -> dict:
        text = path.read_text(encoding="utf-8")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            normalized = re.sub(r",(\s*[}\]])", r"\1", text)
            return json.loads(normalized)
