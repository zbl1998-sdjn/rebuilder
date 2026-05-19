"""Parse LLM-generated text output into a Codebase object."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict

from core.data_models import ArchitectureBlueprint, Codebase
from core.implementation.entrypoint import (
    determine_executable,
    normalize_output_path,
    python_entry_path,
)
from core.implementation.output_writer import write_generated_file, write_unparseable_output
from core.llm_output import extract_json_value


def parse_codebase(
    text: str,
    blueprint: ArchitectureBlueprint,
    output_dir: Path,
) -> Codebase:
    """Parse file-delimited LLM output into a Codebase object and write to disk."""
    files: Dict[str, str] = {}
    build_script: str | None = None

    files.update(_parse_json_manifest(text))

    file_pattern = r"---\s*FILE:\s*(.+?)\s*---\s*\r?\n(.*?)\r?\n---\s*END FILE\s*---"
    for match in re.finditer(file_pattern, text, re.DOTALL | re.IGNORECASE):
        filepath = normalize_output_path(match.group(1))
        if filepath:
            content = match.group(2).strip("\r\n")
            files[filepath] = content

    build_pattern = r"---\s*BUILD SCRIPT:\s*(.+?)\s*---\n(.*?)\n---\s*END BUILD\s*---"
    build_match = re.search(build_pattern, text, re.DOTALL | re.IGNORECASE)
    if build_match:
        build_script = build_match.group(2).strip("\r\n")

    if not files:
        for i, (info, content) in enumerate(_parse_code_blocks(text)):
            filepath = _code_block_path(info, i, blueprint)
            if filepath:
                files[filepath] = content.strip("\r\n")

    files = {
        filepath: _normalize_file_content(content)
        for filepath, content in files.items()
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    generation_metadata = {
        "parse_status": "ok" if files else "no_files",
        "raw_output_chars": len(text),
    }
    if not files:
        write_unparseable_output(output_dir, text)

    for filepath, content in files.items():
        write_generated_file(output_dir, filepath, content)

    executable_path = determine_executable(output_dir, blueprint, build_script)

    return Codebase(
        root_path=output_dir,
        language=blueprint.language,
        files=files,
        build_script=build_script,
        executable_path=executable_path,
        generation_metadata=generation_metadata,
    )


# ---------------------------------------------------------------------------
# JSON manifest parsers
# ---------------------------------------------------------------------------

def _parse_json_manifest(text: str) -> Dict[str, str]:
    """Parse a JSON file manifest if the model emitted one."""
    try:
        data = extract_json_value(text)
    except json.JSONDecodeError:
        data = None

    if isinstance(data, list):
        parsed = _parse_file_items(data)
        if parsed:
            return parsed
    elif isinstance(data, dict):
        parsed = _parse_json_manifest_dict(data)
        if parsed:
            return parsed

    return _parse_jsonish_manifest(text)


def _parse_json_manifest_dict(data: dict) -> Dict[str, str]:
    raw_files = data.get("files", {})
    parsed: Dict[str, str] = {}
    if isinstance(raw_files, dict):
        for path, content in raw_files.items():
            filepath = normalize_output_path(str(path))
            if filepath and isinstance(content, str):
                parsed[filepath] = content
        return parsed
    if isinstance(raw_files, list):
        parsed.update(_parse_file_items(raw_files))
    return parsed


def _parse_jsonish_manifest(text: str) -> Dict[str, str]:
    """Recover a single file from a JSON-like manifest with unescaped code quotes."""
    path_match = re.search(r'"path"\s*:\s*"(?P<path>[^"]+)"', text)
    content_match = re.search(r'"content"\s*:\s*"', text)
    if not path_match or not content_match:
        return {}

    filepath = normalize_output_path(path_match.group("path"))
    if not filepath:
        return {}

    content_start = content_match.end()
    tail = text[content_start:]
    end_matches = list(
        re.finditer(r'"\s*}\s*]\s*,\s*"build_script"', tail, re.DOTALL)
    )
    if not end_matches:
        truncated = _parse_truncated_jsonish_manifest(filepath, tail)
        if truncated:
            return truncated
        return {}

    encoded = tail[: end_matches[-1].start()]
    return {filepath: _decode_jsonish_content(encoded)}


def _parse_truncated_jsonish_manifest(filepath: str, tail: str) -> Dict[str, str]:
    """Recover content when the JSON manifest is truncated before build_script."""
    candidate = tail
    fence_index = candidate.find("\n```")
    if fence_index >= 0:
        candidate = candidate[:fence_index]
    candidate = re.sub(r'"\s*}\s*]\s*}\s*$', "", candidate, flags=re.DOTALL)
    decoded = _decode_jsonish_content(candidate).strip("\r\n")
    if not _looks_like_source_code(decoded):
        return {}
    return {filepath: decoded}


def _looks_like_source_code(text: str) -> bool:
    lowered = text.lower()
    markers = (
        "def ",
        "class ",
        "import ",
        "from ",
        "fn ",
        "function ",
        "#include",
        "package ",
        "public ",
        "int main(",
        "if __name__ ==",
    )
    return any(marker in lowered for marker in markers)


def _decode_jsonish_content(encoded: str) -> str:
    return (
        encoded.replace("\\r\\n", "\n")
        .replace("\\n", "\n")
        .replace("\\t", "\t")
        .replace('\\"', '"')
        .replace("\\\\", "\\")
    )


def _parse_file_items(raw_files: list) -> Dict[str, str]:
    parsed: Dict[str, str] = {}
    for item in raw_files:
        if not isinstance(item, dict):
            continue
        raw_path = (
            item.get("path")
            or item.get("file")
            or item.get("filename")
            or item.get("name")
        )
        content = (
            item.get("content")
            or item.get("source")
            or item.get("code")
            or item.get("text")
        )
        if raw_path and isinstance(content, str):
            filepath = normalize_output_path(str(raw_path))
            if filepath:
                parsed[filepath] = content
    return parsed


# ---------------------------------------------------------------------------
# Code-block parsers
# ---------------------------------------------------------------------------

def _parse_code_blocks(text: str) -> list[tuple[str, str]]:
    return [
        (match.group("info").strip(), match.group("content"))
        for match in re.finditer(
            r"```(?P<info>[^\n`]*)\r?\n(?P<content>.*?)```",
            text,
            re.DOTALL,
        )
    ]


def _code_block_path(
    info: str,
    index: int,
    blueprint: ArchitectureBlueprint,
) -> str | None:
    explicit = _path_from_code_block_info(info)
    if explicit:
        return explicit

    language = (info.split() or [""])[0].lower()
    if blueprint.language.lower() == "python" and index == 0:
        return python_entry_path(blueprint)
    extension = {
        "python": "py",
        "py": "py",
        "bash": "sh",
        "sh": "sh",
        "shell": "sh",
        "javascript": "js",
        "js": "js",
        "typescript": "ts",
        "ts": "ts",
    }.get(language, "txt")
    return f"module_{index}.{extension}"


def _path_from_code_block_info(info: str) -> str | None:
    for token in info.replace(",", " ").split():
        if "=" in token:
            key, value = token.split("=", 1)
            if key.lower() in {"file", "filename", "path"}:
                normalized = normalize_output_path(value.strip("'\""))
                if normalized:
                    return normalized
        elif "." in token and "/" not in token[:1]:
            normalized = normalize_output_path(token.strip("'\""))
            if normalized:
                return normalized
    return None


# ---------------------------------------------------------------------------
# Content normalisation
# ---------------------------------------------------------------------------

def _normalize_file_content(content: str) -> str:
    stripped = content.strip("\r\n")
    match = re.match(r"^```[^\n`]*\r?\n(?P<body>.*?)\r?\n```$", stripped, re.DOTALL)
    if match:
        return match.group("body").strip("\r\n")
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        return "\n".join(lines[1:]).strip("\r\n")
    return content
