"""Utilities for parsing provider-neutral LLM output."""

from __future__ import annotations

import json
from typing import Any


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
