"""Fetch cleanroom ProgramBench sample metadata from official DockerHub images."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pydantic import BaseModel


DOCKERHUB_NAMESPACE_URL = "https://hub.docker.com/v2/repositories/programbench/"


class ProgramBenchSample(BaseModel):
    """Metadata for one official ProgramBench Docker image pair."""

    instance_id: str
    docker_repository: str
    source_project: str
    cleanroom_image: str
    task_image: str
    description: str = ""
    pull_count: int = 0
    storage_size: int | None = None
    last_updated: str = ""


def parse_dockerhub_repository(repo: Dict[str, Any]) -> ProgramBenchSample:
    """Convert one DockerHub repository object into stable ProgramBench metadata."""
    docker_repository = repo["name"]
    if not isinstance(docker_repository, str) or not docker_repository:
        raise ValueError("DockerHub repository name must be a non-empty string.")
    instance_id = docker_repository.replace("_1776_", "__")
    raw_description = repo.get("description") or ""
    description = raw_description if isinstance(raw_description, str) else ""
    source_project = _source_project_from_description(description) or _source_project_from_name(docker_repository)
    image_base = f"programbench/{docker_repository}"
    return ProgramBenchSample(
        instance_id=instance_id,
        docker_repository=docker_repository,
        source_project=source_project,
        cleanroom_image=f"{image_base}:task_cleanroom",
        task_image=f"{image_base}:task",
        description=description,
        pull_count=repo.get("pull_count") or 0,
        storage_size=repo.get("storage_size"),
        last_updated=repo.get("last_updated") or "",
    )


def fetch_programbench_samples(limit: int = 10) -> List[ProgramBenchSample]:
    """Fetch official ProgramBench repository metadata without downloading task tests."""
    samples: List[ProgramBenchSample] = []
    page = 1
    page_size = min(max(limit, 1), 100)

    while len(samples) < limit:
        query = urlencode({"page": page, "page_size": page_size})
        request = Request(
            f"{DOCKERHUB_NAMESPACE_URL}?{query}",
            headers={"User-Agent": "ReBuilder ProgramBench metadata fetcher"},
        )
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))

        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise ValueError("DockerHub response must contain a JSON list of repository results.")

        for repo in payload["results"]:
            if not isinstance(repo, dict):
                continue
            try:
                samples.append(parse_dockerhub_repository(repo))
            except (KeyError, TypeError, ValueError):
                continue
            if len(samples) >= limit:
                break

        if not payload.get("next"):
            break
        page += 1

    return samples


def _source_project_from_description(description: str) -> str | None:
    match = re.search(r"ProgramBench task:\s*([^ ]+)\s*\(", description)
    return match.group(1) if match else None


def _source_project_from_name(name: str) -> str:
    owner, _, rest = name.partition("_1776_")
    repo = rest.rsplit(".", 1)[0] if rest else name
    return f"{owner}/{repo}" if rest else name
