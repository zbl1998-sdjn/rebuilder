"""
GLM-5.1 (Zhipu AI) client implementation.
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator, List, Optional

import httpx

from .base import BaseLLMClient, LLMResponse, Message


class GLMClient(BaseLLMClient):
    """Client for Zhipu AI GLM series models (GLM-5.1, etc.)."""
    
    def __init__(self, api_key: str, base_url: str, model: str = "glm-5.1", **kwargs):
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
        self.default_thinking = kwargs.get("thinking")
        self.max_retries = int(kwargs.get("max_retries", 2))
        self.retry_delay = float(kwargs.get("retry_delay", 1.0))
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
        if temperature is None:
            temperature = self.default_temperature
        if max_tokens is None:
            max_tokens = self.default_max_tokens
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if self.default_thinking is not None and "thinking" not in kwargs:
            payload["thinking"] = self.default_thinking
        
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
        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.http_timeout) as client:
                    resp = await client.post(url, headers=self.headers, json=payload)
                    resp.raise_for_status()
                    return resp.json()
            except self._retryable_exceptions() as exc:
                if attempt >= self.max_retries or not self._should_retry(exc):
                    raise
                await asyncio.sleep(self.retry_delay * (2 ** attempt))
        raise RuntimeError("unreachable retry state")

    def _retryable_exceptions(self):
        return (
            httpx.ConnectError,
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
            httpx.RemoteProtocolError,
            httpx.PoolTimeout,
            httpx.HTTPStatusError,
        )

    def _should_retry(self, exc: Exception) -> bool:
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code in {408, 409, 425, 429, 500, 502, 503, 504}
        return True
    
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
        if temperature is None:
            temperature = self.default_temperature
        if max_tokens is None:
            max_tokens = self.default_max_tokens
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if self.default_thinking is not None and "thinking" not in kwargs:
            payload["thinking"] = self.default_thinking
        
        payload.update(kwargs)
        
        async with httpx.AsyncClient(timeout=self.http_timeout) as client:
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
