"""
Base LLM client interface. All provider-specific clients must implement this.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncGenerator, Dict, List, Optional
from pydantic import BaseModel, Field


class Message(BaseModel):
    role: str  # system, user, assistant
    content: str


class LLMResponse(BaseModel):
    content: str
    usage: Dict[str, object] = Field(default_factory=dict)
    model: str = ""
    finish_reason: str = ""


class BaseLLMClient(ABC):
    """Abstract base class for LLM providers."""
    
    def __init__(self, api_key: str, base_url: str, model: str, **kwargs):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.config = kwargs
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
    async def chat_stream(
        self,
        messages: List[Message],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Stream the response content chunk by chunk."""
        pass
    
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

    def usage_summary(self) -> Dict[str, Dict[str, Dict[str, float]]]:
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
