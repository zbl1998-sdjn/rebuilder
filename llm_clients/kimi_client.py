"""
Kimi K2.6 (Moonshot AI) client implementation.
"""

from __future__ import annotations

import json
from typing import AsyncGenerator, List, Optional

import httpx

from .base import BaseLLMClient, LLMResponse, Message


class KimiClient(BaseLLMClient):
    """Client for Moonshot AI Kimi series models (Kimi K2.6, etc.)."""

    def __init__(self, api_key: str, base_url: str, model: str = "kimi-k2-6", **kwargs):
        super().__init__(api_key, base_url, model, **kwargs)
        self.timeout = kwargs.get("timeout", 120)
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def chat(
        self,
        messages: List[Message],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> LLMResponse:
        url = f"{self.base_url}/chat/completions"

        payload = {
            "model": self.model,
            "messages": [m.model_dump() for m in messages],
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        payload.update(kwargs)

        data = await self._post_json(url, payload)

        choice = data["choices"][0]
        return self.finalize_response(LLMResponse(
            content=choice["message"]["content"],
            usage=data.get("usage", {}),
            model=data.get("model", self.model),
            finish_reason=choice.get("finish_reason", ""),
        ))

    async def _post_json(self, url: str, payload: dict) -> dict:
        async def send() -> httpx.Response:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                return await client.post(url, headers=self.headers, json=payload)

        return await self._retrying_request(send)
    
    async def chat_stream(
        self,
        messages: List[Message],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        url = f"{self.base_url}/chat/completions"
        
        payload = {
            "model": self.model,
            "messages": [m.model_dump() for m in messages],
            "stream": True,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        
        payload.update(kwargs)
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", url, headers=self.headers, json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
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
