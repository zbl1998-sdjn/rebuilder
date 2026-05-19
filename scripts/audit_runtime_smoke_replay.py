"""Audit whether historical candidates can replay local runtime smoke checks."""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.codebase.runtime_smoke import PythonRuntimeSmokeChecker  # noqa: E402
from core.data_models import BehaviorContract, Codebase  # noqa: E402
from core.evidence.models import EvidenceSource  # noqa: E402
from core.evidence.store import EvidenceStore  # noqa: E402
from core.submission.gate import (  # noqa: E402
    RUNTIME_SMOKE_DIMENSIONS,
    parse_runtime_smoke_dimensions,
    runtime_smoke_metadata,
)


@dataclass(frozen=True)
class RuntimeSmokeReplayRow:
    task_id: str | None
    result_path: Path
    status: str
    generated_file_count: int = 0
    entry_point: str | None = None
    evidence_path: Path | None = None
    evidence_contract_count: int = 0
    existing_runtime_smoke_status: str = ""
    existing_runtime_smoke_input_dimensions: tuple[str, ...] = ()
    planned_runtime_smoke_status: str = ""
    planned_runtime_smoke_input_dimensions: tuple[str, ...] = ()
    replay_runtime_smoke_status: str = ""
    replay_runtime_smoke_input_dimensions: tuple[str, ...] = ()
    required_runtime_smoke_dimensions: tuple[str, ...] = ()
    missing_required_dimensions: tuple[str, ...] = ()
    failed_issue_kind: str | None = None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audit historical result.json artifacts for local runtime-smoke replay "
            "readiness. The default mode is read-only and does not mutate result.json."
        )
    )
    parser.add_argument("--runs", default="runs", help="Root directory containing result.json files")
    parser.add_argument(
        "--task",
        dest="task_ids",
        action="append",
        default=None,
        help="Limit output to a specific task_id; may be repeated",
    )
    parser.add_argument("--limit", type=positive_int, default=50, help="Maximum rows to print")
    parser.add_argument(
        "--require-runtime-smoke-dimensions",
        type=parse_runtime_smoke_dimensions,
        default=(),
        help="Comma-separated runtime-smoke input dimensions required for readiness",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually execute local runtime-smoke checks against generated Python files",
    )
    parser.add_argument(
        "--status",
        dest="statuses",
        action="append",
        default=None,
        help="Limit output to a replay status; may be repeated",
    )
    parser.add_argument(
        "--failed-issue-kind",
        "--replay-failed-issue-kind",
        dest="failed_issue_kinds",
        action="append",
        default=None,
        help="Limit output to a runtime-smoke failed_issue_kind; may be repeated",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format. JSON emits aggregate-only replay rows.",
    )
    return parser.parse_args(argv)


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def audit_runtime_smoke_replay(
    runs_root: Path | str,
    *,
    required_runtime_smoke_dimensions: str | tuple[str, ...] | list[str] = (),
    execute: bool = False,
    task_ids: tuple[str, ...] | list[str] | None = None,
    statuses: tuple[str, ...] | list[str] | None = None,
    failed_issue_kinds: tuple[str, ...] | list[str] | None = None,
) -> list[RuntimeSmokeReplayRow]:
    required_dimensions = parse_runtime_smoke_dimensions(required_runtime_smoke_dimensions)
    selected_tasks = set(task_ids or ())
    rows = [
        audit_result_for_runtime_smoke_replay(
            result_path,
            required_runtime_smoke_dimensions=required_dimensions,
            execute=execute,
        )
        for result_path in sorted(Path(runs_root).rglob("result.json"))
    ]
    if selected_tasks:
        rows = [row for row in rows if row.task_id in selected_tasks]
    selected_statuses = set(statuses or ())
    if selected_statuses:
        rows = [row for row in rows if row.status in selected_statuses]
    selected_issue_kinds = set(failed_issue_kinds or ())
    if selected_issue_kinds:
        rows = [row for row in rows if row.failed_issue_kind in selected_issue_kinds]
    return sorted(rows, key=replay_row_sort_key)


