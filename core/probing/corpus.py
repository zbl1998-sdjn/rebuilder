"""Deterministic corpus splitting for cleanroom validation."""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from pydantic import BaseModel, Field

from core.data_models import BehaviorSample
from core.evidence.models import test_case_fingerprint
from core.probing.axes import description_axis_tags


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
        covered_dimensions: set[str] = set()
        remaining_groups = list(ordered_groups)
        while remaining_groups and len(holdout) < holdout_count:
            remaining_slots = holdout_count - len(holdout)
            candidate_groups = [group for group in remaining_groups if len(group) <= remaining_slots]
            if not candidate_groups:
                if holdout:
                    break
                candidate_groups = remaining_groups
            group = self._next_holdout_group(candidate_groups, covered_dimensions)
            remaining_groups.remove(group)
            if len(holdout) >= holdout_count:
                break
            if len(holdout) + len(group) >= len(corpus):
                continue
            holdout.extend(group)
            covered_dimensions.update(self._group_dimensions(group))
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

    def _next_holdout_group(
        self,
        groups: list[list[BehaviorSample]],
        covered_dimensions: set[str],
    ) -> list[BehaviorSample]:
        def coverage_key(group: list[BehaviorSample]) -> tuple[int, int, int, str]:
            new_dimensions = self._group_dimensions(group) - covered_dimensions
            non_generic_dimensions = new_dimensions - {"generic"}
            return (
                -len(non_generic_dimensions),
                -len(new_dimensions),
                len(group),
                self._group_stable_key(group),
            )

        return min(
            groups,
            key=coverage_key,
        )

    def _group_dimensions(self, group: list[BehaviorSample]) -> set[str]:
        dimensions: set[str] = set()
        for sample in group:
            dimensions.update(self._sample_dimensions(sample))
        return dimensions or {"generic"}

    def _sample_dimensions(self, sample: BehaviorSample) -> set[str]:
        dimensions: set[str] = set()
        test_case = sample.test_case
        result = sample.observed_result
        args = list(test_case.args)
        lowered_args = [arg.lower() for arg in args]

        for tag in sample.tags:
            if tag.startswith("stateful_step:"):
                continue
            dimensions.add(f"tag:{tag}")
            if tag.startswith("profile_domain:"):
                dimensions.add(tag)

        dimensions.update(description_axis_tags(test_case.description))

        if any(arg in {"--help", "-h", "help"} for arg in lowered_args):
            dimensions.add("mode:help")
        if any(arg in {"--version", "-v", "version"} for arg in lowered_args):
            dimensions.add("mode:version")
        if test_case.stdin:
            dimensions.add("mode:stdin")
        if "-" in args and test_case.stdin:
            dimensions.add("mode:explicit_stdin")
        if test_case.input_files:
            dimensions.add("mode:file_input")
        if result.output_files:
            dimensions.add("mode:file_output")
        if result.exit_code != 0:
            dimensions.add("mode:nonzero_exit")
        if result.stderr:
            dimensions.add("mode:stderr")
        if result.timeout_triggered:
            dimensions.add("mode:timeout")

        for arg in args:
            if arg.startswith("-"):
                dimensions.add(f"flag:{arg.split('=', 1)[0]}")
                continue
            if arg != "-":
                dimensions.add("mode:positional")
                dimensions.add(f"arg:{arg}")

        return dimensions or {"generic"}
