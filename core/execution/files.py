"""Shared file path safety helpers for executor work directories."""

from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Mapping


class UnsafeInputFilePathError(ValueError):
    """Raised when an untrusted test input file path escapes the workdir."""


def _unsafe_input_file_path(filename: object) -> UnsafeInputFilePathError:
    return UnsafeInputFilePathError(f"unsafe input file path: {filename!r}")


def safe_input_file_relative_path(filename: str) -> Path:
    """Return a normalized relative path for a test input file.

    Test cases can be produced by LLM output, so file names are treated as
    untrusted. Only simple relative paths inside the executor workdir are
    accepted.
    """
    if not isinstance(filename, str) or filename == "":
        raise _unsafe_input_file_path(filename)
    if "\x00" in filename:
        raise _unsafe_input_file_path(filename)

    normalized = filename.replace("\\", "/")
    windows_path = PureWindowsPath(filename)
    posix_path = PurePosixPath(normalized)
    if windows_path.drive or windows_path.is_absolute() or posix_path.is_absolute():
        raise _unsafe_input_file_path(filename)

    parts = normalized.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise _unsafe_input_file_path(filename)

    return Path(*parts)


def safe_input_file_path(workdir: Path, filename: str) -> Path:
    """Resolve an input file path and prove it stays inside workdir."""
    root = workdir.resolve(strict=False)
    target = (root / safe_input_file_relative_path(filename)).resolve(strict=False)
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise _unsafe_input_file_path(filename) from exc
    return target


def safe_input_file_names(input_files: Mapping[str, object]) -> set[str]:
    """Normalize safe input file names for output-file filtering."""
    return {
        safe_input_file_relative_path(filename).as_posix()
        for filename in input_files
    }
