import subprocess

import pytest

from core.data_models import TestCase
from core.execution.wsl import WSLExecutorBackend


class CaptureRunner:
    def __init__(self):
        self.command = None
        self.input_bytes = None
        self.timeout = None

    def run(self, command, input_bytes, timeout):
        self.command = command
        self.input_bytes = input_bytes
        self.timeout = timeout
        return subprocess.CompletedProcess(command, 0, stdout=b"ok\n", stderr=b"")


@pytest.mark.asyncio
async def test_wsl_executor_runs_python_with_linux_paths_and_env(tmp_path):
    script = tmp_path / "tool.py"
    script.write_text("print('ok')\n", encoding="utf-8")
    data_dir = tmp_path / "state"
    runner = CaptureRunner()

    result = await WSLExecutorBackend(runner=runner, timeout=7).run(
        script,
        TestCase(
            name="case",
            args=["--flag", "value"],
            stdin="input",
            env_vars={"DATA_DIR": str(data_dir), "PLAIN": "x"},
        ),
    )

    assert result.stdout == "ok\n"
    assert runner.input_bytes == b"input"
    assert runner.timeout == 7
    assert runner.command[:4] == ["wsl", "--cd", runner.command[2], "--exec"]
    assert "/mnt/" in runner.command[2]
    assert runner.command[4:7] == ["timeout", "--kill-after=1s", "7s"]
    assert "python3" in runner.command
    assert any(token.startswith("DATA_DIR=/mnt/") for token in runner.command)
    assert "PLAIN=x" in runner.command
    assert runner.command[-2:] == ["--flag", "value"]


@pytest.mark.asyncio
async def test_wsl_executor_preserves_shell_sensitive_argument_literals(tmp_path):
    script = tmp_path / "tool.py"
    script.write_text("print('ok')\n", encoding="utf-8")
    runner = CaptureRunner()

    await WSLExecutorBackend(runner=runner, timeout=7).run(
        script,
        TestCase(name="case", args=[r"(\w+) (\w+)", "$2 $1", "$$bar"]),
    )

    assert runner.command[:4] == ["wsl", "--cd", runner.command[2], "--exec"]
    assert runner.command[-3:] == [r"(\w+) (\w+)", "$2 $1", "$$bar"]
    assert "bash" not in runner.command
    assert "-lc" not in runner.command


@pytest.mark.asyncio
async def test_wsl_executor_closes_empty_stdin(tmp_path):
    script = tmp_path / "tool.py"
    script.write_text("import sys\nsys.stdin.read()\nprint('done')\n", encoding="utf-8")
    runner = CaptureRunner()

    await WSLExecutorBackend(runner=runner).run(script, TestCase(name="empty-stdin"))

    assert runner.input_bytes == b""


@pytest.mark.asyncio
async def test_wsl_executor_rejects_input_file_path_escape_before_running(tmp_path):
    script = tmp_path / "tool.py"
    script.write_text("print('should-not-run')\n", encoding="utf-8")
    runner = CaptureRunner()

    with pytest.raises(ValueError, match="unsafe input file path"):
        await WSLExecutorBackend(runner=runner).run_in_workdir(
            script,
            TestCase(name="escape", input_files={"../escape.txt": b"x"}),
            tmp_path / "work",
        )

    assert runner.command is None
    assert not (tmp_path / "escape.txt").exists()
