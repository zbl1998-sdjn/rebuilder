import asyncio
import sys

import pytest

from core.data_models import TestCase
from main import load_task
from utils.executable import SandboxExecutor


@pytest.mark.asyncio
async def test_python_script_runs_via_current_interpreter(tmp_path):
    script = tmp_path / "program.py"
    script.write_text("import sys\nprint('args=' + ','.join(sys.argv[1:]))\n", encoding="utf-8")

    result = await SandboxExecutor(script).run(TestCase(name="args", args=["a", "b"]))

    assert result.exit_code == 0
    assert result.stdout.strip() == "args=a,b"


@pytest.mark.asyncio
async def test_relative_executable_path_is_resolved_before_temp_cwd(tmp_path, monkeypatch):
    script = tmp_path / "program.py"
    script.write_text("print('ok')\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = await SandboxExecutor("program.py").run(TestCase(name="relative"))

    assert result.exit_code == 0
    assert result.stdout.strip() == "ok"


def test_load_task_prefers_script_or_wrapper_over_fake_windows_exe(tmp_path):
    task = tmp_path / "task"
    task.mkdir()
    (task / "program.py").write_text("print('py')\n", encoding="utf-8")
    (task / "program.exe").write_text("@echo off\necho fake\n", encoding="utf-8")
    (task / "README.md").write_text("docs", encoding="utf-8")

    executable, docs = load_task(task)

    assert executable.name == "program.py"
    assert docs == "docs"


def test_load_task_reads_mkd_documentation(tmp_path):
    task = tmp_path / "task"
    task.mkdir()
    (task / "program.py").write_text("print('py')\n", encoding="utf-8")
    (task / "README.mkd").write_text("mkd docs", encoding="utf-8")

    executable, docs = load_task(task)

    assert executable.name == "program.py"
    assert docs == "mkd docs"
