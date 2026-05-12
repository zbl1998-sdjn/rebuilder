from core.coverage.behavioral import BehavioralCoverageAnalyzer
from core.data_models import BehaviorSample, CLISurface, FlagSpec, TestCase, TestResult


def sample(name, args=None, stdin="", input_files=None, result=None):
    return BehaviorSample(
        test_case=TestCase(
            name=name,
            args=args or [],
            stdin=stdin,
            input_files=input_files or {},
        ),
        observed_result=result or TestResult(stdout="", stderr="", exit_code=0),
    )


def test_behavioral_coverage_tracks_observed_modes_and_exit_classes():
    corpus = [
        sample("help", args=["--help"], result=TestResult(stdout="usage", exit_code=0)),
        sample("stdin", stdin="abc", result=TestResult(stderr="warn", exit_code=2)),
        sample("dash", args=["-"], stdin="abc", result=TestResult(stdout="ok", exit_code=0)),
        sample("subcommand", args=["count"], result=TestResult(stdout="2", exit_code=0)),
        sample("file", input_files={"input.txt": b"abc"}, result=TestResult(output_files={"out.txt": b"x"})),
    ]
    cli = CLISurface(
        flags=[FlagSpec(name="--help"), FlagSpec(name="--version")],
        subcommands=["count", "select"],
        stdin_mode=True,
        file_input_mode=True,
        file_output_mode=True,
    )

    report = BehavioralCoverageAnalyzer().analyze(corpus, cli)

    assert report.total_samples == 5
    assert report.observed_flags == {"--help"}
    assert report.uncovered_flags == {"--version"}
    assert report.observed_subcommands == {"count"}
    assert report.uncovered_subcommands == {"select"}
    assert report.stdin_cases == 2
    assert report.explicit_stdin_cases == 1
    assert report.file_input_cases == 1
    assert report.stderr_cases == 1
    assert report.output_file_cases == 1
    assert report.exit_codes == {0, 2}
    assert report.nonzero_exit_cases == 1
    assert "flags" in report.missing_modes
    assert "subcommands" in report.missing_modes


def test_behavioral_coverage_detects_equals_style_flags():
    corpus = [sample("flag-equals", args=["--count=2"])]
    cli = CLISurface(flags=[FlagSpec(name="--count")])

    report = BehavioralCoverageAnalyzer().analyze(corpus, cli)

    assert report.observed_flags == {"--count"}
    assert report.uncovered_flags == set()


def test_behavioral_coverage_score_increases_with_modes_and_flags():
    cli = CLISurface(flags=[FlagSpec(name="--help")])
    low = BehavioralCoverageAnalyzer().analyze([sample("plain")], cli)
    high = BehavioralCoverageAnalyzer().analyze([sample("help", args=["--help"], stdin="x")], cli)

    assert high.coverage_score > low.coverage_score
