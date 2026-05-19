"""File-backed LLM bridge for local human or Codex-subagent handoff.

This provider performs no network calls. Each chat request is written to a
local JSON file, and the client waits for a matching local response file.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator, List, Optional

from .base import BaseLLMClient, LLMResponse, Message


class FileBridgeClient(BaseLLMClient):
    """LLM client that hands requests to a local file-based responder."""

    def __init__(self, api_key: str, base_url: str, model: str, **kwargs):
        request_dir = kwargs.get("request_dir") or base_url
        super().__init__(api_key, str(request_dir), model, **kwargs)
        self.request_dir = Path(request_dir)
        self.default_temperature = kwargs.get("temperature")
        self.default_max_tokens = kwargs.get("max_tokens")
        self.timeout = float(kwargs.get("timeout", 3600))
        self.poll_interval = float(kwargs.get("poll_interval", 1.0))

    async def chat(
        self,
        messages: List[Message],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> LLMResponse:
        self.request_dir.mkdir(parents=True, exist_ok=True)
        if temperature is None:
            temperature = self.default_temperature
        if max_tokens is None:
            max_tokens = self.default_max_tokens

        request_id = uuid.uuid4().hex
        request_path = self.request_dir / f"request_{request_id}.json"
        response_json_path = self.request_dir / f"response_{request_id}.json"
        response_text_path = self.request_dir / f"response_{request_id}.txt"
        request_payload = {
            "id": request_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "model": self.model,
            "messages": [message.model_dump() for message in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "kwargs": kwargs,
            "response_json_path": str(response_json_path),
            "response_text_path": str(response_text_path),
        }
        _write_json_atomically(request_path, request_payload)

        return self.finalize_response(
            await self._wait_for_response(
                request_path,
                response_json_path,
                response_text_path,
            )
        )

    async def _wait_for_response(
        self,
        request_path: Path,
        response_json_path: Path,
        response_text_path: Path,
    ) -> LLMResponse:
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            if response_json_path.exists():
                return self._read_json_response(response_json_path)
            if response_text_path.exists():
                return LLMResponse(
                    content=response_text_path.read_text(encoding="utf-8"),
                    model=self.model,
                    finish_reason="file_bridge_text",
                )
            await asyncio.sleep(self.poll_interval)

        raise TimeoutError(
            "file_bridge response timed out; write JSON response to "
            f"{response_json_path} or text response to {response_text_path} "
            f"for request {request_path}"
        )

    def _read_json_response(self, response_path: Path) -> LLMResponse:
        payload = json.loads(response_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("content"), str):
            raise ValueError("file_bridge JSON response must contain string field 'content'")
        usage = payload.get("usage", {})
        if not isinstance(usage, dict):
            usage = {}
        return LLMResponse(
            content=payload["content"],
            usage=usage,
            model=str(payload.get("model") or self.model),
            finish_reason=str(payload.get("finish_reason") or "file_bridge_json"),
        )

    async def chat_stream(
        self,
        messages: List[Message],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        response = await self.chat(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        yield response.content


def _write_json_atomically(path: Path, payload: dict) -> None:
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temp_path.replace(path)
