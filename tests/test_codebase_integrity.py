from core.codebase.integrity import CodebaseIntegrityChecker
from core.data_models import Codebase


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
