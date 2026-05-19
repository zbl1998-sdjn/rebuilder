"""Prompt utilities for exact cleanroom behavior contracts."""

from __future__ import annotations

import json

from core.data_models import BehaviorContract, ProgramSpec, TaskProfile
from core.evidence.models import json_safe_value
from core.implementation.contract_assets import is_materializable_static_output_contract


TASK_PROFILE_PROMPT_PAYLOAD_LIMIT = 6000
TASK_PROFILE_COMPACT_TEXT_LIMIT = 140
TASK_PROFILE_COMPACT_DOMAIN_LIMIT = 8
TASK_PROFILE_COMPACT_HINT_LIMIT = 4
TASK_PROFILE_COMPACT_PLAYBOOK_LIMIT = 12
TASK_PROFILE_COMPACT_VALIDATION_LIMIT = 6
TASK_PROFILE_COMPACT_GENERALIZATION_LIMIT = 6
TASK_PROFILE_COMPACT_ANTI_PATTERN_LIMIT = 4
TASK_PROFILE_COMPACT_KEYWORD_LIMIT = 12
SPEC_PROMPT_RAW_OBSERVATIONS_LIMIT = 2500
SPEC_PROMPT_TEXT_FIELD_LIMIT = 800
SPEC_PROMPT_LIST_LIMIT = 8
SPEC_PROMPT_LIST_TEXT_LIMIT = 240
SPEC_PROMPT_MAPPING_LIMIT = 12


def spec_prompt_json(spec: ProgramSpec) -> str:
    """Serialize the inferred spec without duplicating exact contracts."""
    return json.dumps(
        spec_prompt_dict(spec),
        indent=2,
        ensure_ascii=False,
    )


def spec_prompt_dict(spec: ProgramSpec) -> dict:
    """Return a JSON-ready spec dict without exact contracts."""
    payload = spec.model_dump(exclude={"behavior_contracts", "task_profile"})
    complexity_hints = payload.get("complexity_hints")
    if isinstance(complexity_hints, dict) and "task_profile" in complexity_hints:
        compact_hints = dict(complexity_hints)
        compact_hints.pop("task_profile", None)
        payload["complexity_hints"] = compact_hints
    return _compact_spec_prompt_payload(json_safe_value(payload))


def _compact_spec_prompt_payload(payload: dict) -> dict:
    compact = dict(payload)
    raw_observations = compact.get("raw_observations")
    if isinstance(raw_observations, str):
        compact["raw_observations"] = _truncate_prompt_text(
            raw_observations,
            SPEC_PROMPT_RAW_OBSERVATIONS_LIMIT,
        )
    for field in ("summary", "behavior_graph"):
        value = compact.get(field)
        if isinstance(value, str):
            compact[field] = _truncate_prompt_text(value, SPEC_PROMPT_TEXT_FIELD_LIMIT)
    for field in ("input_formats", "output_formats", "edge_cases"):
        value = compact.get(field)
        if isinstance(value, list):
            compact[field] = _compact_prompt_list(value)
    complexity_hints = compact.get("complexity_hints")
    if isinstance(complexity_hints, dict):
        compact["complexity_hints"] = _compact_prompt_mapping(complexity_hints)
    invariants = compact.get("invariants")
    if isinstance(invariants, list):
        compact["invariants"] = _compact_prompt_list(invariants)
    return compact


def _compact_prompt_mapping(value: dict) -> dict:
    compact: dict = {}
    items = list(value.items())
    for key, item in items[:SPEC_PROMPT_MAPPING_LIMIT]:
        compact[key] = _compact_prompt_value(item)
    if len(items) > SPEC_PROMPT_MAPPING_LIMIT:
        compact["__truncated_keys__"] = len(items) - SPEC_PROMPT_MAPPING_LIMIT
    return compact


def _compact_prompt_list(value: list) -> list:
    compact = [
        _compact_prompt_value(item)
        for item in value[:SPEC_PROMPT_LIST_LIMIT]
    ]
    if len(value) > SPEC_PROMPT_LIST_LIMIT:
        compact.append({"__truncated__": len(value) - SPEC_PROMPT_LIST_LIMIT})
    return compact


def _compact_prompt_value(value):
    if isinstance(value, str):
        return _truncate_prompt_text(value, SPEC_PROMPT_LIST_TEXT_LIMIT)
    if isinstance(value, dict):
        return _compact_prompt_mapping(value)
    if isinstance(value, list):
        return _compact_prompt_list(value)
    return value


