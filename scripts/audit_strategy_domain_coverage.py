"""Audit task-domain strategy pack coverage against adaptive smoke probes."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.probing.adaptive import AdaptiveProbePlanner  # noqa: E402
from core.profiling.task_profile import _load_profile_rules  # noqa: E402


AXIS_PATTERN = re.compile(r"\b(?P<kind>smoke_contract|adaptive_axis):(?P<domain>[a-z0-9_]+)\.(?P<axis>[a-z0-9_]+)")
TASK_ID_PATTERN = re.compile(r"\b[a-z0-9][a-z0-9-]*__[a-z0-9][a-z0-9-]*\.[a-f0-9]{7}\b")
FORBIDDEN_CLEANROOM_PATTERNS = (
    re.compile(r"\bofficial\b", re.IGNORECASE),
    re.compile(r"\bhidden\s+(failure|failures|test|tests|case|cases|detail|details)\b", re.IGNORECASE),
    re.compile(r"\btest[- ]?set\b", re.IGNORECASE),
    re.compile(r"\bleaderboard\b", re.IGNORECASE),
    re.compile(r"\beval\s+score\b", re.IGNORECASE),
    TASK_ID_PATTERN,
)


@dataclass(frozen=True)
class StrategyDomainCoverage:
    domain: str
    generalization_playbook_count: int
    validation_playbook_count: int
    cleanroom_issue_count: int
    probe_count: int
    smoke_contract_axis_count: int
    adaptive_axis_count: int
    status: str


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit strategy domain coverage for profile rules and adaptive probes"
    )
    parser.add_argument("--limit", type=int, default=50, help="Maximum rows to print")
    parser.add_argument(
        "--fail-on-missing",
        action="store_true",
        help="Exit non-zero when a domain lacks generalization guidance or adaptive smoke axes",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format. JSON emits aggregate-only domain coverage rows for automation.",
    )
    return parser.parse_args(argv)


def collect_strategy_domain_coverage() -> list[StrategyDomainCoverage]:
    planner = AdaptiveProbePlanner()
    rows = []
    for rule in _load_profile_rules():
        probes = planner.plan({"primary_domain": rule.domain})
        smoke_axes, adaptive_axes = probe_axes(rule.domain, probes)
        cleanroom_issues = cleanroom_policy_issues(rule)
        rows.append(
            StrategyDomainCoverage(
                domain=rule.domain,
                generalization_playbook_count=len(rule.generalization_playbook),
                validation_playbook_count=len(rule.validation_playbook),
                cleanroom_issue_count=len(cleanroom_issues),
                probe_count=len(probes),
                smoke_contract_axis_count=len(smoke_axes),
                adaptive_axis_count=len(adaptive_axes),
                status=coverage_status(
                    generalization_count=len(rule.generalization_playbook),
                    validation_count=len(rule.validation_playbook),
                    cleanroom_issue_count=len(cleanroom_issues),
                    probe_count=len(probes),
                    smoke_axis_count=len(smoke_axes),
                    adaptive_axis_count=len(adaptive_axes),
                ),
            )
        )
    return sorted(rows, key=lambda row: row.domain)


def probe_axes(domain: str, probes) -> tuple[set[str], set[str]]:
    smoke_axes: set[str] = set()
    adaptive_axes: set[str] = set()
    for probe in probes:
        for match in AXIS_PATTERN.finditer(probe.description):
            if match.group("domain") != domain:
                continue
            axis = match.group("axis")
            if match.group("kind") == "smoke_contract":
                smoke_axes.add(axis)
            else:
                adaptive_axes.add(axis)
    return smoke_axes, adaptive_axes


def cleanroom_policy_issues(rule) -> list[str]:
    issues = []
    for field_name, item in rule_text_items(rule):
        for pattern in FORBIDDEN_CLEANROOM_PATTERNS:
            if pattern.search(item):
                issues.append(f"{field_name}: {item}")
                break
    return issues


def rule_text_items(rule) -> list[tuple[str, str]]:
    fields = (
        "keywords",
        "formats",
        "implementation_hints",
        "repair_hints",
        "implementation_playbook",
        "repair_playbook",
        "validation_playbook",
        "generalization_playbook",
        "anti_patterns",
    )
    return [
        (field, str(item))
        for field in fields
        for item in getattr(rule, field, ())
    ]


def coverage_status(
    *,
    generalization_count: int,
    validation_count: int,
    cleanroom_issue_count: int,
    probe_count: int,
    smoke_axis_count: int,
    adaptive_axis_count: int,
) -> str:
    missing = []
    if generalization_count <= 0:
        missing.append("generalization_playbook")
    if validation_count <= 0:
        missing.append("validation_playbook")
    if cleanroom_issue_count > 0:
        missing.append("cleanroom_policy")
    if probe_count <= 0:
        missing.append("adaptive_probes")
    if smoke_axis_count <= 0:
        missing.append("smoke_contract_axes")
    if adaptive_axis_count <= 0:
        missing.append("adaptive_axes")
    return "ok" if not missing else "missing_" + ",".join(missing)


def write_markdown(rows: list[StrategyDomainCoverage], limit: int) -> None:
    selected = rows[: max(0, limit)]
    print("| rank | domain | generalization items | validation items | cleanroom issues | probes | smoke axes | adaptive axes | status |")
    print("| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |")
    for index, row in enumerate(selected, start=1):
        print(
            f"| {index} | {row.domain} | {row.generalization_playbook_count} | "
            f"{row.validation_playbook_count} | {row.cleanroom_issue_count} | "
            f"{row.probe_count} | {row.smoke_contract_axis_count} | "
            f"{row.adaptive_axis_count} | {row.status} |"
        )


def coverage_json_row(row: StrategyDomainCoverage, rank: int) -> dict[str, object]:
    return {
        "rank": rank,
        "domain": row.domain,
        "generalization_playbook_count": row.generalization_playbook_count,
        "validation_playbook_count": row.validation_playbook_count,
        "cleanroom_issue_count": row.cleanroom_issue_count,
        "probe_count": row.probe_count,
        "smoke_contract_axis_count": row.smoke_contract_axis_count,
        "adaptive_axis_count": row.adaptive_axis_count,
        "status": row.status,
    }


def coverage_json_payload(rows: list[StrategyDomainCoverage], limit: int) -> dict[str, object]:
    selected = rows[: max(0, limit)]
    return {
        "schema_version": 1,
        "row_count": len(selected),
        "total_row_count": len(rows),
        "limit": limit,
        "rows": [coverage_json_row(row, rank) for rank, row in enumerate(selected, start=1)],
    }


def write_json(rows: list[StrategyDomainCoverage], limit: int) -> None:
    print(json.dumps(coverage_json_payload(rows, limit), indent=2, ensure_ascii=False))


def should_fail(rows: list[StrategyDomainCoverage], fail_on_missing: bool) -> bool:
    return fail_on_missing and any(row.status != "ok" for row in rows)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    rows = collect_strategy_domain_coverage()
    if args.format == "json":
        write_json(rows, args.limit)
    else:
        print("strategy domain coverage")
        write_markdown(rows, args.limit)
    return 2 if should_fail(rows[: max(0, args.limit)], args.fail_on_missing) else 0


if __name__ == "__main__":
    raise SystemExit(main())
