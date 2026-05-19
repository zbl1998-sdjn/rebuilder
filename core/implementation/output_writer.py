"""File-system write helpers for generated codebase output."""

from __future__ import annotations

import shutil
from pathlib import Path, PurePosixPath
from typing import Dict


def clear_output_sources(output_dir: Path) -> None:
    """Remove all generated files from *output_dir*, keeping .rebuilder/."""
    output_dir.mkdir(parents=True, exist_ok=True)
    for child in output_dir.iterdir():
        if child.name == ".rebuilder":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def write_unparseable_output(output_dir: Path, text: str) -> None:
    """Write raw LLM output to .rebuilder/implementation_raw.txt for diagnosis."""
    diagnostic_dir = output_dir / ".rebuilder"
    diagnostic_dir.mkdir(parents=True, exist_ok=True)
    (diagnostic_dir / "implementation_raw.txt").write_text(text, encoding="utf-8")


def write_files(output_dir: Path, files: Dict[str, str]) -> None:
    """Write *files* dict to disk under *output_dir*."""
    output_dir.mkdir(parents=True, exist_ok=True)
    for filepath, content in files.items():
        write_generated_file(output_dir, filepath, content)


def write_generated_file(output_dir: Path, filepath: str, content: str) -> None:
    """Write a single generated file, creating parent directories as needed."""
    target = _prepare_generated_file_target(output_dir, filepath)
    target.write_text(content, encoding="utf-8")


def _prepare_generated_file_target(output_dir: Path, filepath: str) -> Path:
    root = output_dir.resolve()
    target = (output_dir / filepath).resolve()
    target.relative_to(root)

    current = output_dir
    for part in PurePosixPath(filepath).parts[:-1]:
        current = current / part
        if current.exists() and not current.is_dir():
            current.unlink()
        current.mkdir(exist_ok=True)

    if target.exists() and target.is_dir():
        shutil.rmtree(target)
    return target
