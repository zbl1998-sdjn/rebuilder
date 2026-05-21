"""Domain-aware deterministic probe planning from inferred task profiles."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from core.data_models import TestCase
from core.probing.adaptive_domains import (
    DOMAIN_PROBE_BUILDERS,
    SUPPORTED_DOMAINS as ADAPTIVE_SUPPORTED_DOMAINS,
    normalize_profile_domains,
)


class AdaptiveProbePlanner:
    """Plan cleanroom probes for high-signal task-profile domains.

    The planner intentionally does not call ProbeEngine or inspect repository
    identity. It only uses domain labels inferred from docs, CLI help, and
    corpus metadata, then emits deterministic edge cases for that domain.
    """

    SUPPORTED_DOMAINS = ADAPTIVE_SUPPORTED_DOMAINS

    def __init__(self, excluded_domains: Iterable[str] | None = None):
        self.excluded_domains = {
            domain.strip().lower()
            for domain in (excluded_domains or ())
            if isinstance(domain, str) and domain.strip()
        }

    def plan(
        self,
        profile: dict,
        documentation: str = "",
        cli_surface: Any = None,
        corpus: Any = None,
    ) -> list[TestCase]:
        del documentation, cli_surface, corpus

        probes: list[TestCase] = []
        for domain in self._domains(profile):
            builder = DOMAIN_PROBE_BUILDERS.get(domain)
            if builder is not None:
                probes.extend(builder())
        return probes

    def _domains(self, profile: dict) -> list[str]:
        return normalize_profile_domains(
            profile,
            supported_domains=self.SUPPORTED_DOMAINS,
            excluded_domains=self.excluded_domains,
        )
