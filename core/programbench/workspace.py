"""Cleanroom workspace loading and validation."""

from __future__ import annotations

from pathlib import Path


class CleanroomWorkspaceError(RuntimeError):
    """Raised when an exported workspace violates the cleanroom contract."""


class CleanroomWorkspace:
    """A local ProgramBench cleanroom workspace."""

    EVALUATION_ARTIFACT_NAMES = {
        "tests.json",
        "submission.tar.gz",
    }
    EVALUATION_ARTIFACT_SUFFIXES = {
        ".eval.json",
    }

    def __init__(self, root_path: Path, executable_path: Path, documentation: str):
        self.root_path = root_path
        self.executable_path = executable_path
        self.documentation = documentation

    @classmethod
    def load(cls, root_path: Path | str) -> "CleanroomWorkspace":
        root = Path(root_path)
        cls._assert_no_evaluation_artifacts(root)
        executable = cls._find_executable(root)
        documentation = cls._load_documentation(root)
        return cls(root_path=root, executable_path=executable, documentation=documentation)

    @classmethod
    def _assert_no_evaluation_artifacts(cls, root: Path) -> None:
        for path in root.rglob("*"):
            if path.name in cls.EVALUATION_ARTIFACT_NAMES:
                raise CleanroomWorkspaceError(f"Found evaluation artifact: {path}")
            if any(path.name.endswith(suffix) for suffix in cls.EVALUATION_ARTIFACT_SUFFIXES):
                raise CleanroomWorkspaceError(f"Found evaluation artifact: {path}")

    @staticmethod
    def _find_executable(root: Path) -> Path:
        candidates = [
            root / "executable",
            root / "program",
            root / "program.py",
            root / "program.bat",
            root / "program.cmd",
            root / "program.exe",
            root / "a.out",
        ]
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate
        raise CleanroomWorkspaceError(f"No executable found in cleanroom workspace: {root}")

    @staticmethod
    def _load_documentation(root: Path) -> str:
        for name in ("README.md", "doc.txt", "documentation.txt"):
            path = root / name
            if path.exists() and path.is_file():
                return path.read_text(encoding="utf-8")
        return ""
