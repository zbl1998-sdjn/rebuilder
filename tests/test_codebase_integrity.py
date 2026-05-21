import pytest

from core.codebase.integrity import CodebaseIntegrityChecker
from core.codebase.runtime_smoke import PythonRuntimeSmokeChecker
from core.data_models import BehaviorContract, Codebase, TestResult


def test_python_integrity_checker_reports_missing_generated_imports(tmp_path):
    codebase = Codebase(
        root_path=tmp_path,
        language="python",
        files={
            "main.py": (
                "import argparse\n"
                "import query_engine\n"
                "from database import load_db\n"
            )
        },
    )

    issues = CodebaseIntegrityChecker().find_issues(codebase)

    assert [(issue.kind, issue.module, issue.path) for issue in issues] == [
        ("missing_import", "database", "main.py"),
        ("missing_import", "query_engine", "main.py"),
    ]


def test_python_integrity_checker_reports_missing_entrypoint(tmp_path):
    codebase = Codebase(
        root_path=tmp_path,
        language="python",
        files={
            "zoxide/__init__.py": "",
            "zoxide/core.py": "def main():\n    return 0\n",
        },
    )

    issues = CodebaseIntegrityChecker().find_issues(codebase, entry_point="main.py")

    assert [(issue.kind, issue.module, issue.path) for issue in issues] == [
        ("missing_entrypoint", "main.py", "main.py"),
    ]


def test_python_integrity_checker_reports_non_executable_entrypoint(tmp_path):
    codebase = Codebase(
        root_path=tmp_path,
        language="python",
        files={
            "main.py": (
                '"""Database helpers."""\n'
                "import json\n"
                "class Database:\n"
                "    pass\n"
                "def load_database():\n"
                "    return Database()\n"
            ),
        },
    )

    issues = CodebaseIntegrityChecker().find_issues(codebase, entry_point="main.py")

    assert [(issue.kind, issue.module, issue.path) for issue in issues] == [
        ("non_executable_entrypoint", "main.py", "main.py"),
    ]


def test_python_integrity_checker_reports_syntax_error(tmp_path):
    codebase = Codebase(
        root_path=tmp_path,
        language="python",
        files={
            "main.py": "def main(:\n    return 0\n",
        },
    )

    issues = CodebaseIntegrityChecker().find_issues(codebase, entry_point="main.py")

    assert issues
    assert issues[0].kind == "syntax_error"
    assert issues[0].path == "main.py"


def test_python_integrity_checker_reports_likely_truncated_syntax_output(tmp_path):
    codebase = Codebase(
        root_path=tmp_path,
        language="python",
        files={
            "main.py": (
                "def main():\n"
                "    with open('input.csv'\n"
            ),
        },
    )

    issues = CodebaseIntegrityChecker().find_issues(codebase, entry_point="main.py")

    assert issues
    assert issues[0].kind == "syntax_error"
    assert "likely truncated generated output" in issues[0].message
    assert "compact complete source files" in issues[0].message


def test_python_integrity_checker_accepts_entrypoint_guard(tmp_path):
    codebase = Codebase(
        root_path=tmp_path,
        language="python",
        files={
            "main.py": (
                "def main():\n"
                "    return 0\n"
                "if __name__ == '__main__':\n"
                "    raise SystemExit(main())\n"
            ),
        },
    )

    assert CodebaseIntegrityChecker().find_issues(codebase, entry_point="main.py") == []


def test_python_integrity_checker_accepts_local_modules_and_stdlib(tmp_path):
    codebase = Codebase(
        root_path=tmp_path,
        language="python",
        files={
            "main.py": "import argparse\nfrom database import load_db\n",
            "database.py": "def load_db():\n    return {}\n",
        },
    )

    assert CodebaseIntegrityChecker().find_issues(codebase) == []


@pytest.mark.asyncio
async def test_python_runtime_smoke_checker_reports_entrypoint_traceback(tmp_path):
    codebase = Codebase(
        root_path=tmp_path,
        language="python",
        files={
            "main.py": (
                "def main(argv):\n"
                "    return 0\n"
                "if __name__ == '__main__':\n"
                "    raise SystemExit(main())\n"
            ),
        },
    )

    issues = await PythonRuntimeSmokeChecker().find_issues(
        codebase,
        entry_point="main.py",
    )

    assert [(issue.kind, issue.path) for issue in issues] == [
        ("runtime_smoke_traceback", "main.py")
    ]
    assert "TypeError" in issues[0].message


