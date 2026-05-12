import subprocess

import pytest

from core.data_models import TestCase
from core.execution.docker import DockerExecutorBackend, DockerExecutable


class FakeDockerRunner:
    def __init__(self, result=None):
        self.calls = []
        self.result = result or subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=b"ok\n",
            stderr=b"",
        )

    def run(self, command, input_bytes, timeout):
        self.calls.append((command, input_bytes, timeout))
        return self.result


@pytest.mark.asyncio
async def test_docker_backend_runs_with_network_disabled_and_mounted_workdir():
    runner = FakeDockerRunner()
    backend = DockerExecutorBackend(runner=runner)
    executable = DockerExecutable(
        image="programbench/owner_1776_repo.abcdef0:task_cleanroom",
        executable_path="/workspace/executable",
    )

    result = await backend.run(executable, TestCase(name="help", args=["--help"], stdin="in"))

    command, input_bytes, timeout = runner.calls[0]
    assert command[:4] == ["docker", "run", "--rm", "-i"]
    assert "--name" in command
    assert command[command.index("--name") + 1].startswith("rebuilder-")
    assert "--network" in command
    assert "none" in command
    assert "-v" in command
    assert "/workspace/executable" in command
    assert "--help" in command
    assert input_bytes == b"in"
    assert timeout == 10.0
    assert result.stdout == "ok\n"
    assert result.exit_code == 0


def test_subprocess_docker_runner_removes_named_container_on_timeout(monkeypatch):
    removed = []

    class HangingProcess:
        returncode = None

        def communicate(self, input=None, timeout=None):
            if timeout is not None:
                raise subprocess.TimeoutExpired(["docker"], timeout)
            return b"", b""

        def kill(self):
            self.returncode = -9

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: HangingProcess())

    def fake_run(command, **kwargs):
        removed.append(command)
        return subprocess.CompletedProcess(command, 0, b"", b"")

    monkeypatch.setattr(subprocess, "run", fake_run)

    from core.execution.docker import SubprocessDockerRunner

    runner = SubprocessDockerRunner()

    with pytest.raises(subprocess.TimeoutExpired):
        runner.run(
            ["docker", "run", "--rm", "-i", "--name", "rebuilder-test", "image"],
            b"",
            0.01,
        )

    assert removed == [["docker", "rm", "-f", "rebuilder-test"]]


@pytest.mark.asyncio
async def test_docker_backend_passes_env_vars_and_can_reuse_workdir(tmp_path):
    runner = FakeDockerRunner()
    backend = DockerExecutorBackend(runner=runner, timeout=3)
    executable = DockerExecutable(
        image="programbench/owner_1776_repo.abcdef0:task_cleanroom",
        executable_path="/workspace/executable",
    )
    test_case = TestCase(
        name="stateful",
        args=["query"],
        env_vars={"_ZO_DATA_DIR": ".rebuilder-state/zoxide", "BAD-NAME": "ignored"},
    )

    await backend.run_in_workdir(executable, test_case, tmp_path)
    await backend.run_in_workdir(executable, test_case, tmp_path)

    first_command, _input_bytes, timeout = runner.calls[0]
    second_command, _input_bytes, _timeout = runner.calls[1]
    assert timeout == 3
    assert "-e" in first_command
    assert "_ZO_DATA_DIR=.rebuilder-state/zoxide" in first_command
    assert "BAD-NAME=ignored" not in first_command
    assert first_command[first_command.index("-v") + 1] == second_command[second_command.index("-v") + 1]


@pytest.mark.asyncio
async def test_docker_backend_closes_empty_stdin():
    runner = FakeDockerRunner()
    backend = DockerExecutorBackend(runner=runner)
    executable = DockerExecutable(
        image="programbench/owner_1776_repo.abcdef0:task_cleanroom",
        executable_path="/workspace/executable",
    )

    await backend.run(executable, TestCase(name="empty-stdin"))

    _command, input_bytes, _timeout = runner.calls[0]
    assert input_bytes == b""


@pytest.mark.asyncio
async def test_docker_backend_rejects_non_cleanroom_images():
    backend = DockerExecutorBackend(runner=FakeDockerRunner())
    executable = DockerExecutable(
        image="programbench/owner_1776_repo.abcdef0:task",
        executable_path="/workspace/executable",
    )

    with pytest.raises(ValueError, match="task_cleanroom"):
        await backend.run(executable, TestCase(name="bad"))
