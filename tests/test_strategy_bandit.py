import math

import pytest

from core.experiments.bandit import StrategyBandit
from core.experiments.registry import AggregateFeedback, ExperimentRun, StrategyVariant


def variant(variant_id: str) -> StrategyVariant:
    return StrategyVariant(variant_id=variant_id, strategy="repair_loop")


def run(variant_id: str, score: float, holdout_cases: int = 1) -> ExperimentRun:
    return ExperimentRun(
        run_id=f"{variant_id}-{score}",
        instance_id="owner__repo.abcdef0",
        variant=variant(variant_id),
        official=AggregateFeedback(score=score, passed_tests=0, total_tests=0, pass_rate=score),
        holdout_cases=holdout_cases,
    )


def test_bandit_selects_variant_with_higher_average_official_score():
    candidates = [variant("baseline"), variant("learned")]
    history = [
        run("baseline", 0.4),
        run("baseline", 0.6),
        run("learned", 0.9),
    ]

    selected = StrategyBandit().select_variant(history, candidates)

    assert selected.variant_id == "learned"


def test_bandit_prefers_history_over_no_history():
    candidates = [variant("new"), variant("known")]
    history = [run("known", 0.1)]

    selected = StrategyBandit().select_variant(history, candidates)

    assert selected.variant_id == "known"


def test_bandit_ignores_rows_with_insufficient_holdout_cases():
    candidates = [variant("strong_without_holdout"), variant("validated")]
    history = [
        run("strong_without_holdout", 1.0, holdout_cases=0),
        run("validated", 0.25, holdout_cases=1),
    ]

    selected = StrategyBandit().select_variant(history, candidates)

    assert selected.variant_id == "validated"


def test_bandit_uses_candidate_order_when_no_history_or_tie():
    candidates = [variant("first"), variant("second")]

    assert StrategyBandit().select_variant([], candidates).variant_id == "first"
    assert StrategyBandit().select_variant([run("first", 0.5), run("second", 0.5)], candidates).variant_id == "first"


def test_bandit_requires_candidates():
    with pytest.raises(ValueError, match="at least one"):
        StrategyBandit().select_variant([], [])


@pytest.mark.parametrize("min_holdout_cases", [-1, math.nan, 1.5])
def test_bandit_rejects_invalid_min_holdout_cases(min_holdout_cases):
    with pytest.raises(ValueError, match="min_holdout_cases must be"):
        StrategyBandit(min_holdout_cases=min_holdout_cases)