@pytest.mark.asyncio
async def test_python_runtime_smoke_checker_reports_entrypoint_syntax_error(
    tmp_path,
    monkeypatch,
):
    async def fail_if_called(self, test_case):
        raise AssertionError("runtime smoke should classify syntax before execution")

    monkeypatch.setattr(
        "core.codebase.runtime_smoke.SandboxExecutor.run",
        fail_if_called,
    )
    codebase = Codebase(
        root_path=tmp_path,
        language="python",
        files={
            "main.py": "def main(:\n    return 0\n",
        },
    )

    issues = await PythonRuntimeSmokeChecker().find_issues(
        codebase,
        entry_point="main.py",
    )

    assert [(issue.kind, issue.path) for issue in issues] == [
        ("runtime_smoke_syntax_error", "main.py")
    ]


@pytest.mark.asyncio
async def test_python_runtime_smoke_checker_reports_likely_truncated_syntax_output(
    tmp_path,
    monkeypatch,
):
    async def fail_if_called(self, test_case):
        raise AssertionError("runtime smoke should classify syntax before execution")

    monkeypatch.setattr(
        "core.codebase.runtime_smoke.SandboxExecutor.run",
        fail_if_called,
    )
    codebase = Codebase(
        root_path=tmp_path,
        language="python",
        files={
            "main.py": (
                "def main():\n"
                "    value = open('input.csv'\n"
            ),
        },
    )

    issues = await PythonRuntimeSmokeChecker().find_issues(
        codebase,
        entry_point="main.py",
    )

    assert [(issue.kind, issue.path) for issue in issues] == [
        ("runtime_smoke_syntax_error", "main.py")
    ]
    assert "likely truncated generated output" in issues[0].message
    assert "compact complete source files" in issues[0].message


@pytest.mark.asyncio
async def test_python_runtime_smoke_checker_reports_executor_permission_denied(
    tmp_path,
    monkeypatch,
):
    async def permission_denied(self, test_case):
        return TestResult(stderr="[WinError 5] Access is denied.", exit_code=-1)

    monkeypatch.setattr(
        "core.codebase.runtime_smoke.SandboxExecutor.run",
        permission_denied,
    )
    codebase = Codebase(
        root_path=tmp_path,
        language="python",
        files={
            "main.py": (
                "def main():\n"
                "    return 0\n"
                "if __name__ == '__main__':\n"
                "    raise SystemExit(main())\n"
            ),
        },
    )

    issues = await PythonRuntimeSmokeChecker().find_issues(
        codebase,
        entry_point="main.py",
    )

    assert [(issue.kind, issue.path) for issue in issues] == [
        ("runtime_smoke_executor_permission_denied", "main.py")
    ]


@pytest.mark.asyncio
async def test_python_runtime_smoke_checker_accepts_nonzero_usage_exit(tmp_path):
    codebase = Codebase(
        root_path=tmp_path,
        language="python",
        files={
            "main.py": (
                "import sys\n"
                "def main():\n"
                "    if '--help' in sys.argv:\n"
                "        print('usage')\n"
                "        return 0\n"
                "    print('usage', file=sys.stderr)\n"
                "    return 2\n"
                "if __name__ == '__main__':\n"
                "    raise SystemExit(main())\n"
            ),
        },
    )

    issues = await PythonRuntimeSmokeChecker().find_issues(
        codebase,
        entry_point="main.py",
    )

    assert issues == []


@pytest.mark.asyncio
async def test_python_runtime_smoke_checker_runs_safe_behavior_contract_args(tmp_path):
    codebase = Codebase(
        root_path=tmp_path,
        language="python",
        files={
            "main.py": (
                "import sys\n"
                "def main():\n"
                "    if len(sys.argv) > 1 and sys.argv[1] == '--bad':\n"
                "        raise RuntimeError('dispatch exploded')\n"
                "    return 0\n"
                "if __name__ == '__main__':\n"
                "    raise SystemExit(main())\n"
            ),
        },
    )

    issues = await PythonRuntimeSmokeChecker().find_issues(
        codebase,
        entry_point="main.py",
        behavior_contracts=[
            BehaviorContract(
                test_name="bad_flag_contract",
                args=["--bad"],
                stderr="bad flag\n",
                exit_code=2,
                tags=["error_mode"],
            )
        ],
    )

    assert [(issue.kind, issue.path) for issue in issues] == [
        ("runtime_smoke_traceback", "main.py")
    ]
    assert "--bad" in issues[0].message
    assert "dispatch exploded" in issues[0].message


