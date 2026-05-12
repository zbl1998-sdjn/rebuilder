"""ProgramBench sample catalog helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List

from .samples import ProgramBenchSample


def load_sample_catalog(path: Path | str) -> List[ProgramBenchSample]:
    """Load sample metadata previously fetched from DockerHub."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return [ProgramBenchSample.model_validate(item) for item in payload]


def select_sample(samples: Iterable[ProgramBenchSample], instance_id: str) -> ProgramBenchSample:
    """Select one sample by ProgramBench instance id."""
    for sample in samples:
        if sample.instance_id == instance_id:
            return sample
    raise KeyError(f"ProgramBench sample not found: {instance_id}")
