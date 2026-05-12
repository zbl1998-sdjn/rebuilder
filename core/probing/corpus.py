"""Deterministic corpus splitting for cleanroom validation."""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from pydantic import BaseModel, Field

from core.data_models import BehaviorSample
from core.evidence.models import test_case_fingerprint


class CorpusSplit(BaseModel):
    exploration: list[BehaviorSample] = Field(default_factory=list)
    holdout: list[BehaviorSample] = Field(default_factory=list)
    adversarial: list[BehaviorSample] = Field(default_factory=list)


class CorpusSplitter:
    """Split observations without using official hidden tests."""

    def __init__(self, holdout_ratio: float = 0.2, seed: str = "rebuilder"):
        self.holdout_ratio = max(0.0, min(holdout_ratio, 0.9))
        self.seed = seed

    def split(self, corpus: list[BehaviorSample]) -> CorpusSplit:
        if len(corpus) < 2 or self.holdout_ratio == 0:
            return CorpusSplit(exploration=list(corpus))
        holdout_count = int(round(len(corpus) * self.holdout_ratio))
        holdout_count = max(1, min(holdout_count, len(corpus) - 1))
        groups = self._atomic_groups(corpus)
        ordered_groups = sorted(groups.values(), key=self._group_stable_key)
        holdout: list[BehaviorSample] = []
        for group in ordered_groups:
            if len(holdout) >= holdout_count:
                break
            if len(holdout) + len(group) >= len(corpus):
                continue
            holdout.extend(group)
            if len(holdout) >= holdout_count:
                break
        if not holdout:
            holdout = ordered_groups[0]
        holdout_ids = {id(sample) for sample in holdout}
        exploration = [sample for sample in corpus if id(sample) not in holdout_ids]
        return CorpusSplit(exploration=exploration, holdout=holdout)

    def _stable_key(self, sample: BehaviorSample) -> str:
        raw = f"{self.seed}:{test_case_fingerprint(sample.test_case)}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def _atomic_groups(self, corpus: list[BehaviorSample]) -> "OrderedDict[str, list[BehaviorSample]]":
        groups: OrderedDict[str, list[BehaviorSample]] = OrderedDict()
        for index, sample in enumerate(corpus):
            groups.setdefault(self._group_key(sample, index), []).append(sample)
        return groups

    def _group_key(self, sample: BehaviorSample, index: int) -> str:
        for tag in sample.tags:
            if tag.startswith("stateful_plan:"):
                return tag
        return f"sample:{index}"

    def _group_stable_key(self, group: list[BehaviorSample]) -> str:
        payload = "|".join(self._stable_key(sample) for sample in group)
        raw = f"{self.seed}:{payload}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()
