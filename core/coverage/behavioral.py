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
    observed_subcommands: set[str] = Field(default_factory=set)
    uncovered_subcommands: set[str] = Field(default_factory=set)
    exit_codes: set[int] = Field(default_factory=set)
    stdin_cases: int = 0
    explicit_stdin_cases: int = 0
    file_input_cases: int = 0
    stderr_cases: int = 0
    output_file_cases: int = 0
    nonzero_exit_cases: int = 0
    missing_modes: set[str] = Field(default_factory=set)
    coverage_score: float = 0.0


class BehavioralCoverageAnalyzer:
    """Summarize cleanroom exploration coverage from observable behavior."""

    def analyze(
        self,
        corpus: list[BehaviorSample],
        cli_surface: CLISurface,
    ) -> BehavioralCoverageReport:
        known_flags = {flag.name for flag in cli_surface.flags}
        known_subcommands = set(cli_surface.subcommands)
        observed_flags: set[str] = set()
        observed_subcommands: set[str] = set()
        exit_codes: set[int] = set()
        stdin_cases = explicit_stdin_cases = file_input_cases = stderr_cases = output_file_cases = 0
        nonzero_exit_cases = 0

        for sample in corpus:
            test_case = sample.test_case
            result = sample.observed_result
            observed_flags.update(self._observed_flags(test_case.args, known_flags))
            if test_case.args and test_case.args[0] in known_subcommands:
                observed_subcommands.add(test_case.args[0])
            exit_codes.add(result.exit_code)
            if test_case.stdin:
                stdin_cases += 1
            if "-" in test_case.args:
                explicit_stdin_cases += 1
            if test_case.input_files:
                file_input_cases += 1
            if result.stderr:
                stderr_cases += 1
            if result.output_files:
                output_file_cases += 1
            if result.exit_code != 0:
                nonzero_exit_cases += 1

        uncovered_flags = known_flags - observed_flags
        uncovered_subcommands = known_subcommands - observed_subcommands
        missing_modes = self._missing_modes(
            cli_surface=cli_surface,
            uncovered_flags=uncovered_flags,
            uncovered_subcommands=uncovered_subcommands,
            stdin_cases=stdin_cases,
            explicit_stdin_cases=explicit_stdin_cases,
            file_input_cases=file_input_cases,
            stderr_cases=stderr_cases,
            output_file_cases=output_file_cases,
            nonzero_exit_cases=nonzero_exit_cases,
        )
        score_parts = [
            _ratio(len(observed_flags), len(known_flags)) if known_flags else 1.0,
            _ratio(len(observed_subcommands), len(known_subcommands)) if known_subcommands else 1.0,
            1.0 if stdin_cases else 0.0,
            1.0 if explicit_stdin_cases else 0.0,
            1.0 if file_input_cases else 0.0,
            1.0 if stderr_cases else 0.0,
            1.0 if output_file_cases else 0.0,
            1.0 if nonzero_exit_cases else 0.0,
            min(len(exit_codes), 3) / 3,
        ]
        return BehavioralCoverageReport(
            total_samples=len(corpus),
            observed_flags=observed_flags,
            uncovered_flags=uncovered_flags,
            observed_subcommands=observed_subcommands,
            uncovered_subcommands=uncovered_subcommands,
            exit_codes=exit_codes,
            stdin_cases=stdin_cases,
            explicit_stdin_cases=explicit_stdin_cases,
            file_input_cases=file_input_cases,
            stderr_cases=stderr_cases,
            output_file_cases=output_file_cases,
            nonzero_exit_cases=nonzero_exit_cases,
            missing_modes=missing_modes,
            coverage_score=sum(score_parts) / len(score_parts),
        )

    def _observed_flags(self, args: list[str], known_flags: set[str]) -> set[str]:
        observed: set[str] = set()
        for arg in args:
            if arg in known_flags:
                observed.add(arg)
                continue
            if arg.startswith("--") and "=" in arg:
                flag_name = arg.split("=", 1)[0]
                if flag_name in known_flags:
                    observed.add(flag_name)
        return observed

    def _missing_modes(
        self,
        *,
        cli_surface: CLISurface,
        uncovered_flags: set[str],
        uncovered_subcommands: set[str],
        stdin_cases: int,
        explicit_stdin_cases: int,
        file_input_cases: int,
        stderr_cases: int,
        output_file_cases: int,
        nonzero_exit_cases: int,
    ) -> set[str]:
        missing: set[str] = set()
        if uncovered_flags:
            missing.add("flags")
        if uncovered_subcommands:
            missing.add("subcommands")
        if not stdin_cases:
            missing.add("stdin")
        if cli_surface.stdin_mode and not explicit_stdin_cases:
            missing.add("explicit_stdin")
        if cli_surface.file_input_mode and not file_input_cases:
            missing.add("file_input")
        if cli_surface.file_output_mode and not output_file_cases:
            missing.add("file_output")
        if not stderr_cases:
            missing.add("stderr")
        if not nonzero_exit_cases:
            missing.add("nonzero_exit")
        return missing


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0
