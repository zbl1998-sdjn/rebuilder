"""Deterministic probe planner for uncovered behavior."""

from __future__ import annotations

from core.coverage.behavioral import BehavioralCoverageReport
from core.data_models import TestCase
from core.hypotheses.graph import HypothesisGraph


class ProbePlanner:
    """Plan simple follow-up probes from coverage gaps and hypotheses."""

    def plan(
        self,
        coverage: BehavioralCoverageReport | None = None,
        hypotheses: HypothesisGraph | None = None,
    ) -> list[TestCase]:
        probes: list[TestCase] = []

        if coverage:
            for flag in sorted(coverage.uncovered_flags):
                probes.append(
                    TestCase(
                        name=f"probe_flag_{flag.lstrip('-').replace('-', '_')}",
                        args=[flag],
                        description=f"Probe uncovered documented flag {flag}",
                    )
                )

        if hypotheses:
            for hypothesis in hypotheses.unresolved():
                for name in hypothesis.missing_probes:
                    probes.append(
                        TestCase(
                            name=name,
                            description=f"Probe missing evidence for: {hypothesis.claim}",
                        )
                    )

        return probes
