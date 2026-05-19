import importlib
import json
import subprocess
import sys
from types import SimpleNamespace

import pytest


def load_module():
    try:
        return importlib.import_module("scripts.audit_strategy_domain_coverage")
    except ModuleNotFoundError:
        pytest.fail("scripts.audit_strategy_domain_coverage is not implemented yet")


def test_collect_strategy_domain_coverage_includes_every_profile_rule_domain():
    module = load_module()

    rows = module.collect_strategy_domain_coverage()

    assert len(rows) == 11
    assert {row.domain for row in rows} == {
        "archive_compression",
        "binary_hexdump",
        "csv_table",
        "filesystem_tool",
        "find_replace",
        "go_dependency_report",
        "html_selector",
        "json_transform",
        "network_ping",
        "terminal_animation",
        "terminal_ui",
    }
    assert all(row.generalization_playbook_count >= 3 for row in rows)
    assert all(row.validation_playbook_count >= 3 for row in rows)
    assert all(row.cleanroom_issue_count == 0 for row in rows)
    assert all(row.probe_count > 0 for row in rows)
    assert all(row.smoke_contract_axis_count > 0 for row in rows)
    assert all(row.adaptive_axis_count > 0 for row in rows)
    assert all(row.status == "ok" for row in rows)


def test_cleanroom_policy_rejects_eval_specific_strategy_text():
    module = load_module()
    rule = SimpleNamespace(
        keywords=("csv",),
        formats=("csv",),
        implementation_hints=("replay burntsushi__xsv.f430466 hidden test details",),
        repair_hints=(),
        implementation_playbook=(),
        repair_playbook=(),
        validation_playbook=(),
        generalization_playbook=(),
        anti_patterns=(),
    )

    issues = module.cleanroom_policy_issues(rule)

    assert issues
    assert "hidden test details" in issues[0]


def test_strategy_domain_coverage_cli_is_a_green_gate_for_current_rules():
    result = subprocess.run(
        [
            sys.executable,
            "scripts/audit_strategy_domain_coverage.py",
            "--fail-on-missing",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "strategy domain coverage" in result.stdout
    assert "validation items" in result.stdout
    assert "cleanroom issues" in result.stdout
    assert "terminal_animation" in result.stdout
    assert "filesystem_tool" in result.stdout
    assert "| ok |" in result.stdout


def test_strategy_domain_coverage_cli_outputs_machine_readable_json_without_banner():
    result = subprocess.run(
        [
            sys.executable,
            "scripts/audit_strategy_domain_coverage.py",
            "--fail-on-missing",
            "--limit",
            "3",
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.lstrip().startswith("{")
    assert "strategy domain coverage" not in result.stdout
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == 1
    assert payload["row_count"] == 3
    assert payload["total_row_count"] == 11
    assert payload["limit"] == 3
    assert [row["rank"] for row in payload["rows"]] == [1, 2, 3]
    first = payload["rows"][0]
    assert set(first) == {
        "rank",
        "domain",
        "generalization_playbook_count",
        "validation_playbook_count",
        "cleanroom_issue_count",
        "probe_count",
        "smoke_contract_axis_count",
        "adaptive_axis_count",
        "status",
    }
    assert first["status"] == "ok"
    assert "hidden test details" not in result.stdout
    assert "leaderboard" not in result.stdout
