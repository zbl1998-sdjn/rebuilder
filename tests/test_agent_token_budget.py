import pytest

from core.implementer_agent import ImplementerAgent
from core.data_models import ArchitectureBlueprint, ProgramSpec
from llm_clients.base import BaseLLMClient, LLMResponse


class CaptureLLM(BaseLLMClient):
    def __init__(self):
        super().__init__("key", "http://example", "model", max_tokens=123)
        self.calls = []

    async def chat(self, messages, temperature=None, max_tokens=None, **kwargs):
        self.calls.append({"temperature": temperature, "max_tokens": max_tokens})
        return LLMResponse(content="--- FILE: main.py ---\nprint('ok')\n--- END FILE ---")

    async def chat_stream(self, messages, temperature=None, max_tokens=None, **kwargs):
        yield "x"


class UsageTrackingLLM(BaseLLMClient):
    def __init__(self):
        super().__init__("key", "http://example", "model")

    async def chat(self, messages, temperature=None, max_tokens=None, **kwargs):
        return self.finalize_response(
            LLMResponse(
                content="ok",
                usage={
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                    "cost": 0.25,
                },
            )
        )

    async def chat_stream(self, messages, temperature=None, max_tokens=None, **kwargs):
        yield "x"


@pytest.mark.asyncio
async def test_implementer_uses_client_configured_max_tokens(tmp_path):
    llm = CaptureLLM()

    await ImplementerAgent(llm).implement(
        ProgramSpec(summary="test"),
        ArchitectureBlueprint(language="python", entry_point="main.py"),
        tmp_path,
    )

    assert llm.calls[0]["max_tokens"] == 123


@pytest.mark.asyncio
async def test_base_client_tracks_usage_by_phase():
    llm = UsageTrackingLLM()

    llm.set_usage_phase("probe")
    await llm.chat([])
    llm.set_usage_phase("implementation")
    await llm.chat([])

    summary = llm.usage_summary()

    assert summary["by_phase"]["probe"]["prompt_tokens"] == 10.0
    assert summary["by_phase"]["implementation"]["completion_tokens"] == 5.0
    assert summary["totals"]["calls"] == 2.0
    assert summary["totals"]["total_tokens"] == 30.0
    assert summary["totals"]["cost"] == 0.5
