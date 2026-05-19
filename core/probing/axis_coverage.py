"""Aggregate-safe coverage summaries for local probe axes."""

from __future__ import annotations

from core.data_models import BehaviorSample
from core.probing.axes import description_axis_tags


def summarize_probe_axis_coverage(corpus: list[BehaviorSample]) -> dict[str, object]:
    smoke_axes: set[str] = set()
    adaptive_axes: set[str] = set()
    for sample in corpus:
        for tag in _axis_tags(sample):
            if tag.startswith("smoke_contract:"):
                smoke_axes.add(tag.removeprefix("smoke_contract:"))
            elif tag.startswith("adaptive_axis:"):
                adaptive_axes.add(tag.removeprefix("adaptive_axis:"))

    sorted_smoke_axes = sorted(smoke_axes)
    sorted_adaptive_axes = sorted(adaptive_axes)
    return {
        "smoke_contract_axis_count": len(sorted_smoke_axes),
        "adaptive_axis_count": len(sorted_adaptive_axes),
        "smoke_contract_domains": _domains(sorted_smoke_axes),
        "adaptive_domains": _domains(sorted_adaptive_axes),
        "smoke_contract_axes": sorted_smoke_axes,
        "adaptive_axes": sorted_adaptive_axes,
    }


def _axis_tags(sample: BehaviorSample) -> list[str]:
    tags = list(sample.tags)
    for tag in description_axis_tags(sample.test_case.description):
        if tag not in tags:
            tags.append(tag)
    return tags


def _domains(axes: list[str]) -> list[str]:
    return sorted({axis.split(".", 1)[0] for axis in axes if axis})
