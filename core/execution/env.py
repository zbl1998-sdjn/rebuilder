"""Shared environment-variable safety helpers."""

from __future__ import annotations

import re
from collections.abc import Mapping


SENSITIVE_ENV_TOKENS = {"AUTH", "CREDENTIAL", "KEY", "PASS", "PASSWORD", "SECRET", "TOKEN"}


def valid_env_name(name: object) -> bool:
    return isinstance(name, str) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name) is not None


def sensitive_env_name(name: str) -> bool:
    parts = [part for part in re.split(r"[^A-Za-z0-9]+|_", name.upper()) if part]
    return any(part in SENSITIVE_ENV_TOKENS for part in parts)


def safe_env_vars(
    env_vars: Mapping[str, object],
    *,
    max_value_chars: int = 256,
) -> dict[str, str]:
    safe: dict[str, str] = {}
    for name, value in sorted(env_vars.items()):
        if not valid_env_name(name) or sensitive_env_name(name):
            continue
        text = value if isinstance(value, str) else str(value)
        if "\x00" in text or len(text) > max_value_chars:
            continue
        safe[name] = text
    return safe
