import pytest
import httpx

from llm_clients.kimi_client import KimiClient


class FakeResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 1},
            "model": "kimi-k2-6",
        }


class FakeAsyncClient:
    payloads: list = []

    def __init__(self, timeout):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, headers, json):
        FakeAsyncClient.payloads.append(json)
        return FakeResponse()


class FlakyAsyncClient(FakeAsyncClient):
    attempts = 0

    async def post(self, url, headers, json):
        FlakyAsyncClient.attempts += 1
        if FlakyAsyncClient.attempts == 1:
            raise httpx.ConnectError("temporary connect failure")
        return await super().post(url, headers, json)


@pytest.mark.asyncio
async def test_kimi_client_retries_transient_connect_errors(monkeypatch):
    FlakyAsyncClient.attempts = 0
    FakeAsyncClient.payloads = []
    monkeypatch.setattr("llm_clients.kimi_client.httpx.AsyncClient", FlakyAsyncClient)
    client = KimiClient(
        api_key="key",
        base_url="https://api.moonshot.cn/v1",
        model="kimi-k2-6",
        timeout=10,
        max_retries=1,
        retry_delay=0,
    )

    response = await client.chat([client.user_prompt("hi")])

    assert FlakyAsyncClient.attempts == 2
    assert response.content == "ok"
