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
    assert command[:3] == ["docker", "run", "--rm"]
    assert "--network" in command
    assert "none" in command
    assert "-v" in command
    assert "/workspace/executable" in command
    assert "--help" in command
    assert input_bytes == b"in"
    assert timeout == 10.0
    assert result.stdout == "ok\n"
    assert result.exit_code == 0


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
async def test_docker_backend_rejects_non_cleanroom_images():
    backend = DockerExecutorBackend(runner=FakeDockerRunner())
    executable = DockerExecutable(
        image="programbench/owner_1776_repo.abcdef0:task",
        executable_path="/workspace/executable",
    )

    with pytest.raises(ValueError, match="task_cleanroom"):
        await backend.run(executable, TestCase(name="bad"))