def audit_result_for_runtime_smoke_replay(
    result_path: Path,
    *,
    required_runtime_smoke_dimensions: tuple[str, ...],
    execute: bool,
) -> RuntimeSmokeReplayRow:
    payload = load_result_payload(result_path)
    if not isinstance(payload, dict):
        return RuntimeSmokeReplayRow(
            task_id=None,
            result_path=result_path,
            status="invalid_result",
            required_runtime_smoke_dimensions=required_runtime_smoke_dimensions,
            missing_required_dimensions=required_runtime_smoke_dimensions,
        )

    task_id = payload.get("task_id")
    if not isinstance(task_id, str):
        task_id = None
    existing_status, existing_dimensions = runtime_smoke_metadata(payload)
    existing_missing = missing_dimensions(required_runtime_smoke_dimensions, existing_dimensions)
    if existing_status and not execute:
        status = "already_recorded" if existing_status == "passed" and not existing_missing else "existing_incomplete"
        return RuntimeSmokeReplayRow(
            task_id=task_id,
            result_path=result_path,
            status=status,
            existing_runtime_smoke_status=existing_status,
            existing_runtime_smoke_input_dimensions=existing_dimensions,
            required_runtime_smoke_dimensions=required_runtime_smoke_dimensions,
            missing_required_dimensions=existing_missing,
        )

    files = load_generated_files(result_path.parent)
    entry_point = entry_point_from_payload(payload, files)
    if not files:
        return base_artifact_row(
            payload,
            result_path,
            "missing_generated_code",
            required_runtime_smoke_dimensions=required_runtime_smoke_dimensions,
            existing_status=existing_status,
            existing_dimensions=existing_dimensions,
        )
    if entry_point is None:
        return base_artifact_row(
            payload,
            result_path,
            "missing_entrypoint",
            generated_file_count=len(files),
            required_runtime_smoke_dimensions=required_runtime_smoke_dimensions,
            existing_status=existing_status,
            existing_dimensions=existing_dimensions,
        )

    evidence_path = find_evidence_path(result_path)
    contracts = load_evidence_contracts(evidence_path) if evidence_path else []
    checker = PythonRuntimeSmokeChecker()
    planned_metadata = checker.plan_metadata(contracts)
    planned_dimensions = runtime_dimensions_from_metadata(planned_metadata)
    planned_missing = missing_dimensions(required_runtime_smoke_dimensions, planned_dimensions)
    if planned_missing:
        return RuntimeSmokeReplayRow(
            task_id=task_id,
            result_path=result_path,
            status="insufficient_contract_artifacts",
            generated_file_count=len(files),
            entry_point=entry_point,
            evidence_path=evidence_path,
            evidence_contract_count=len(contracts),
            existing_runtime_smoke_status=existing_status,
            existing_runtime_smoke_input_dimensions=existing_dimensions,
            planned_runtime_smoke_status=str(planned_metadata.get("status") or ""),
            planned_runtime_smoke_input_dimensions=planned_dimensions,
            required_runtime_smoke_dimensions=required_runtime_smoke_dimensions,
            missing_required_dimensions=planned_missing,
        )

    if not execute:
        return RuntimeSmokeReplayRow(
            task_id=task_id,
            result_path=result_path,
            status="ready_for_replay",
            generated_file_count=len(files),
            entry_point=entry_point,
            evidence_path=evidence_path,
            evidence_contract_count=len(contracts),
            existing_runtime_smoke_status=existing_status,
            existing_runtime_smoke_input_dimensions=existing_dimensions,
            planned_runtime_smoke_status=str(planned_metadata.get("status") or ""),
            planned_runtime_smoke_input_dimensions=planned_dimensions,
            required_runtime_smoke_dimensions=required_runtime_smoke_dimensions,
        )

    report = asyncio.run(
        checker.check(
            Codebase(root_path=result_path.parent, language="python", files=files),
            entry_point=entry_point,
            behavior_contracts=contracts,
        )
    )
    replay_dimensions = runtime_dimensions_from_metadata(report.metadata)
    replay_missing = missing_dimensions(required_runtime_smoke_dimensions, replay_dimensions)
    replay_status = str(report.metadata.get("status") or "")
    issue_kind = failed_issue_kind(report.metadata)
    status = replay_status_from_report(replay_status, replay_missing, issue_kind)
    return RuntimeSmokeReplayRow(
        task_id=task_id,
        result_path=result_path,
        status=status,
        generated_file_count=len(files),
        entry_point=entry_point,
        evidence_path=evidence_path,
        evidence_contract_count=len(contracts),
        existing_runtime_smoke_status=existing_status,
        existing_runtime_smoke_input_dimensions=existing_dimensions,
        planned_runtime_smoke_status=str(planned_metadata.get("status") or ""),
        planned_runtime_smoke_input_dimensions=planned_dimensions,
        replay_runtime_smoke_status=replay_status,
        replay_runtime_smoke_input_dimensions=replay_dimensions,
        required_runtime_smoke_dimensions=required_runtime_smoke_dimensions,
        missing_required_dimensions=replay_missing,
        failed_issue_kind=issue_kind,
    )


