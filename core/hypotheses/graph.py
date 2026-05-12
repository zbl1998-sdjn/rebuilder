"""Evidence-backed hypothesis graph for cleanroom reconstruction."""

from __future__ import annotations

import hashlib
from enum import Enum
from typing import Dict, List

from pydantic import BaseModel, Field


class HypothesisStatus(str, Enum):
    UNKNOWN = "unknown"
    LIKELY = "likely"
    CONFIRMED = "confirmed"
    CONTRADICTED = "contradicted"


class BehaviorHypothesis(BaseModel):
    hypothesis_id: str
    claim: str
    status: HypothesisStatus = HypothesisStatus.UNKNOWN
    confidence: float = 0.0
    evidence_ids: List[str] = Field(default_factory=list)
    counterexample_ids: List[str] = Field(default_factory=list)
    missing_probes: List[str] = Field(default_factory=list)


class HypothesisGraph:
    """Small graph-like collection of behavior claims and their evidence."""

    def __init__(self):
        self._items: Dict[str, BehaviorHypothesis] = {}

    def add_claim(
        self,
        claim: str,
        evidence_ids: List[str] | None = None,
        confidence: float = 0.0,
        missing_probes: List[str] | None = None,
    ) -> BehaviorHypothesis:
        hypothesis_id = hashlib.sha256(claim.encode("utf-8")).hexdigest()[:16]
        status = HypothesisStatus.LIKELY if evidence_ids or confidence > 0 else HypothesisStatus.UNKNOWN
        item = BehaviorHypothesis(
            hypothesis_id=hypothesis_id,
            claim=claim,
            status=status,
            confidence=confidence,
            evidence_ids=evidence_ids or [],
            missing_probes=missing_probes or [],
        )
        self._items[hypothesis_id] = item
        return item

    def get(self, hypothesis_id: str) -> BehaviorHypothesis:
        return self._items[hypothesis_id]

    def confirm(self, hypothesis_id: str, evidence_id: str) -> None:
        item = self._items[hypothesis_id]
        if evidence_id not in item.evidence_ids:
            item.evidence_ids.append(evidence_id)
        item.status = HypothesisStatus.CONFIRMED
        item.confidence = 1.0
        item.missing_probes = []

    def contradict(self, hypothesis_id: str, evidence_id: str) -> None:
        item = self._items[hypothesis_id]
        if evidence_id not in item.counterexample_ids:
            item.counterexample_ids.append(evidence_id)
        item.status = HypothesisStatus.CONTRADICTED
        item.confidence = 0.0

    def unresolved(self) -> list[BehaviorHypothesis]:
        return [
            item
            for item in self._items.values()
            if item.status in {HypothesisStatus.UNKNOWN, HypothesisStatus.LIKELY}
        ]

    def contradictions(self) -> list[BehaviorHypothesis]:
        return [item for item in self._items.values() if item.status == HypothesisStatus.CONTRADICTED]
