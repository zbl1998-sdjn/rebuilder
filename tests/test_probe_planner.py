from core.coverage.behavioral import BehavioralCoverageReport
from core.hypotheses.graph import HypothesisGraph
from core.probing.planner import ProbePlanner


def test_probe_planner_targets_uncovered_flags():
    coverage = BehavioralCoverageReport(
        uncovered_flags={"--json", "--version"},
        uncovered_subcommands={"count"},
        missing_modes={"stdin", "explicit_stdin", "file_input", "nonzero_exit"},
    )

    probes = ProbePlanner().plan(coverage=coverage)

    args = {tuple(probe.args) for probe in probes}
    assert ("--json",) in args
    assert ("--version",) in args
    assert ("count", "--help") in args
    assert ("-",) in args
    assert ("input.txt",) in args
    assert ("--__rebuilder_invalid_flag__",) in args
    assert any(probe.stdin for probe in probes)


def test_probe_planner_includes_missing_hypothesis_probes():
    graph = HypothesisGraph()
    graph.add_claim("supports json", missing_probes=["json_stdin"])

    probes = ProbePlanner().plan(hypotheses=graph)

    assert any(probe.name == "json_stdin" for probe in probes)
