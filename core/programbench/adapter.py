"""ProgramBench cleanroom task preparation."""

from __future__ import annotations

import subprocess
import time
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from core.programbench.samples import ProgramBenchSample
from core.programbench.workspace import CleanroomWorkspace
from core.session import RunSession


class DockerClient(Protocol):
    """Narrow Docker interface used by the cleanroom exporter."""

    def inspect_image(self, image: str) -> bool: ...

    def pull_image(self, image: str) -> None: ...

    def create_container(self, image: str) -> str: ...

    def copy_from_container(self, container_id: str, source_path: str, destination_path: Path) -> None: ...

    def remove_container(self, container_id: str) -> None: ...


@dataclass(frozen=True)
class ExportedCleanroomLayout:
    """Result of exporting a cleanroom image into a local workspace."""

    instance_id: str
    image: str
    workspace_path: Path
    source_path: str


@dataclass(frozen=True)
class PreparedProgramBenchTask:
    """A ProgramBench task ready for ReBuilder probing."""

    sample: ProgramBenchSample
    session: RunSession
    workspace: CleanroomWorkspace
    layout: ExportedCleanroomLayout


class SubprocessDockerClient:
    """Docker CLI adapter.

    This class is intentionally command-level and contains no ProgramBench policy.
    """

    def __init__(self, pull_retries: int = 3, pull_retry_delay: float = 5.0):
        self.pull_retries = pull_retries
        self.pull_retry_delay = pull_retry_delay

    def inspect_image(self, image: str) -> bool:
        result = subprocess.run(
            ["docker", "image", "inspect", image],
            text=True,
            capture_output=True,
            check=False,
        )
        return result.returncode == 0

    def pull_image(self, image: str) -> None:
        last_error: RuntimeError | None = None
        for attempt in range(self.pull_retries + 1):
            try:
                self._run(["docker", "pull", image])
                return
            except RuntimeError as exc:
                if not self._is_retryable_pull_error(exc) or attempt >= self.pull_retries:
                    raise
                last_error = exc
                time.sleep(self.pull_retry_delay)
        if last_error is not None:
            raise last_error

    def create_container(self, image: str) -> str:
        result = self._run(["docker", "create", "--network", "none", image])
        return result.stdout.strip()

    def copy_from_container(self, container_id: str, source_path: str, destination_path: Path) -> None:
        destination_path.mkdir(parents=True, exist_ok=True)
        self._run(["docker", "cp", f"{container_id}:{source_path}/.", str(destination_path)])

    def remove_container(self, container_id: str) -> None:
        subprocess.run(
            ["docker", "rm", "-f", container_id],
            text=True,
            capture_output=True,
            check=False,
        )

    def _run(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(command, text=True, capture_output=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(
                f"Command failed ({result.returncode}): {' '.join(command)}\n{result.stderr}"
            )
        return result

    def _is_retryable_pull_error(self, exc: RuntimeError) -> bool:
        text = str(exc).lower()
        return (
            "docker pull " in text
            and any(
                token in text
                for token in (
                    "eof",
                    "tls handshake timeout",
                    "context deadline exceeded",
                    "connection reset by peer",
                    "i/o timeout",
                )
            )
        )


class DockerCleanroomExporter:
    """Export official `task_cleanroom` images into a local workspace."""

    def __init__(
        self,
        docker_client: DockerClient | None = None,
        image_workspace_path: str = "/workspace",
    ):
        self.docker_client = docker_client or SubprocessDockerClient()
        self.image_workspace_path = image_workspace_path.rstrip("/") or "/workspace"

    def export(
        self,
        sample: ProgramBenchSample,
        destination_path: Path | str,
        pull: bool = False,
    ) -> ExportedCleanroomLayout:
        image = sample.cleanroom_image
        if not image.endswith(":task_cleanroom"):
            raise ValueError(f"Only task_cleanroom images are allowed for inference: {image}")

        if not self.docker_client.inspect_image(image):
            if not pull:
                raise RuntimeError(
                    f"Cleanroom image is not available locally: {image}. "
                    "Pass pull=True to download the cleanroom image."
                )
            self.docker_client.pull_image(image)

        destination = Path(destination_path)
        container_id = self.docker_client.create_container(image)
        try:
            self.docker_client.copy_from_container(
                container_id=container_id,
                source_path=self.image_workspace_path,
                destination_path=destination,
            )
        finally:
            self.docker_client.remove_container(container_id)

        return ExportedCleanroomLayout(
            instance_id=sample.instance_id,
            image=image,
            workspace_path=destination,
            source_path=self.image_workspace_path,
        )


class ProgramBenchTaskAdapter:
    """Prepare ProgramBench cleanroom tasks without touching evaluation assets."""

    def __init__(self, exporter: DockerCleanroomExporter | None = None):
        self.exporter = exporter or DockerCleanroomExporter()

    def prepare(
        self,
        sample: ProgramBenchSample,
        run_root: Path | str,
        pull: bool = False,
    ) -> PreparedProgramBenchTask:
        session = RunSession.create(
            root_path=run_root,
            task_id=sample.instance_id,
            source="programbench_cleanroom",
        )
        layout = self.exporter.export(
            sample=sample,
            destination_path=session.workspace_path,
            pull=pull,
        )
        workspace = CleanroomWorkspace.load(session.workspace_path)
        (session.root_path / "programbench_sample.json").write_text(
            sample.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return PreparedProgramBenchTask(
            sample=sample,
            session=session,
            workspace=workspace,
            layout=layout,
        )
