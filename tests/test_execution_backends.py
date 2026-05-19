from pathlib import Path

import pytest

from core.data_models import TestCase
from core.execution.local import LocalExecutorBackend
from utils.executable import SandboxExecutor


@pytest.mark.asyncio
async def test_local_executor_backend_runs_python_scripts(tmp_path):
    script = tmp_path / "tool.py"
    script.write_text(
        "import sys\nprint('args=' + ','.join(sys.argv[1:]))\n",
        encoding="utf-8",
    )

    backend = LocalExecutorBackend()
    result = await backend.run(script, TestCase(name="args", args=["one", "two"]))

    assert result.exit_code == 0
    assert result.stdout.strip() == "args=one,two"


@pytest.mark.asyncio
async def test_local_executor_backend_forces_utf8_for_python_scripts(tmp_path):
    script = tmp_path / "tool.py"
    script.write_text(
        "import sys\n"
        "print(sys.stdout.encoding)\n"
        "print('straße')\n",
        encoding="utf-8",
    )

    backend = LocalExecutorBackend()
    result = await backend.run(script, TestCase(name="unicode"))

    assert result.exit_code == 0
    lines = result.stdout.splitlines()
    assert lines[0].lower() == "utf-8"
    assert lines[1] == "straße"


@pytest.mark.asyncio
async def test_local_executor_backend_closes_empty_stdin(tmp_path):
    script = tmp_path / "tool.py"
    script.write_text(
        "import sys\n"
        "data = sys.stdin.read()\n"
        "print(f'len={len(data)}')\n",
        encoding="utf-8",
    )

    result = await LocalExecutorBackend(timeout=1).run(script, TestCase(name="stdin-eof"))

    assert result.exit_code == 0
    assert result.stdout.strip() == "len=0"


@pytest.mark.asyncio
async def test_local_executor_backend_rejects_input_file_path_escape(tmp_path):
    script = tmp_path / "tool.py"
    script.write_text("print('should-not-run')\n", encoding="utf-8")
    workdir = tmp_path / "work"

    with pytest.raises(ValueError, match="unsafe input file path"):
        await LocalExecutorBackend().run_in_workdir(
            script,
            TestCase(name="escape", input_files={"../escape.txt": b"x"}),
            workdir,
        )

    assert not (tmp_path / "escape.txt").exists()


@pytest.mark.asyncio
async def test_local_executor_backend_writes_safe_nested_input_files(tmp_path):
    script = tmp_path / "tool.py"
    script.write_text(
        "from pathlib import Path\n"
        "print(Path('nested/input.txt').read_text(encoding='utf-8'))\n",
        encoding="utf-8",
    )

    result = await LocalExecutorBackend().run(
        script,
        TestCase(name="nested", input_files={"nested/input.txt": b"ok"}),
    )

    assert result.exit_code == 0
    assert result.stdout.strip() == "ok"


@pytest.mark.asyncio
async def test_local_executor_backend_filters_invalid_env_var_names(tmp_path):
    script = tmp_path / "tool.py"
    script.write_text(
        "import os\n"
        "print(os.environ.get('GOOD_NAME', 'missing'))\n"
        "print(os.environ.get('BAD-NAME', 'missing'))\n",
        encoding="utf-8",
    )

    result = await LocalExecutorBackend().run(
        script,
        TestCase(
            name="env",
            env_vars={"GOOD_NAME": "kept", "BAD-NAME": "dropped"},
        ),
    )

    assert result.exit_code == 0
    assert result.stdout.splitlines() == ["kept", "missing"]


@pytest.mark.asyncio
async def test_local_executor_backend_ignores_tempdir_cleanup_errors(tmp_path, monkeypatch):
    script = tmp_path / "tool.py"
    script.write_text("print('ok')\n", encoding="utf-8")

    captured = {}
    real_tempdir = __import__("tempfile").TemporaryDirectory

    class TrackingTemporaryDirectory:
        def __init__(self, *args, **kwargs):
            captured["ignore_cleanup_errors"] = kwargs.get("ignore_cleanup_errors")
            self._inner = real_tempdir(*args, **kwargs)

        def __enter__(self):
            return self._inner.__enter__()

        def __exit__(self, exc_type, exc, tb):
            return self._inner.__exit__(exc_type, exc, tb)

    monkeypatch.setattr("core.execution.local.tempfile.TemporaryDirectory", TrackingTemporaryDirectory)

    backend = LocalExecutorBackend()
    result = await backend.run(script, TestCase(name="cleanup"))

    assert result.exit_code == 0
    assert result.stdout.strip() == "ok"
    assert captured["ignore_cleanup_errors"] is True


@pytest.mark.asyncio
async def test_sandbox_executor_accepts_backend_injection(tmp_path):
    script = tmp_path / "tool.py"
    script.write_text("print('backend')\n", encoding="utf-8")

    executor = SandboxExecutor(script, backend=LocalExecutorBackend())
    result = await executor.run(TestCase(name="backend"))

    assert result.exit_code == 0
    assert result.stdout.strip() == "backend"


class ConstantBackend:
    async def run(self, executable, test_case):
        from core.data_models import TestResult

        return TestResult(stdout=f"{executable}:{test_case.name}", exit_code=0)


@pytest.mark.asyncio
async def test_sandbox_executor_accepts_non_path_executable_with_custom_backend():
    executor = SandboxExecutor("docker-image-reference", backend=ConstantBackend())

    result = await executor.run(TestCase(name="case"))

    assert result.stdout == "docker-image-reference:case"
