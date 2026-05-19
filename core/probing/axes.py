"""Shared parsing for local probe axis markers."""

from __future__ import annotations


AXIS_PREFIXES = ("smoke_contract:", "adaptive_axis:")


def description_axis_tags(description: str) -> list[str]:
    """Return stable local-only axis tags embedded in a probe description."""
    tags: list[str] = []
    seen: set[str] = set()
    for token in description.split():
        normalized = token.strip(".,;()[]{}")
        if not normalized.startswith(AXIS_PREFIXES) or normalized in seen:
            continue
        tags.append(normalized)
        seen.add(normalized)
    return tags