def load_result_payload(result_path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def load_generated_files(generated_root: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in sorted(generated_root.rglob("*")):
        if not path.is_file():
            continue
        if path.name == "result.json" or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        files[path.relative_to(generated_root).as_posix()] = text
    return files


def entry_point_from_payload(payload: dict[str, Any], files: dict[str, str]) -> str | None:
    metadata = payload.get("implementation_metadata")
    if isinstance(metadata, dict):
        entrypoint_files = metadata.get("entrypoint_stage_files")
        if isinstance(entrypoint_files, list):
            for item in entrypoint_files:
                if isinstance(item, str):
                    normalized = normalize_entrypoint(item)
                    if normalized in files:
                        return normalized
    if "main.py" in files:
        return "main.py"
    python_files = sorted(path for path in files if path.endswith(".py"))
    return python_files[0] if python_files else None


def normalize_entrypoint(value: str) -> str:
    normalized = value.replace("\\", "/")
    return normalized if normalized.endswith(".py") else f"{normalized}.py"


def find_evidence_path(result_path: Path) -> Path | None:
    for parent in result_path.parents:
        candidate = parent / "evidence"
        if (candidate / "index.json").exists():
            return candidate
    return None


def load_evidence_contracts(evidence_path: Path | None) -> list[BehaviorContract]:
    if evidence_path is None:
        return []
    records = EvidenceStore(evidence_path).list_records()
    contracts: list[BehaviorContract] = []
    for record in records:
        if record.source != EvidenceSource.REFERENCE_EXECUTABLE:
            continue
        contracts.append(
            BehaviorContract(
                test_name=record.test_case.name,
                args=list(record.test_case.args),
                stdin=record.test_case.stdin,
                input_files=dict(record.test_case.input_files),
                env_vars=dict(record.test_case.env_vars),
                stdout=record.result.stdout,
                stderr=record.result.stderr,
                exit_code=record.result.exit_code,
                output_files=sorted(record.result.output_files),
                tags=list(record.tags),
            )
        )
    return contracts


def runtime_dimensions_from_metadata(metadata: dict[str, object]) -> tuple[str, ...]:
    if not isinstance(metadata, dict):
        return ()
    value = metadata.get("input_dimensions")
    raw_dimensions: list[str] = []
    if isinstance(value, str):
        raw_dimensions.extend(part.strip() for part in value.split(","))
    elif isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, str):
                raw_dimensions.extend(part.strip() for part in item.split(","))
    allowed = set(RUNTIME_SMOKE_DIMENSIONS)
    seen = set()
    dimensions = []
    for dimension in raw_dimensions:
        if dimension in allowed and dimension not in seen:
            seen.add(dimension)
            dimensions.append(dimension)
    return tuple(dimensions)


def missing_dimensions(required: tuple[str, ...], available: tuple[str, ...]) -> tuple[str, ...]:
    available_set = set(available)
    return tuple(dimension for dimension in required if dimension not in available_set)


def failed_issue_kind(metadata: dict[str, object]) -> str | None:
    value = metadata.get("failed_issue_kind")
    return value if isinstance(value, str) else None


def replay_status_from_report(
    replay_status: str,
    replay_missing: tuple[str, ...],
    issue_kind: str | None,
) -> str:
    if replay_status == "passed" and not replay_missing:
        return "replay_passed"
    if issue_kind == "runtime_smoke_executor_permission_denied":
        return "replay_environment_blocked"
    return "replay_failed"


def base_artifact_row(
    payload: dict[str, Any],
    result_path: Path,
    status: str,
    *,
    generated_file_count: int = 0,
    required_runtime_smoke_dimensions: tuple[str, ...],
    existing_status: str,
    existing_dimensions: tuple[str, ...],
) -> RuntimeSmokeReplayRow:
    task_id = payload.get("task_id")
    return RuntimeSmokeReplayRow(
        task_id=task_id if isinstance(task_id, str) else None,
        result_path=result_path,
        status=status,
        generated_file_count=generated_file_count,
        existing_runtime_smoke_status=existing_status,
        existing_runtime_smoke_input_dimensions=existing_dimensions,
        required_runtime_smoke_dimensions=required_runtime_smoke_dimensions,
        missing_required_dimensions=required_runtime_smoke_dimensions,
    )


def replay_row_sort_key(row: RuntimeSmokeReplayRow) -> tuple[int, str, str]:
    status_order = {
        "insufficient_contract_artifacts": 0,
        "missing_entrypoint": 1,
        "missing_generated_code": 2,
        "existing_incomplete": 3,
        "replay_failed": 4,
        "replay_environment_blocked": 5,
        "ready_for_replay": 6,
        "already_recorded": 7,
        "replay_passed": 8,
        "invalid_result": 9,
    }
    return (status_order.get(row.status, 99), row.task_id or "", str(row.result_path))


def replay_json_row(row: RuntimeSmokeReplayRow, rank: int) -> dict[str, object]:
    return {
        "rank": rank,
        "task_id": row.task_id,
        "status": row.status,
        "generated_file_count": row.generated_file_count,
        "entry_point": row.entry_point,
        "evidence_contract_count": row.evidence_contract_count,
        "existing_runtime_smoke_status": row.existing_runtime_smoke_status,
        "existing_runtime_smoke_input_dimensions": list(row.existing_runtime_smoke_input_dimensions),
        "planned_runtime_smoke_status": row.planned_runtime_smoke_status,
        "planned_runtime_smoke_input_dimensions": list(row.planned_runtime_smoke_input_dimensions),
        "replay_runtime_smoke_status": row.replay_runtime_smoke_status,
        "replay_runtime_smoke_input_dimensions": list(row.replay_runtime_smoke_input_dimensions),
        "required_runtime_smoke_dimensions": list(row.required_runtime_smoke_dimensions),
        "missing_required_dimensions": list(row.missing_required_dimensions),
        "failed_issue_kind": row.failed_issue_kind,
        "result_path": str(row.result_path),
        "evidence_path": str(row.evidence_path) if row.evidence_path else None,
    }


def replay_json_payload(rows: list[RuntimeSmokeReplayRow], limit: int) -> dict[str, object]:
    selected = rows[: max(0, limit)]
    return {
        "schema_version": 1,
        "row_count": len(selected),
        "total_row_count": len(rows),
        "limit": limit,
        "status_counts": count_values(row.status for row in rows),
        "failed_issue_kind_counts": count_values(
            row.failed_issue_kind for row in rows if row.failed_issue_kind
        ),
        "rows": [replay_json_row(row, rank) for rank, row in enumerate(selected, start=1)],
    }


def count_values(values) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def write_json(rows: list[RuntimeSmokeReplayRow], limit: int) -> None:
    print(json.dumps(replay_json_payload(rows, limit), indent=2, ensure_ascii=False))


def write_markdown(rows: list[RuntimeSmokeReplayRow], limit: int) -> None:
    selected = rows[: max(0, limit)]
    print(
        "| rank | task | status | planned dimensions | replay dimensions | "
        "missing required | evidence contracts | result |"
    )
    print("| ---: | --- | --- | --- | --- | --- | ---: | --- |")
    for rank, row in enumerate(selected, start=1):
        print(
            f"| {rank} | {row.task_id or '-'} | {row.status} | "
            f"{format_dimensions(row.planned_runtime_smoke_input_dimensions)} | "
            f"{format_dimensions(row.replay_runtime_smoke_input_dimensions)} | "
            f"{format_dimensions(row.missing_required_dimensions)} | "
            f"{row.evidence_contract_count} | {row.result_path} |"
        )


def format_dimensions(dimensions: tuple[str, ...]) -> str:
    return ",".join(dimensions) if dimensions else "-"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    rows = audit_runtime_smoke_replay(
        args.runs,
        required_runtime_smoke_dimensions=args.require_runtime_smoke_dimensions,
        execute=args.execute,
        task_ids=args.task_ids,
        statuses=args.statuses,
        failed_issue_kinds=args.failed_issue_kinds,
    )
    write = write_json if args.format == "json" else write_markdown
    write(rows, args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
