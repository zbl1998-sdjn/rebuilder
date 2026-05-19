import subprocess
from pathlib import Path

import pytest

from core.programbench.adapter import (
    DockerCleanroomExporter,
    ProgramBenchTaskAdapter,
    SubprocessDockerClient,
)
from core.programbench.samples import ProgramBenchSample
from core.programbench.workspace import CleanroomWorkspace, CleanroomWorkspaceError


class FakeDockerClient:
    def __init__(self, image_exists=True):
        self.image_exists = image_exists
        self.commands = []

    def inspect_image(self, image):
        self.commands.append(("inspect_image", image))
        return self.image_exists

    def pull_image(self, image):
        self.commands.append(("pull_image", image))

    def create_container(self, image):
        self.commands.append(("create_container", image))
        return "container-1"

    def copy_from_container(self, container_id, source_path, destination_path):
        self.commands.append(("copy_from_container", container_id, source_path, Path(destination_path)))
        Path(destination_path).mkdir(parents=True, exist_ok=True)
        (Path(destination_path) / "executable").write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
        (Path(destination_path) / "README.md").write_text("usage docs", encoding="utf-8")

    def remove_container(self, container_id):
        self.commands.append(("remove_container", container_id))


def sample():
    return ProgramBenchSample(
        instance_id="owner__repo.abcdef0",
        docker_repository="owner_1776_repo.abcdef0",
        source_project="owner/repo",
        cleanroom_image="programbench/owner_1776_repo.abcdef0:task_cleanroom",
        task_image="programbench/owner_1776_repo.abcdef0:task",
    )


def test_exporter_uses_only_task_cleanroom_image_by_default(tmp_path):
    docker = FakeDockerClient()
    exporter = DockerCleanroomExporter(docker_client=docker)

    layout = exporter.export(sample(), tmp_path / "workspace")

    assert layout.image == "programbench/owner_1776_repo.abcdef0:task_cleanroom"
    assert ("inspect_image", layout.image) in docker.commands
    used_images = [command[1] for command in docker.commands if command[0] in {"inspect_image", "create_container"}]
    assert "programbench/owner_1776_repo.abcdef0:task" not in used_images
    assert layout.workspace_path == tmp_path / "workspace"


def test_exporter_requires_explicit_pull_when_image_is_missing(tmp_path):
    exporter = DockerCleanroomExporter(docker_client=FakeDockerClient(image_exists=False))

    with pytest.raises(RuntimeError, match="not available locally"):
        exporter.export(sample(), tmp_path / "workspace", pull=False)


def test_workspace_finds_executable_and_docs(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    executable = workspace / "executable"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    docs = workspace / "README.md"
    docs.write_text("docs", encoding="utf-8")

    loaded = CleanroomWorkspace.load(workspace)

    assert loaded.executable_path == executable
    assert loaded.documentation == "docs"


def test_workspace_loads_mkd_readme_and_advanced_docs(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    executable = workspace / "executable"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    (workspace / "README.mkd").write_text("readme docs", encoding="utf-8")
    (workspace / "ADVANCED.mkd").write_text("advanced docs", encoding="utf-8")

    loaded = CleanroomWorkspace.load(workspace)

    assert "readme docs" in loaded.documentation
    assert "advanced docs" in loaded.documentation
    assert loaded.documentation.index("readme docs") < loaded.documentation.index("advanced docs")


def test_workspace_rejects_evaluation_artifacts(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "executable").write_text("#!/bin/sh\n", encoding="utf-8")
    (workspace / "README.md").write_text("docs", encoding="utf-8")
    (workspace / "tests.json").write_text("{}", encoding="utf-8")

    with pytest.raises(CleanroomWorkspaceError, match="evaluation artifact"):
        CleanroomWorkspace.load(workspace)


def test_task_adapter_prepares_session_workspace(tmp_path):
    docker = FakeDockerClient()
    exporter = DockerCleanroomExporter(docker_client=docker)
    adapter = ProgramBenchTaskAdapter(exporter=exporter)

    prepared = adapter.prepare(sample(), run_root=tmp_path / "runs")

    assert prepared.session.task_id == "owner__repo.abcdef0"
    assert prepared.workspace.documentation == "usage docs"
    assert prepared.session.workspace_path == prepared.workspace.root_path
    assert (prepared.session.root_path / "programbench_sample.json").exists()


def test_subprocess_docker_client_retries_transient_pull_eof(monkeypatch):
    calls = []

    def fake_run(command, text, capture_output, check, timeout):
        calls.append(command)
        if len(calls) < 3:
            return subprocess.CompletedProcess(
                command,
                1,
                stdout="",
                stderr='Error response from daemon: Head "https://registry-1.docker.io/...": EOF',
            )
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr("core.programbench.adapter.subprocess.run", fake_run)
    monkeypatch.setattr("core.programbench.adapter.time.sleep", lambda *_args, **_kwargs: None)

    client = SubprocessDockerClient(pull_retries=3, pull_retry_delay=0)
    client.pull_image("programbench/example:task_cleanroom")

    assert calls == [
        ["docker", "pull", "programbench/example:task_cleanroom"],
        ["docker", "pull", "programbench/example:task_cleanroom"],
        ["docker", "pull", "programbench/example:task_cleanroom"],
    ]


def test_subprocess_docker_client_does_not_retry_non_retryable_pull_error(monkeypatch):
    calls = []

    def fake_run(command, text, capture_output, check, timeout):
        calls.append(command)
        return subprocess.CompletedProcess(
            command,
            1,
            stdout="",
            stderr="pull access denied for programbench/example",
        )

    monkeypatch.setattr("core.programbench.adapter.subprocess.run", fake_run)
    monkeypatch.setattr("core.programbench.adapter.time.sleep", lambda *_args, **_kwargs: None)

    client = SubprocessDockerClient(pull_retries=3, pull_retry_delay=0)

    with pytest.raises(RuntimeError, match="pull access denied"):
        client.pull_image("programbench/example:task_cleanroom")

    assert calls == [["docker", "pull", "programbench/example:task_cleanroom"]]


def test_subprocess_docker_client_sets_timeout_on_docker_commands(monkeypatch, tmp_path):
    calls = []

    def fake_run(command, text, capture_output, check, timeout):
        calls.append((command, timeout))
        stdout = "container-1\n" if command[:2] == ["docker", "create"] else ""
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr("core.programbench.adapter.subprocess.run", fake_run)

    client = SubprocessDockerClient(command_timeout=12)
    assert client.inspect_image("programbench/example:task_cleanroom")
    client.pull_image("programbench/example:task_cleanroom")
    assert client.create_container("programbench/example:task_cleanroom") == "container-1"
    client.copy_from_container("container-1", "/workspace", tmp_path / "workspace")
    client.remove_container("container-1")

    assert calls == [
        (["docker", "image", "inspect", "programbench/example:task_cleanroom"], 12),
        (["docker", "pull", "programbench/example:task_cleanroom"], 12),
        (["docker", "create", "--network", "none", "programbench/example:task_cleanroom"], 12),
        (["docker", "cp", "container-1:/workspace/.", str(tmp_path / "workspace")], 12),
        (["docker", "rm", "-f", "container-1"], 12),
    ]
