"""Utilities for parsing provider-neutral LLM output."""

from __future__ import annotations

import base64
import binascii
import json
from typing import Any, List

from core.data_models import TestCase


def extract_json_value(text: str) -> Any:
    """Return the first valid JSON object or array embedded in an LLM response."""
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char not in "{[":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, (dict, list)):
            return value
    raise json.JSONDecodeError("No JSON value found", text, 0)


def extract_json_object(text: str) -> dict[str, Any]:
    """Return the first valid JSON object embedded in an LLM response."""
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise json.JSONDecodeError("No JSON object found", text, 0)


def parse_llm_test_cases(text: str) -> List[TestCase]:
    """Parse an LLM response into TestCase objects.

    Accepts either a top-level JSON array of cases or an object with a
    ``test_cases`` field. Unknown shapes return an empty list. Callers are
    responsible for any domain-specific sanitization or deduplication.
    """
    try:
        data = extract_json_value(text.strip())
    except (json.JSONDecodeError, ValueError):
        return []

    if isinstance(data, dict) and "test_cases" in data:
        data = data["test_cases"]
    if not isinstance(data, list):
        return []

    cases: List[TestCase] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            cases.append(
                TestCase(
                    name=item.get("name", "unnamed"),
                    args=list(item.get("args", []) or []),
                    stdin=item.get("stdin", "") or "",
                    input_files=_normalize_input_files(item.get("input_files", {}) or {}),
                    description=item.get("description", "") or "",
                )
            )
        except ValueError:
            continue
    return cases


def _normalize_input_files(value: Any) -> dict[str, bytes]:
    if not isinstance(value, dict):
        return {}

    normalized: dict[str, bytes] = {}
    for filename, content in value.items():
        if not isinstance(filename, str) or not filename:
            continue
        materialized = _normalize_input_file_content(content)
        if materialized is None:
            continue
        normalized[filename] = materialized
    return normalized


def _normalize_input_file_content(value: Any) -> bytes | None:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    if not isinstance(value, dict):
        return None

    if value.get("__type__") != "bytes":
        return None

    encoded = value.get("base64")
    if not isinstance(encoded, str):
        return None
    try:
        return base64.b64decode(encoded.encode("ascii"), validate=True)
    except (binascii.Error, ValueError):
        return None
