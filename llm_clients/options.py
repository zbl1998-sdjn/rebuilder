"""Helpers for provider-neutral LLM request options."""

from __future__ import annotations

from llm_clients.base import BaseLLMClient


def configured_max_tokens(llm_client: BaseLLMClient, fallback: int) -> int:
    value = llm_client.config.get("max_tokens")
    return int(value) if value else fallback
