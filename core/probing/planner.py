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
            for subcommand in sorted(coverage.uncovered_subcommands):
                probes.append(
                    TestCase(
                        name=f"probe_subcommand_{subcommand}_help",
                        args=[subcommand, "--help"],
                        description=f"Probe uncovered documented subcommand {subcommand}",
                    )
                )
            if "stdin" in coverage.missing_modes:
                probes.append(
                    TestCase(
                        name="probe_mode_stdin_json",
                        stdin='{"probe":true,"items":[1,2]}\n',
                        description="Probe stdin input mode with structured data",
                    )
                )
            if "explicit_stdin" in coverage.missing_modes:
                probes.append(
                    TestCase(
                        name="probe_mode_explicit_stdin",
                        args=["-"],
                        stdin='{"probe":true}\n',
                        description="Probe explicit '-' stdin marker",
                    )
                )
            if "file_input" in coverage.missing_modes:
                probes.append(
                    TestCase(
                        name="probe_mode_file_input",
                        args=["input.txt"],
                        input_files={"input.txt": b"a,b\n1,2\n"},
                        description="Probe file input mode",
                    )
                )
            if "nonzero_exit" in coverage.missing_modes:
                probes.append(
                    TestCase(
                        name="probe_mode_invalid_flag",
                        args=["--__rebuilder_invalid_flag__"],
                        description="Probe invalid-option error behavior",
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
