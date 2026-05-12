"""Prompt utilities for exact cleanroom behavior contracts."""

from __future__ import annotations

import json

from core.data_models import BehaviorContract, ProgramSpec
from core.evidence.models import json_safe_value
from core.implementation.contract_assets import is_materializable_static_output_contract


def spec_prompt_json(spec: ProgramSpec) -> str:
    """Serialize the inferred spec without duplicating exact contracts."""
    return json.dumps(
        spec_prompt_dict(spec),
        indent=2,
        ensure_ascii=False,
    )


def spec_prompt_dict(spec: ProgramSpec) -> dict:
    """Return a JSON-ready spec dict without exact contracts."""
    return json_safe_value(spec.model_dump(exclude={"behavior_contracts"}))


def behavior_contract_prompt(spec: ProgramSpec) -> str:
    if not spec.behavior_contracts:
        return ""
    return _behavior_contract_prompt_from_contracts(spec.behavior_contracts)


def implementation_behavior_contract_prompt(spec: ProgramSpec) -> str:
    if not spec.behavior_contracts:
        return ""
    materialized = [
        contract
        for contract in spec.behavior_contracts
        if _is_materialized_implementation_contract(contract)
    ]
    regular = [
        contract
        for contract in spec.behavior_contracts
        if not _is_materialized_implementation_contract(contract)
    ]
    sections: list[str] = []
    if materialized:
        payload = [
            {
                "test_name": contract.test_name,
                "args": contract.args,
                "stdout_len": len(contract.stdout),
                "stderr_len": len(contract.stderr),
                "exit_code": contract.exit_code,
                "tags": contract.tags,
            }
            for contract in materialized
        ]
        sections.append(
            "Some exact long-output behavior contracts will be materialized as generated assets "
            "in rebuilder_contracts.py after code generation. Do not hand-copy or approximate "
            "their script bodies in the implementation; dispatch for these exact argv forms "
            "may use the generated asset:\n"
            f"{json.dumps(payload, indent=2, ensure_ascii=False)}\n\n"
        )
    sections.append(_behavior_contract_prompt_from_contracts(regular))
    return "".join(sections)


def _behavior_contract_prompt_from_contracts(
    contracts: list[BehaviorContract],
) -> str:
    if not contracts:
        return ""
    payload = [
        _contract_payload(contract)
        for contract in _select_contracts(contracts)
    ]
    return (
        "Exact behavior contracts from cleanroom exploration. "
        "Prioritize these over inferred summaries; stdout/stderr/exit_code "
        "must match exactly for the listed inputs:\n"
        f"{json.dumps(payload, indent=2, ensure_ascii=False)}\n\n"
    )


def _select_contracts(
    contracts: list[BehaviorContract],
    limit: int = 6,
) -> list[BehaviorContract]:
    indexed = list(enumerate(contracts))
    indexed.sort(key=lambda item: (*_contract_priority(item[1]), item[0]))
    return [contract for _, contract in indexed[:limit]]


def _contract_priority(contract: BehaviorContract) -> tuple[int, int]:
    name = contract.test_name.lower()
    args = set(contract.args)
    if name in {"help_long", "help_short"} or "--help" in args or "-h" in args:
        return (0, 0)
    if "version" in name or "--version" in args or "-v" in args or "-V" in args:
        return (1, 0)
    if "no_args" in name or not contract.args:
        return (2, 0)
    if _is_shell_init_contract(contract):
        return (3, 0)
    if _is_file_io_contract(contract):
        return (4, 0)
    if contract.exit_code != 0 or contract.stderr:
        return (5, 0)
    return (6, 0)


def _contract_payload(contract: BehaviorContract) -> dict:
    stdout_limit = 8000 if _is_shell_init_contract(contract) else 1200
    stderr_limit = 8000 if _is_shell_init_contract(contract) else 1200
    return {
        "test_name": contract.test_name,
        "args": contract.args,
        "stdin": _truncate_contract_stream(contract.stdin, limit=800),
        "stdout": _truncate_contract_stream(contract.stdout, limit=stdout_limit),
        "stderr": _truncate_contract_stream(contract.stderr, limit=stderr_limit),
        "exit_code": contract.exit_code,
        "output_files": contract.output_files,
        "output_file_previews": {
            name: _truncate_contract_stream(content, limit=2000)
            for name, content in sorted(contract.output_file_previews.items())
        },
        "tags": contract.tags,
    }


def _is_shell_init_contract(contract: BehaviorContract) -> bool:
    return (
        "shell_init" in contract.tags
        or contract.test_name.lower().startswith("shell_init_")
        or contract.args[:1] == ["init"]
    )


def _is_file_io_contract(contract: BehaviorContract) -> bool:
    return (
        "file_io" in contract.tags
        or bool(contract.output_files)
        or bool(contract.output_file_previews)
    )


def _is_materialized_implementation_contract(contract: BehaviorContract) -> bool:
    return is_materializable_static_output_contract(contract)


def _truncate_contract_stream(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit]}\n...[truncated]"
