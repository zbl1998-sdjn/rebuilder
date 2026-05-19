"""Deterministic strategy selection over aggregate experiment history."""

from __future__ import annotations

from collections import defaultdict
import math

from core.experiments.registry import ExperimentRun, StrategyVariant


class StrategyBandit:
    """Select variants by historical average official score."""

    def __init__(self, min_holdout_cases: int = 1):
        self.min_holdout_cases = validate_min_holdout_cases(min_holdout_cases)

    def select_variant(
        self,
        history: list[ExperimentRun],
        candidates: list[StrategyVariant],
    ) -> StrategyVariant:
        if not candidates:
            raise ValueError("at least one strategy candidate is required")

        scores: dict[str, list[float]] = defaultdict(list)
        for row in history:
            if row.holdout_cases < self.min_holdout_cases:
                continue
            scores[row.variant.variant_id].append(row.official.score)

        candidate_positions = {candidate.variant_id: index for index, candidate in enumerate(candidates)}

        def rank(candidate: StrategyVariant) -> tuple[int, float, int]:
            candidate_scores = scores.get(candidate.variant_id, [])
            if not candidate_scores:
                return (0, 0.0, -candidate_positions[candidate.variant_id])
            average = sum(candidate_scores) / len(candidate_scores)
            return (1, average, -candidate_positions[candidate.variant_id])

        return max(candidates, key=rank)


def validate_min_holdout_cases(value: int) -> int:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("min_holdout_cases must be a finite non-negative integer") from exc
    if not math.isfinite(parsed) or parsed < 0 or not parsed.is_integer():
        raise ValueError("min_holdout_cases must be a finite non-negative integer")
    return int(parsed)
