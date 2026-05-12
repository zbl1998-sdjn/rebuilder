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
        sample("file", input_files={"input.txt": b"abc"}, result=TestResult(output_files={"out.txt": b"x"})),
    ]
    cli = CLISurface(flags=[FlagSpec(name="--help"), FlagSpec(name="--version")])

    report = BehavioralCoverageAnalyzer().analyze(corpus, cli)

    assert report.total_samples == 3
    assert report.observed_flags == {"--help"}
    assert report.uncovered_flags == {"--version"}
    assert report.stdin_cases == 1
    assert report.file_input_cases == 1
    assert report.stderr_cases == 1
    assert report.output_file_cases == 1
    assert report.exit_codes == {0, 2}


def test_behavioral_coverage_score_increases_with_modes_and_flags():
    cli = CLISurface(flags=[FlagSpec(name="--help")])
    low = BehavioralCoverageAnalyzer().analyze([sample("plain")], cli)
    high = BehavioralCoverageAnalyzer().analyze([sample("help", args=["--help"], stdin="x")], cli)

    assert high.coverage_score > low.coverage_score