@pytest.mark.asyncio
async def test_python_runtime_smoke_checker_runs_safe_file_input_contracts(tmp_path):
    codebase = Codebase(
        root_path=tmp_path,
        language="python",
        files={
            "main.py": (
                "from pathlib import Path\n"
                "import sys\n"
                "def main():\n"
                "    if len(sys.argv) > 1 and sys.argv[1] == 'input.csv':\n"
                "        Path(sys.argv[1]).read_text()\n"
                "        raise RuntimeError('file dispatch exploded')\n"
                "    return 0\n"
                "if __name__ == '__main__':\n"
                "    raise SystemExit(main())\n"
            ),
        },
    )

    issues = await PythonRuntimeSmokeChecker().find_issues(
        codebase,
        entry_point="main.py",
        behavior_contracts=[
            BehaviorContract(
                test_name="file_input_contract",
                args=["input.csv"],
                input_files={"input.csv": b"name\nAda\n"},
                stdout="Ada\n",
                tags=["file_io", "smoke_contract:csv_table.file_input"],
            )
        ],
    )

    assert [(issue.kind, issue.path) for issue in issues] == [
        ("runtime_smoke_traceback", "main.py")
    ]
    assert "input.csv" in issues[0].message
    assert "file dispatch exploded" in issues[0].message


@pytest.mark.asyncio
async def test_python_runtime_smoke_checker_prioritizes_input_files_with_limited_contract_budget(
    tmp_path,
):
    codebase = Codebase(
        root_path=tmp_path,
        language="python",
        files={
            "main.py": (
                "from pathlib import Path\n"
                "import sys\n"
                "def main():\n"
                "    if len(sys.argv) > 1 and sys.argv[1] == 'input.csv':\n"
                "        Path(sys.argv[1]).read_text()\n"
                "        raise RuntimeError('file dimension smoked')\n"
                "    return 0\n"
                "if __name__ == '__main__':\n"
                "    raise SystemExit(main())\n"
            ),
        },
    )
    contracts = [
        BehaviorContract(
            test_name=f"aaa_arg_contract_{index}",
            args=[f"--flag-{index}"],
            stdout="ok\n",
            tags=["smoke_contract:csv_table.flag"],
        )
        for index in range(6)
    ]
    contracts.append(
        BehaviorContract(
            test_name="zzz_file_input_contract",
            args=["input.csv"],
            input_files={"input.csv": b"name\nAda\n"},
            stdout="Ada\n",
            tags=["file_io", "smoke_contract:csv_table.file_input"],
        )
    )

    checker = PythonRuntimeSmokeChecker(max_contract_cases=3)
    metadata = checker.plan_metadata(contracts)
    issues = await checker.find_issues(
        codebase,
        entry_point="main.py",
        behavior_contracts=contracts,
    )

    assert metadata["input_file_case_count"] == 1
    assert "input_files" in metadata["input_dimensions"]
    assert [(issue.kind, issue.path) for issue in issues] == [
        ("runtime_smoke_traceback", "main.py")
    ]
    assert "input.csv" in issues[0].message
    assert "file dimension smoked" in issues[0].message


@pytest.mark.asyncio
async def test_python_runtime_smoke_checker_keeps_file_input_when_error_contracts_fill_budget(
    tmp_path,
):
    codebase = Codebase(
        root_path=tmp_path,
        language="python",
        files={
            "main.py": (
                "from pathlib import Path\n"
                "import sys\n"
                "def main():\n"
                "    if len(sys.argv) > 1 and sys.argv[1] == 'input.csv':\n"
                "        Path(sys.argv[1]).read_text()\n"
                "        raise RuntimeError('file dimension smoked')\n"
                "    return 0\n"
                "if __name__ == '__main__':\n"
                "    raise SystemExit(main())\n"
            ),
        },
    )
    contracts = [
        BehaviorContract(
            test_name=f"aaa_error_contract_{index}",
            args=[f"--missing-value-{index}"],
            stderr="error\n",
            exit_code=2,
            tags=["error_mode"],
        )
        for index in range(8)
    ]
    contracts.append(
        BehaviorContract(
            test_name="zzz_file_input_contract",
            args=["input.csv"],
            input_files={"input.csv": b"name\nAda\n"},
            stdout="Ada\n",
            tags=["file_io", "smoke_contract:csv_table.file_input"],
        )
    )

    checker = PythonRuntimeSmokeChecker(max_contract_cases=3)
    metadata = checker.plan_metadata(contracts)
    issues = await checker.find_issues(
        codebase,
        entry_point="main.py",
        behavior_contracts=contracts,
    )

    assert metadata["input_file_case_count"] == 1
    assert "input_files" in metadata["input_dimensions"]
    assert [(issue.kind, issue.path) for issue in issues] == [
        ("runtime_smoke_traceback", "main.py")
    ]
    assert "input.csv" in issues[0].message


