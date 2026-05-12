"""Infer domain-specific strategy hints from cleanroom evidence."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from core.data_models import BehaviorSample, CLISurface


@dataclass(frozen=True)
class ProfileRule:
    domain: str
    keywords: tuple[str, ...]
    formats: tuple[str, ...]
    implementation_hints: tuple[str, ...]
    repair_hints: tuple[str, ...]


PROFILE_RULES: tuple[ProfileRule, ...] = (
    ProfileRule(
        domain="network_ping",
        keywords=(
            "ping",
            "icmp",
            "packet",
            "packets",
            "ttl",
            "latency",
            "rtt",
            "host",
            "hostname",
            "ipv4",
            "ipv6",
            "dns",
        ),
        formats=("plain_text",),
        implementation_hints=(
            "Treat network behavior as a CLI output contract first; do not depend on privileged raw sockets unless observed behavior requires it.",
            "Model host/count/timeout/interval parsing explicitly and preserve stderr, exit codes, and timeout wording for unreachable or invalid hosts.",
            "Keep any real network calls bounded by short timeouts and provide deterministic formatting around measured values.",
        ),
        repair_hints=(
            "If mismatches mention packet summaries, RTT/latency lines, DNS failures, or permission errors, repair formatting and exit-code semantics before adding network complexity.",
            "Check that count defaults, host position, and unreachable-host branches match observed contracts.",
        ),
    ),
    ProfileRule(
        domain="csv_table",
        keywords=(
            "csv",
            "delimiter",
            "quote",
            "header",
            "column",
            "select",
            "sort",
            "table",
            "record",
            "tsv",
        ),
        formats=("csv", "tsv", "table"),
        implementation_hints=(
            "Use Python csv parsing instead of ad-hoc split logic so quoting, embedded delimiters, and newlines remain correct.",
            "Preserve header handling, column selection order, delimiter flags, and empty-field rendering exactly.",
        ),
        repair_hints=(
            "For table mismatches, inspect delimiter, quoting, header, row ordering, and trailing newline behavior first.",
            "Avoid normalizing whitespace unless observations prove the original does.",
        ),
    ),
    ProfileRule(
        domain="json_transform",
        keywords=(
            "json",
            "jq",
            "gron",
            "object",
            "array",
            "key",
            "value",
            "pretty",
            "ungron",
        ),
        formats=("json",),
        implementation_hints=(
            "Use json.loads/json.dumps and preserve ordering, escaping, indentation, and newline behavior seen in contracts.",
            "Handle invalid JSON and empty input with observed stderr and exit-code semantics.",
        ),
        repair_hints=(
            "For JSON mismatches, check escaping, key ordering, list indexes, invalid-input diagnostics, and final newline behavior.",
        ),
    ),
    ProfileRule(
        domain="html_selector",
        keywords=(
            "html",
            "css selector",
            "selector",
            "tag",
            "attribute",
            "href",
            "text",
            "node",
            "element",
            "htmlq",
        ),
        formats=("html", "xml"),
        implementation_hints=(
            "Parse HTML leniently and preserve selector semantics, text-vs-HTML output modes, attribute extraction, and document order.",
            "Prefer small deterministic selector support over broad dependencies unless the project already allows them.",
        ),
        repair_hints=(
            "For HTML mismatches, check selector matching, text extraction whitespace, attribute mode, and whether output keeps original markup.",
        ),
    ),
    ProfileRule(
        domain="archive_compression",
        keywords=(
            "zip",
            "tar",
            "gzip",
            "archive",
            "compress",
            "password",
            "encrypted",
            "crc",
        ),
        formats=("binary", "archive"),
        implementation_hints=(
            "Use standard archive libraries where possible and preserve binary-safe file handling.",
            "Treat passwords, missing files, and corrupt archives as explicit error branches with observed channels and exit codes.",
        ),
        repair_hints=(
            "For archive mismatches, check binary mode, password handling, member path normalization, and corrupt-file diagnostics.",
        ),
    ),
    ProfileRule(
        domain="terminal_ui",
        keywords=(
            "terminal",
            "ansi",
            "escape",
            "color",
            "tui",
            "screen",
            "cursor",
            "matrix",
        ),
        formats=("ansi", "terminal"),
        implementation_hints=(
            "Keep terminal control output deterministic under test conditions and preserve ANSI sequences only when observed.",
            "Avoid interactive waits unless stdin/TTY behavior is explicitly covered.",
        ),
        repair_hints=(
            "For terminal mismatches, compare raw escape sequences, screen dimensions, color flags, and timeout behavior.",
        ),
    ),
    ProfileRule(
        domain="filesystem_tool",
        keywords=(
            "file",
            "directory",
            "path",
            "stat",
            "permission",
            "symlink",
            "mkdir",
            "rename",
        ),
        formats=("file", "path"),
        implementation_hints=(
            "Perform path and filesystem operations explicitly, including missing paths, directories vs files, and symlink behavior when observed.",
            "Keep writes idempotent where feasible and surface OS errors through observed stderr and exit-code semantics.",
        ),
        repair_hints=(
            "For filesystem mismatches, check path normalization, current working directory assumptions, file mode, and missing-path errors.",
        ),
    ),
)

GENERIC_IMPLEMENTATION_HINTS = (
    "Implement only behavior supported by cleanroom evidence; mark uncertain semantics as conservative branches rather than guessing hidden behavior.",
    "Preserve exact stdout/stderr channels, exit codes, argument parsing, and trailing newline behavior from observed contracts.",
)

GENERIC_REPAIR_HINTS = (
    "Repair the smallest shared semantic mismatch indicated by the failure cluster before broad rewrites.",
    "Prefer exact observed behavior over inferred summaries whenever they disagree.",
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
    domains = [
        domain
        for domain, score in sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        if score > 0
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
    return {
        "primary_domain": primary_domain,
        "domains": domains or ["generic_cli"],
        "confidence": _confidence(scores.get(primary_domain, 0)),
        "input_format_hints": input_format_hints,
        "implementation_hints": implementation_hints[:6],
        "repair_hints": repair_hints[:6],
        "evidence_keywords": _evidence_keywords(evidence_text, selected_rules),
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
