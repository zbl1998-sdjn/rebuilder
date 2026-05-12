from core.hypotheses.graph import HypothesisGraph, HypothesisStatus


def test_hypothesis_graph_records_evidence_backed_claims():
    graph = HypothesisGraph()

    hypothesis = graph.add_claim(
        claim="empty stdin exits with code 2",
        evidence_ids=["abc"],
        confidence=0.8,
    )

    assert hypothesis.status == HypothesisStatus.LIKELY
    assert hypothesis.evidence_ids == ["abc"]
    assert graph.get(hypothesis.hypothesis_id) == hypothesis


def test_hypothesis_graph_status_transitions_and_missing_probes():
    graph = HypothesisGraph()
    hypothesis = graph.add_claim("supports --json output", missing_probes=["json_happy_path"])

    graph.confirm(hypothesis.hypothesis_id, evidence_id="e1")

    confirmed = graph.get(hypothesis.hypothesis_id)
    assert confirmed.status == HypothesisStatus.CONFIRMED
    assert confirmed.evidence_ids == ["e1"]
    assert confirmed.missing_probes == []


def test_hypothesis_graph_tracks_contradictions():
    graph = HypothesisGraph()
    hypothesis = graph.add_claim("unknown flag exits 1")

    graph.contradict(hypothesis.hypothesis_id, evidence_id="counter")

    contradicted = graph.get(hypothesis.hypothesis_id)
    assert contradicted.status == HypothesisStatus.CONTRADICTED
    assert contradicted.counterexample_ids == ["counter"]
    assert graph.contradictions() == [contradicted]