def _truncate_prompt_text(value: str, limit: int) -> str:
    if limit <= 0:
        return "...[truncated for spec prompt]"
    if len(value) <= limit:
        return value
    marker = "\n...[truncated for spec prompt]...\n"
    if limit <= len(marker):
        return marker[:limit]
    head = max(1, (limit - len(marker)) // 2)
    tail = max(1, limit - len(marker) - head)
    return value[:head].rstrip() + marker + value[-tail:].lstrip()


def task_profile_prompt(spec: ProgramSpec, *, purpose: str = "implementation") -> str:
    profile = _task_profile_payload(spec)
    if not isinstance(profile, dict):
        return ""
    payload = _task_profile_prompt_payload(profile, purpose=purpose, compact=False)
    if _payload_size(payload) > TASK_PROFILE_PROMPT_PAYLOAD_LIMIT:
        payload = _task_profile_prompt_payload(profile, purpose=purpose, compact=True)
        payload["profile_prompt_budget"] = {
            "max_payload_chars": TASK_PROFILE_PROMPT_PAYLOAD_LIMIT,
            "__truncated__": True,
        }
    return (
        "Task strategy profile inferred from cleanroom docs and probes. "
        "Use it as domain guidance, but never override exact observed contracts:\n"
        f"{json.dumps(payload, indent=2, ensure_ascii=False)}\n\n"
    )


def _task_profile_prompt_payload(
    profile: dict,
    *,
    purpose: str,
    compact: bool,
) -> dict:
    hints_key = "repair_hints" if purpose == "repair" else "implementation_hints"
    if not compact:
        return {
            "primary_domain": profile.get("primary_domain", "generic_cli"),
            "domains": profile.get("domains", ["generic_cli"]),
            "confidence": profile.get("confidence", "fallback"),
            "input_format_hints": profile.get("input_format_hints", []),
            hints_key: profile.get(hints_key, []),
            "strategy_pack": _task_strategy_pack(profile, purpose=purpose),
            "evidence_keywords": profile.get("evidence_keywords", []),
        }
    return {
        "primary_domain": profile.get("primary_domain", "generic_cli"),
        "domains": _compact_profile_list(
            profile.get("domains", ["generic_cli"]),
            limit=TASK_PROFILE_COMPACT_DOMAIN_LIMIT,
        ),
        "confidence": profile.get("confidence", "fallback"),
        "input_format_hints": _compact_profile_list(
            profile.get("input_format_hints", []),
            limit=TASK_PROFILE_COMPACT_HINT_LIMIT,
        ),
        hints_key: _compact_profile_list(
            profile.get(hints_key, []),
            limit=TASK_PROFILE_COMPACT_HINT_LIMIT,
        ),
        "strategy_pack": _task_strategy_pack(profile, purpose=purpose, compact=True),
        "evidence_keywords": _compact_profile_list(
            profile.get("evidence_keywords", []),
            limit=TASK_PROFILE_COMPACT_KEYWORD_LIMIT,
        ),
    }


def _payload_size(payload: dict) -> int:
    return len(json.dumps(payload, ensure_ascii=False))


def _task_profile_payload(spec: ProgramSpec) -> dict | None:
    if spec.task_profile is not None:
        return spec.task_profile.model_dump()
    profile = spec.complexity_hints.get("task_profile")
    if isinstance(profile, TaskProfile):
        return profile.model_dump()
    if isinstance(profile, dict):
        return profile
    return None


def _task_strategy_pack(profile: dict, *, purpose: str, compact: bool = False) -> dict:
    pack = profile.get("strategy_pack")
    if not isinstance(pack, dict):
        return {}
    playbook_key = "repair_playbook" if purpose == "repair" else "implementation_playbook"
    if not compact:
        return {
            "domain": pack.get("domain", profile.get("primary_domain", "generic_cli")),
            playbook_key: pack.get(playbook_key, []),
            "validation_playbook": pack.get("validation_playbook", []),
            "generalization_playbook": pack.get("generalization_playbook", []),
            "anti_patterns": pack.get("anti_patterns", []),
        }
    return {
        "domain": pack.get("domain", profile.get("primary_domain", "generic_cli")),
        playbook_key: _compact_profile_list(
            pack.get(playbook_key, []),
            limit=TASK_PROFILE_COMPACT_PLAYBOOK_LIMIT,
        ),
        "validation_playbook": _compact_profile_list(
            pack.get("validation_playbook", []),
            limit=TASK_PROFILE_COMPACT_VALIDATION_LIMIT,
        ),
        "generalization_playbook": _compact_profile_list(
            pack.get("generalization_playbook", []),
            limit=TASK_PROFILE_COMPACT_GENERALIZATION_LIMIT,
        ),
        "anti_patterns": _compact_profile_list(
            pack.get("anti_patterns", []),
            limit=TASK_PROFILE_COMPACT_ANTI_PATTERN_LIMIT,
        ),
    }


def _compact_profile_list(value, *, limit: int) -> list:
    if not isinstance(value, list):
        value = [] if value is None else [value]
    compacted = [_compact_profile_value(item) for item in value[:limit]]
    if len(value) > limit:
        compacted.append({"__truncated__": len(value) - limit})
    return compacted


def _compact_profile_value(value):
    if isinstance(value, str):
        return _compact_profile_text(value)
    return value


def _compact_profile_text(value: str) -> str:
    if len(value) <= TASK_PROFILE_COMPACT_TEXT_LIMIT:
        return value
    marker = "... __truncated__"
    keep = max(1, TASK_PROFILE_COMPACT_TEXT_LIMIT - len(marker))
    return value[:keep].rstrip() + marker


def behavior_contract_prompt(spec: ProgramSpec) -> str:
    if not spec.behavior_contracts:
        return ""
    return _behavior_contract_prompt_from_contracts(
        spec.behavior_contracts,
        profile=_task_profile_payload(spec),
    )


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
    sections.append(
        _behavior_contract_prompt_from_contracts(
            regular,
            profile=_task_profile_payload(spec),
        )
    )
    return "".join(sections)


def _behavior_contract_prompt_from_contracts(
    contracts: list[BehaviorContract],
    *,
    profile: dict | None = None,
) -> str:
    if not contracts:
        return ""
    payload = [
        _contract_payload(contract)
        for contract in _select_contracts(contracts, profile=profile)
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
    *,
    profile: dict | None = None,
) -> list[BehaviorContract]:
    indexed = list(enumerate(contracts))
    profile_domains = _profile_domains(profile)
    indexed.sort(key=lambda item: (*_contract_priority(item[1], profile_domains), item[0]))
    return [contract for _, contract in indexed[:limit]]


def _contract_priority(contract: BehaviorContract, profile_domains: set[str] | None = None) -> tuple[int, int]:
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
    network_ping_rank = _network_ping_contract_rank(contract, profile_domains or set())
    if network_ping_rank is not None:
        return (4, network_ping_rank)
    if _is_file_io_contract(contract):
        return (5, 0)
    if contract.exit_code != 0 or contract.stderr:
        return (6, 0)
    return (7, 0)


def _profile_domains(profile: dict | None) -> set[str]:
    if not isinstance(profile, dict):
        return set()
    domains: set[str] = set()
    primary = profile.get("primary_domain")
    if isinstance(primary, str):
        domains.add(primary.strip().lower())
    raw_domains = profile.get("domains")
    if isinstance(raw_domains, str):
        domains.add(raw_domains.strip().lower())
    elif isinstance(raw_domains, list):
        domains.update(domain.strip().lower() for domain in raw_domains if isinstance(domain, str))
    strategy_pack = profile.get("strategy_pack")
    if isinstance(strategy_pack, dict) and isinstance(strategy_pack.get("domain"), str):
        domains.add(strategy_pack["domain"].strip().lower())
    return domains


def _network_ping_contract_rank(contract: BehaviorContract, profile_domains: set[str]) -> int | None:
    if "network_ping" not in profile_domains and not _has_network_ping_tag(contract):
        return None
    text = " ".join(
        [
            contract.test_name,
            " ".join(contract.args),
            contract.stdout,
            contract.stderr,
            " ".join(contract.tags),
        ]
    ).lower()
    if any(token in text for token in ("loopback", "localhost", "127.0.0.1", "::1", "ttl=", "time=")):
        return 0
    if any(token in text for token in ("count_parse", "parse error", "-c, --count", "invalid value")):
        return 1
    if any(
        token in text
        for token in (
            "special_address",
            "224.0.0.1",
            "255.255.255.255",
            "169.254.",
            "ff02",
            "network is unreachable",
            "0 packets transmitted",
        )
    ):
        return 2
    if any(token in text for token in ("missing_host", "multiple_hosts", "host diagnostics")):
        return 3
    return 4


def _has_network_ping_tag(contract: BehaviorContract) -> bool:
    return any(tag.strip().lower() == "profile_domain:network_ping" for tag in contract.tags)


def _contract_payload(contract: BehaviorContract) -> dict:
    stdout_limit = 8000 if _needs_full_contract_stream(contract) else 1200
    stderr_limit = 8000 if _needs_full_contract_stream(contract) else 1200
    return {
        "test_name": contract.test_name,
        "args": contract.args,
        "stdin": _truncate_contract_stream(contract.stdin, limit=800),
        "input_files": sorted(contract.input_files),
        "input_file_previews": {
            name: _truncate_contract_stream(content, limit=2000)
            for name, content in sorted(contract.input_file_previews.items())
        },
        "env_vars": dict(sorted(contract.env_vars.items())),
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


def _is_help_contract(contract: BehaviorContract) -> bool:
    args = set(contract.args)
    return contract.test_name.lower() in {"help_long", "help_short"} or "--help" in args or "-h" in args


def _needs_full_contract_stream(contract: BehaviorContract) -> bool:
    return _is_shell_init_contract(contract) or _is_help_contract(contract)


def _is_file_io_contract(contract: BehaviorContract) -> bool:
    return (
        "file_io" in contract.tags
        or bool(contract.input_files)
        or bool(contract.input_file_previews)
        or bool(contract.output_files)
        or bool(contract.output_file_previews)
    )


def _is_materialized_implementation_contract(contract: BehaviorContract) -> bool:
    return is_materializable_static_output_contract(contract)


def _truncate_contract_stream(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    marker = "\n...[truncated]\n"
    if limit <= len(marker):
        return marker[:limit]
    head = max(1, (limit - len(marker)) // 2)
    tail = max(1, limit - len(marker) - head)
    return value[:head].rstrip() + marker + value[-tail:].lstrip()
