"""Infer domain-specific strategy hints from cleanroom evidence."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re
from typing import Iterable

import yaml

from core.data_models import BehaviorSample, CLISurface


@dataclass(frozen=True)
class ProfileRule:
    domain: str
    keywords: tuple[str, ...]
    formats: tuple[str, ...]
    implementation_hints: tuple[str, ...]
    repair_hints: tuple[str, ...]
    implementation_playbook: tuple[str, ...]
    repair_playbook: tuple[str, ...]
    validation_playbook: tuple[str, ...]
    generalization_playbook: tuple[str, ...]
    anti_patterns: tuple[str, ...]


RULES_DIR = Path(__file__).parent / "rules"


@lru_cache(maxsize=1)
def _load_profile_rules() -> tuple[ProfileRule, ...]:
    rules = []
    for path in sorted(RULES_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        rules.append(ProfileRule(
            domain=data["domain"],
            keywords=tuple(data.get("keywords", [])),
            formats=tuple(data.get("formats", [])),
            implementation_hints=tuple(data.get("implementation_hints", [])),
            repair_hints=tuple(data.get("repair_hints", [])),
            implementation_playbook=tuple(data.get("implementation_playbook", [])),
            repair_playbook=tuple(data.get("repair_playbook", [])),
            validation_playbook=tuple(data.get("validation_playbook", [])),
            generalization_playbook=tuple(data.get("generalization_playbook", [])),
            anti_patterns=tuple(data.get("anti_patterns", [])),
        ))
    return tuple(rules)


PROFILE_RULES: tuple[ProfileRule, ...] = _load_profile_rules()

GENERIC_IMPLEMENTATION_HINTS = (
    "Implement only behavior supported by cleanroom evidence; mark uncertain semantics as conservative branches rather than guessing hidden behavior.",
    "Preserve exact stdout/stderr channels, exit codes, argument parsing, and trailing newline behavior from observed contracts.",
)

GENERIC_REPAIR_HINTS = (
    "Repair the smallest shared semantic mismatch indicated by the failure cluster before broad rewrites.",
    "Prefer exact observed behavior over inferred summaries whenever they disagree.",
)

GENERIC_GENERALIZATION_PLAYBOOK = (
    "Before trusting exploration improvements, verify unseen holdout coverage across help, no-arg, stdin, file, and error-mode dispatch when those modes exist.",
    "Prefer reusable parsing and rendering rules over exact transcript lookup tables; exact observed contracts should remain examples, not the whole implementation.",
)

GENERIC_VALIDATION_PLAYBOOK = (
    "Run bounded smoke checks for help, no-arg, stdin/file input, unknown flags, and error branches before accepting generated code.",
    "Compare exploration and holdout aggregate rates after each repair; reject candidates that regress previous accepted behavior.",
    "Keep validation fixtures cleanroom-local and reusable across inputs instead of encoding official hidden-case assumptions.",
)


def infer_task_profile(
    *,
    documentation: str = "",
    cli_surface: CLISurface | None = None,
    corpus: Iterable[BehaviorSample] | None = None,
) -> dict:
    """Return a JSON-safe domain profile for prompting and metadata."""
    evidence_text = _evidence_text(documentation, cli_surface, corpus)
    scores = {
        rule.domain: _score_rule(rule, evidence_text)
        for rule in PROFILE_RULES
    }
    max_score = max(scores.values(), default=0)
    min_related_score = max(1, max_score * 0.75) if max_score >= 4 else 1
    domains = [
        domain
        for domain, score in sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        if score >= min_related_score
    ]
    primary_domain = domains[0] if domains else "generic_cli"
    selected_rules = [
        rule
        for rule in PROFILE_RULES
        if rule.domain in set(domains[:3])
    ]
    implementation_hints = _dedupe(
        [
            hint
            for rule in selected_rules
            for hint in rule.implementation_hints
        ]
        or list(GENERIC_IMPLEMENTATION_HINTS)
    )
    repair_hints = _dedupe(
        [
            hint
            for rule in selected_rules
            for hint in rule.repair_hints
        ]
        or list(GENERIC_REPAIR_HINTS)
    )
    input_format_hints = _dedupe(
        [
            fmt
            for rule in selected_rules
            for fmt in rule.formats
        ]
    )
    strategy_pack = _strategy_pack(primary_domain, selected_rules)
    return {
        "primary_domain": primary_domain,
        "domains": domains or ["generic_cli"],
        "confidence": _confidence(scores.get(primary_domain, 0)),
        "input_format_hints": input_format_hints,
        "implementation_hints": implementation_hints[:6],
        "repair_hints": repair_hints[:6],
        "strategy_pack": strategy_pack,
        "evidence_keywords": _evidence_keywords(evidence_text, selected_rules),
    }


def _strategy_pack(primary_domain: str, rules: list[ProfileRule]) -> dict:
    if not rules:
        return {
            "domain": "generic_cli",
            "implementation_playbook": list(GENERIC_IMPLEMENTATION_HINTS),
            "repair_playbook": list(GENERIC_REPAIR_HINTS),
            "validation_playbook": list(GENERIC_VALIDATION_PLAYBOOK),
            "generalization_playbook": list(GENERIC_GENERALIZATION_PLAYBOOK),
            "anti_patterns": [],
        }
    primary_rule = next((rule for rule in rules if rule.domain == primary_domain), rules[0])
    return {
        "domain": primary_rule.domain,
        "implementation_playbook": list(primary_rule.implementation_playbook),
        "repair_playbook": list(primary_rule.repair_playbook),
        "validation_playbook": list(primary_rule.validation_playbook or GENERIC_VALIDATION_PLAYBOOK),
        "generalization_playbook": list(primary_rule.generalization_playbook or GENERIC_GENERALIZATION_PLAYBOOK),
        "anti_patterns": list(primary_rule.anti_patterns),
    }


def _evidence_text(
    documentation: str,
    cli_surface: CLISurface | None,
    corpus: Iterable[BehaviorSample] | None,
) -> str:
    chunks: list[str] = [documentation]
    if cli_surface is not None:
        chunks.extend(cli_surface.subcommands)
        chunks.extend(flag.name for flag in cli_surface.flags)
        chunks.extend(flag.description for flag in cli_surface.flags)
        chunks.extend(arg.name for arg in cli_surface.positional_args)
    for sample in corpus or []:
        chunks.append(sample.test_case.name)
        chunks.append(sample.test_case.description)
        chunks.extend(sample.test_case.args)
        chunks.append(sample.test_case.stdin)
        chunks.extend(sample.tags)
        chunks.append(sample.observed_result.stdout[:1000])
        chunks.append(sample.observed_result.stderr[:500])
    return "\n".join(chunk for chunk in chunks if chunk).lower()


def _score_rule(rule: ProfileRule, text: str) -> int:
    score = 0
    for keyword in rule.keywords:
        if re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", text):
            score += 2 if " " in keyword else 1
    for fmt in rule.formats:
        if fmt in text:
            score += 1
    return score


def _confidence(score: int) -> str:
    if score >= 4:
        return "high"
    if score >= 2:
        return "medium"
    if score == 1:
        return "low"
    return "fallback"


def _evidence_keywords(text: str, rules: list[ProfileRule]) -> list[str]:
    observed: list[str] = []
    for rule in rules:
        for keyword in rule.keywords:
            if keyword in text:
                observed.append(keyword)
    return _dedupe(observed)[:12]


def _dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
