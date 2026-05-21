import pytest
import httpx
from types import SimpleNamespace

from llm_clients.glm_client import GLMClient


class FakeResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 1},
            "model": "glm-5.1",
        }


class FakeAsyncClient:
    payloads: list[object] = []
    last_timeout = None

    def __init__(self, timeout):
        self.timeout = timeout
        FakeAsyncClient.last_timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, headers, json):
        self.payloads.append(json)
        return FakeResponse()


@pytest.mark.asyncio
async def test_glm_client_applies_default_request_options(monkeypatch):
    FakeAsyncClient.payloads = []
    FakeAsyncClient.last_timeout = None
    monkeypatch.setattr("llm_clients.glm_client.httpx.AsyncClient", FakeAsyncClient)
    client = GLMClient(
        api_key="key",
        base_url="https://api.z.ai/api/coding/paas/v4",
        model="glm-5.1",
        temperature=0.3,
        max_tokens=128,
        timeout=10,
        thinking={"type": "disabled"},
    )

    await client.chat([client.user_prompt("hi")])

    payload = FakeAsyncClient.payloads[0]
    assert payload["temperature"] == 0.3
    assert payload["max_tokens"] == 128
    assert payload["thinking"] == {"type": "disabled"}
    assert isinstance(FakeAsyncClient.last_timeout, httpx.Timeout)
    assert FakeAsyncClient.last_timeout.connect == 10
    assert FakeAsyncClient.last_timeout.read == 10


class FlakyAsyncClient(FakeAsyncClient):
    attempts = 0

    async def post(self, url, headers, json):
        FlakyAsyncClient.attempts += 1
        if FlakyAsyncClient.attempts == 1:
            raise httpx.ConnectError("temporary connect failure")
        return await super().post(url, headers, json)


@pytest.mark.asyncio
async def test_glm_client_retries_transient_connect_errors(monkeypatch):
    FlakyAsyncClient.attempts = 0
    monkeypatch.setattr("llm_clients.glm_client.httpx.AsyncClient", FlakyAsyncClient)
    client = GLMClient(
        api_key="key",
        base_url="https://api.z.ai/api/coding/paas/v4",
        model="glm-5.1",
        timeout=10,
        max_retries=1,
        retry_delay=0,
    )

    response = await client.chat([client.user_prompt("hi")])

    assert FlakyAsyncClient.attempts == 2
    assert response.content == "ok"


@pytest.mark.asyncio
async def test_glm_client_retry_backoff_includes_jitter(monkeypatch):
    FlakyAsyncClient.attempts = 0
    sleep_delays = []

    async def fake_sleep(delay):
        sleep_delays.append(delay)

    import llm_clients.base as base_module

    monkeypatch.setattr("llm_clients.glm_client.httpx.AsyncClient", FlakyAsyncClient)
    monkeypatch.setattr(base_module.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(
        base_module,
        "random",
        SimpleNamespace(uniform=lambda _low, _high: 0.25),
        raising=False,
    )
    client = GLMClient(
        api_key="key",
        base_url="https://api.z.ai/api/coding/paas/v4",
        model="glm-5.1",
        timeout=10,
        max_retries=1,
        retry_delay=2,
    )

    response = await client.chat([client.user_prompt("hi")])

    assert response.content == "ok"
    assert sleep_delays == [2.25]


def test_glm_client_caps_connect_timeout_for_long_requests():
    client = GLMClient(
        api_key="key",
        base_url="https://api.z.ai/api/coding/paas/v4",
        model="glm-5.1",
        timeout=300,
    )

    assert client.http_timeout.connect == 30
    assert client.http_timeout.write == 30
    assert client.http_timeout.pool == 30
    assert client.http_timeout.read == 300
