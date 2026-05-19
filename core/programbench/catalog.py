"""ProgramBench sample catalog helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List

from .samples import ProgramBenchSample


def load_sample_catalog(path: Path | str) -> List[ProgramBenchSample]:
    """Load sample metadata previously fetched from DockerHub."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("ProgramBench sample catalog must be valid JSON.") from exc
    if not isinstance(payload, list):
        raise ValueError("ProgramBench sample catalog must contain a JSON list.")

    samples: List[ProgramBenchSample] = []
    seen_instance_ids: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            continue
        try:
            sample = ProgramBenchSample.model_validate(item)
        except ValueError:
            continue
        if sample.instance_id in seen_instance_ids:
            raise ValueError(f"Duplicate ProgramBench sample instance_id: {sample.instance_id}")
        seen_instance_ids.add(sample.instance_id)
        samples.append(sample)
    return samples


def select_sample(samples: Iterable[ProgramBenchSample], instance_id: str) -> ProgramBenchSample:
    """Select one sample by ProgramBench instance id."""
    for sample in samples:
        if sample.instance_id == instance_id:
            return sample
    raise KeyError(f"ProgramBench sample not found: {instance_id}")
