from core.coverage.behavioral import BehavioralCoverageReport
from core.hypotheses.graph import HypothesisGraph
from core.probing.planner import ProbePlanner


def test_probe_planner_targets_uncovered_flags():
    coverage = BehavioralCoverageReport(uncovered_flags={"--json", "--version"})

    probes = ProbePlanner().plan(coverage=coverage)

    args = {tuple(probe.args) for probe in probes}
    assert ("--json",) in args
    assert ("--version",) in args


def test_probe_planner_includes_missing_hypothesis_probes():
    graph = HypothesisGraph()
    graph.add_claim("supports json", missing_probes=["json_stdin"])

    probes = ProbePlanner().plan(hypotheses=graph)

    assert any(probe.name == "json_stdin" for probe in probes)
