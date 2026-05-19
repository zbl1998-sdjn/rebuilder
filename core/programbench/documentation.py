"""Cleanroom documentation discovery for ProgramBench workspaces."""

from __future__ import annotations

from pathlib import Path


DOCUMENTATION_FILENAMES: tuple[str, ...] = (
    "README.md",
    "README.mkd",
    "README.markdown",
    "README",
    "doc.txt",
    "docs.txt",
    "documentation.txt",
    "DOCUMENTATION.md",
    "DOCUMENTATION.mkd",
    "DOCS.md",
    "DOCS.mkd",
    "ADVANCED.md",
    "ADVANCED.mkd",
    "ADVANCED.markdown",
    "USAGE.md",
    "USAGE.mkd",
    "USAGE.txt",
)


def find_documentation_paths(root: Path | str) -> list[Path]:
    """Return known cleanroom documentation files in stable priority order."""
    root_path = Path(root)
    files_by_name = {
        path.name.casefold(): path
        for path in root_path.iterdir()
        if path.exists() and path.is_file()
    }

    paths: list[Path] = []
    seen: set[str] = set()
    for filename in DOCUMENTATION_FILENAMES:
        path = files_by_name.get(filename.casefold())
        if path is None:
            continue
        key = str(path.resolve(strict=False)).casefold()
        if key in seen:
            continue
        paths.append(path)
        seen.add(key)
    return paths


def load_documentation(root: Path | str) -> str:
    """Load all known cleanroom documentation files from a task workspace."""
    loaded: list[tuple[str, str]] = []
    for path in find_documentation_paths(root):
        loaded.append((path.name, path.read_text(encoding="utf-8")))

    if not loaded:
        return ""
    if len(loaded) == 1:
        return loaded[0][1]
    return "\n\n".join(f"## {name}\n\n{text.rstrip()}" for name, text in loaded)
