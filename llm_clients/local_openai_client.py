"""
Local OpenAI-compatible client implementation.

This provider is intentionally limited to loopback endpoints so ReBuilder can
use local model servers without sending cleanroom context to external services.
"""

from __future__ import annotations

import ipaddress
import json
from typing import AsyncGenerator, List, Optional
from urllib.parse import urlparse

import httpx

from .base import BaseLLMClient, LLMResponse, Message


class LocalOpenAIClient(BaseLLMClient):
    """Client for loopback OpenAI-compatible chat/completions endpoints."""

    def __init__(self, api_key: str, base_url: str, model: str, **kwargs):
        if not _is_loopback_url(base_url):
            raise ValueError("local_openai base_url must point to a loopback host")
        super().__init__(api_key, base_url, model, **kwargs)
        self.timeout = kwargs.get("timeout", 120)
        phase_timeout = min(float(self.timeout), 30.0)
        self.http_timeout = httpx.Timeout(
            float(self.timeout),
            connect=phase_timeout,
            write=phase_timeout,
            pool=phase_timeout,
        )
        self.default_temperature = kwargs.get("temperature")
        self.default_max_tokens = kwargs.get("max_tokens")
        self.headers = {"Content-Type": "application/json"}
        if _usable_api_key(api_key):
            self.headers["Authorization"] = f"Bearer {api_key}"

    async def chat(
        self,
        messages: List[Message],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> LLMResponse:
        url = f"{self.base_url}/chat/completions"

        payload: dict[str, object] = {
            "model": self.model,
            "messages": [m.model_dump() for m in messages],
        }
        if temperature is None:
            temperature = self.default_temperature
        if max_tokens is None:
            max_tokens = self.default_max_tokens
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        payload.update(kwargs)

        data = await self._post_json(url, payload)

        choice = data["choices"][0]
        return self.finalize_response(
            LLMResponse(
                content=choice["message"]["content"],
                usage=data.get("usage", {}),
                model=data.get("model", self.model),
                finish_reason=choice.get("finish_reason", ""),
            )
        )

    async def _post_json(self, url: str, payload: dict) -> dict:
        async def send() -> httpx.Response:
            async with httpx.AsyncClient(timeout=self.http_timeout) as client:
                return await client.post(url, headers=self.headers, json=payload)

        return await self._retrying_request(send)

    async def chat_stream(
        self,
        messages: List[Message],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        url = f"{self.base_url}/chat/completions"

        payload: dict[str, object] = {
            "model": self.model,
            "messages": [m.model_dump() for m in messages],
            "stream": True,
        }
        if temperature is None:
            temperature = self.default_temperature
        if max_tokens is None:
            max_tokens = self.default_max_tokens
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        payload.update(kwargs)

        async with httpx.AsyncClient(timeout=self.http_timeout) as client:
            async with client.stream("POST", url, headers=self.headers, json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk["choices"][0]["delta"]
                        if "content" in delta:
                            yield delta["content"]
                    except (json.JSONDecodeError, KeyError):
                        continue


def _usable_api_key(api_key: str) -> bool:
    stripped = (api_key or "").strip()
    return bool(stripped) and not stripped.startswith("${")


def _is_loopback_url(base_url: str) -> bool:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"}:
        return False
    hostname = parsed.hostname
    if hostname is None:
        return False
    if hostname.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False
