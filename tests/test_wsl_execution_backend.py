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
    assert runner.command[:3] == ["wsl", "bash", "-lc"]
    shell_script = runner.command[3]
    assert "python3" in shell_script
    assert "timeout --kill-after=1s 7s" in shell_script
    assert "/mnt/" in shell_script
    assert "DATA_DIR=/mnt/" in shell_script
    assert "PLAIN=x" in shell_script
    assert "--flag value" in shell_script