@pytest.mark.asyncio
async def test_python_runtime_smoke_checker_skips_unsafe_file_path_args(tmp_path):
    codebase = Codebase(
        root_path=tmp_path,
        language="python",
        files={
            "main.py": (
                "import sys\n"
                "def main():\n"
                "    if len(sys.argv) > 1 and sys.argv[1] == '../secret.txt':\n"
                "        raise RuntimeError('unsafe arg should not be smoked')\n"
                "    return 0\n"
                "if __name__ == '__main__':\n"
                "    raise SystemExit(main())\n"
            ),
        },
    )

    issues = await PythonRuntimeSmokeChecker().find_issues(
        codebase,
        entry_point="main.py",
        behavior_contracts=[
            BehaviorContract(
                test_name="unsafe_file_arg_contract",
                args=["../secret.txt"],
                input_files={"safe/input.txt": b"safe\n"},
                stdout="safe\n",
                tags=["file_io", "smoke_contract:filesystem_tool.file_input"],
            )
        ],
    )

    assert issues == []


@pytest.mark.asyncio
async def test_python_runtime_smoke_checker_runs_safe_env_contracts(tmp_path):
    codebase = Codebase(
        root_path=tmp_path,
        language="python",
        files={
            "main.py": (
                "import os\n"
                "import sys\n"
                "def main():\n"
                "    if '--probe-env' in sys.argv and os.environ.get('TERM') == 'unknown':\n"
                "        raise RuntimeError('env dispatch exploded')\n"
                "    return 0\n"
                "if __name__ == '__main__':\n"
                "    raise SystemExit(main())\n"
            ),
        },
    )

    issues = await PythonRuntimeSmokeChecker().find_issues(
        codebase,
        entry_point="main.py",
        behavior_contracts=[
            BehaviorContract(
                test_name="terminal_env_contract",
                args=["--probe-env"],
                env_vars={"TERM": "unknown", "COLUMNS": "40"},
                stdout="",
                tags=["terminal_ui", "smoke_contract:terminal_ui.term_unknown"],
            )
        ],
    )

    assert [(issue.kind, issue.path) for issue in issues] == [
        ("runtime_smoke_traceback", "main.py")
    ]
    assert "env dispatch exploded" in issues[0].message


@pytest.mark.asyncio
async def test_python_runtime_smoke_checker_distinguishes_env_only_contracts_from_no_args(tmp_path):
    codebase = Codebase(
        root_path=tmp_path,
        language="python",
        files={
            "main.py": (
                "import os\n"
                "def main():\n"
                "    if os.environ.get('TERM') == 'unknown':\n"
                "        raise RuntimeError('env-only dispatch exploded')\n"
                "    return 0\n"
                "if __name__ == '__main__':\n"
                "    raise SystemExit(main())\n"
            ),
        },
    )

    issues = await PythonRuntimeSmokeChecker().find_issues(
        codebase,
        entry_point="main.py",
        behavior_contracts=[
            BehaviorContract(
                test_name="terminal_env_only_contract",
                args=[],
                env_vars={"TERM": "unknown"},
                stdout="",
                tags=["terminal_ui", "smoke_contract:terminal_ui.term_unknown"],
            )
        ],
    )

    assert [(issue.kind, issue.path) for issue in issues] == [
        ("runtime_smoke_traceback", "main.py")
    ]
    assert "env-only dispatch exploded" in issues[0].message


@pytest.mark.asyncio
async def test_python_runtime_smoke_checker_filters_sensitive_env_contracts(tmp_path):
    codebase = Codebase(
        root_path=tmp_path,
        language="python",
        files={
            "main.py": (
                "import os\n"
                "def main():\n"
                "    if os.environ.get('API_TOKEN') == 'secret-token':\n"
                "        raise RuntimeError('secret env should not be smoked')\n"
                "    return 0\n"
                "if __name__ == '__main__':\n"
                "    raise SystemExit(main())\n"
            ),
        },
    )

    issues = await PythonRuntimeSmokeChecker().find_issues(
        codebase,
        entry_point="main.py",
        behavior_contracts=[
            BehaviorContract(
                test_name="sensitive_env_contract",
                args=[],
                env_vars={"API_TOKEN": "secret-token"},
                stdout="",
                tags=["terminal_ui"],
            )
        ],
    )

    assert issues == []
