"""Behavior-only coverage proxy.

This module intentionally uses only CLI surface metadata and observed behavior
samples. It never inspects source code, hidden tests, or binary internals.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from core.data_models import BehaviorSample, CLISurface


class BehavioralCoverageReport(BaseModel):
    total_samples: int = 0
    observed_flags: set[str] = Field(default_factory=set)
    uncovered_flags: set[str] = Field(default_factory=set)
    exit_codes: set[int] = Field(default_factory=set)
    stdin_cases: int = 0
    file_input_cases: int = 0
    stderr_cases: int = 0
    output_file_cases: int = 0
    coverage_score: float = 0.0


class BehavioralCoverageAnalyzer:
    """Summarize cleanroom exploration coverage from observable behavior."""

    def analyze(
        self,
        corpus: list[BehaviorSample],
        cli_surface: CLISurface,
    ) -> BehavioralCoverageReport:
        known_flags = {flag.name for flag in cli_surface.flags}
        observed_flags: set[str] = set()
        exit_codes: set[int] = set()
        stdin_cases = file_input_cases = stderr_cases = output_file_cases = 0

        for sample in corpus:
            test_case = sample.test_case
            result = sample.observed_result
            observed_flags.update(arg for arg in test_case.args if arg in known_flags)
            exit_codes.add(result.exit_code)
            if test_case.stdin:
                stdin_cases += 1
            if test_case.input_files:
                file_input_cases += 1
            if result.stderr:
                stderr_cases += 1
            if result.output_files:
                output_file_cases += 1

        uncovered_flags = known_flags - observed_flags
        score_parts = [
            _ratio(len(observed_flags), len(known_flags)) if known_flags else 1.0,
            1.0 if stdin_cases else 0.0,
            1.0 if file_input_cases else 0.0,
            1.0 if stderr_cases else 0.0,
            1.0 if output_file_cases else 0.0,
            min(len(exit_codes), 3) / 3,
        ]
        return BehavioralCoverageReport(
            total_samples=len(corpus),
            observed_flags=observed_flags,
            uncovered_flags=uncovered_flags,
            exit_codes=exit_codes,
            stdin_cases=stdin_cases,
            file_input_cases=file_input_cases,
            stderr_cases=stderr_cases,
            output_file_cases=output_file_cases,
            coverage_score=sum(score_parts) / len(score_parts),
        )


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0
