"""
Base LLM client interface. All provider-specific clients must implement this.
"""

from __future__ import annotations

import asyncio
import random
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Awaitable, Callable, Dict, List, Optional, TypedDict

import httpx
from pydantic import BaseModel, Field


class Message(BaseModel):
    role: str  # system, user, assistant
    content: str


class LLMResponse(BaseModel):
    content: str
    usage: Dict[str, object] = Field(default_factory=dict)
    model: str = ""
    finish_reason: str = ""


class UsageSummary(TypedDict):
    by_phase: Dict[str, Dict[str, float]]
    totals: Dict[str, float]


RETRYABLE_HTTPX_EXCEPTIONS: tuple[type[Exception], ...] = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.RemoteProtocolError,
    httpx.PoolTimeout,
    httpx.HTTPStatusError,
)

RETRYABLE_HTTP_STATUS_CODES: frozenset[int] = frozenset({408, 409, 425, 429, 500, 502, 503, 504})


class BaseLLMClient(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, api_key: str, base_url: str, model: str, **kwargs):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.config = kwargs
        self.max_retries = int(kwargs.get("max_retries", 2))
        self.retry_delay = float(kwargs.get("retry_delay", 1.0))
        self._usage_phase = "unspecified"
        self._usage_by_phase: Dict[str, Dict[str, float]] = {}
    
    @abstractmethod
    async def chat(
        self,
        messages: List[Message],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> LLMResponse:
        """Send a chat completion request and return the response."""
        pass
    
    @abstractmethod
    def chat_stream(
        self,
        messages: List[Message],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Stream the response content chunk by chunk."""
        pass
    
    async def _retrying_request(
        self,
        send: Callable[[], Awaitable[httpx.Response]],
    ) -> dict:
        """Execute a request callable with shared exponential-backoff retry."""
        for attempt in range(self.max_retries + 1):
            try:
                resp = await send()
                resp.raise_for_status()
                return resp.json()
            except RETRYABLE_HTTPX_EXCEPTIONS as exc:
                if attempt >= self.max_retries or not self._is_retryable(exc):
                    raise
                await asyncio.sleep(self._retry_sleep_delay(attempt))
        raise RuntimeError("unreachable retry state")

    def _retry_sleep_delay(self, attempt: int) -> float:
        base_delay = self.retry_delay * (2 ** attempt)
        if base_delay <= 0:
            return 0
        return base_delay + random.uniform(0, min(base_delay * 0.2, 1.0))

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code in RETRYABLE_HTTP_STATUS_CODES
        return True

    def system_prompt(self, content: str) -> Message:
        return Message(role="system", content=content)
    
    def user_prompt(self, content: str) -> Message:
        return Message(role="user", content=content)
    
    def assistant_prompt(self, content: str) -> Message:
        return Message(role="assistant", content=content)

    def set_usage_phase(self, phase: Optional[str]) -> None:
        self._usage_phase = phase or "unspecified"

    def reset_usage_tracking(self) -> None:
        self._usage_by_phase = {}
        self._usage_phase = "unspecified"

    def usage_summary(self) -> UsageSummary:
        by_phase = {
            phase: dict(sorted(values.items()))
            for phase, values in sorted(self._usage_by_phase.items())
        }
        totals: Dict[str, float] = {}
        for values in by_phase.values():
            for key, value in values.items():
                totals[key] = totals.get(key, 0.0) + value
        return {
            "by_phase": by_phase,
            "totals": dict(sorted(totals.items())),
        }

    def finalize_response(self, response: LLMResponse) -> LLMResponse:
        self._record_usage(response.usage)
        return response

    def _record_usage(self, usage: Dict[str, object]) -> None:
        bucket = self._usage_by_phase.setdefault(self._usage_phase, {})
        bucket["calls"] = bucket.get("calls", 0.0) + 1.0
        for key, value in self._flatten_numeric_usage(usage).items():
            bucket[key] = bucket.get(key, 0.0) + value

    def _flatten_numeric_usage(
        self,
        usage: Dict[str, object],
        prefix: str = "",
    ) -> Dict[str, float]:
        flattened: Dict[str, float] = {}
        for key, value in usage.items():
            name = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                flattened.update(self._flatten_numeric_usage(value, prefix=name))
                continue
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                flattened[name] = float(value)
                continue
            if isinstance(value, str):
                try:
                    flattened[name] = float(value)
                except ValueError:
                    continue
        return flattened
