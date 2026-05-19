"""Entry-point path and executable inference helpers."""

from __future__ import annotations

from pathlib import Path

from core.data_models import ArchitectureBlueprint


def python_entry_path(blueprint: ArchitectureBlueprint) -> str:
    """Return the normalised Python entry-point file path for *blueprint*."""
    entry = blueprint.entry_point or "main.py"
    if (
        "." in entry
        and "/" not in entry
        and "\\" not in entry
        and not entry.endswith(".py")
    ):
        entry = entry.replace(".", "/")
    if not entry.endswith(".py"):
        entry += ".py"
    return normalize_output_path(entry) or "main.py"


def expected_entry_point(blueprint: ArchitectureBlueprint) -> str | None:
    """Return the expected entry-point path string (language-aware)."""
    if blueprint.language.lower() != "python":
        return blueprint.entry_point
    return python_entry_path(blueprint)


def determine_executable(
    output_dir: Path,
    blueprint: ArchitectureBlueprint,
    build_script: str | None,
) -> Path | None:
    """Try to determine the path to the built executable."""
    if blueprint.language.lower() == "python":
        entry = python_entry_path(blueprint)
        candidate = output_dir / entry
        if candidate.exists():
            return candidate
    return None


def normalize_output_path(raw_path: str) -> str | None:
    """Validate and normalise a file path emitted by the LLM."""
    from pathlib import PurePosixPath

    normalized = raw_path.strip().strip("`").replace("\\", "/")
    if not normalized:
        return None
    pure = PurePosixPath(normalized)
    if pure.is_absolute() or any(part in {"..", ""} for part in pure.parts):
        return None
    if pure.parts and ":" in pure.parts[0]:
        return None
    return pure.as_posix()
