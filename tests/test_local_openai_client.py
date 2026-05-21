import httpx
import pytest

from llm_clients.local_openai_client import LocalOpenAIClient


class FakeResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 1},
            "model": "local-model",
        }


class FakeAsyncClient:
    requests: list[tuple[object, object, object]] = []
    last_timeout = None

    def __init__(self, timeout):
        self.timeout = timeout
        FakeAsyncClient.last_timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, headers, json):
        self.requests.append((url, headers, json))
        return FakeResponse()


@pytest.mark.asyncio
async def test_local_openai_client_posts_to_loopback_chat_completions(monkeypatch):
    FakeAsyncClient.requests = []
    FakeAsyncClient.last_timeout = None
    monkeypatch.setattr("llm_clients.local_openai_client.httpx.AsyncClient", FakeAsyncClient)
    client = LocalOpenAIClient(
        api_key="",
        base_url="http://127.0.0.1:11434/v1",
        model="qwen2.5-coder",
        temperature=0.2,
        max_tokens=128,
        timeout=10,
    )

    response = await client.chat([client.user_prompt("hi")])

    url, headers, payload = FakeAsyncClient.requests[0]
    assert response.content == "ok"
    assert url == "http://127.0.0.1:11434/v1/chat/completions"
    assert headers == {"Content-Type": "application/json"}
    assert payload["model"] == "qwen2.5-coder"
    assert payload["temperature"] == 0.2
    assert payload["max_tokens"] == 128
    assert isinstance(FakeAsyncClient.last_timeout, httpx.Timeout)
    assert FakeAsyncClient.last_timeout.connect == 10


@pytest.mark.asyncio
async def test_local_openai_client_uses_authorization_only_when_key_is_set(monkeypatch):
    FakeAsyncClient.requests = []
    monkeypatch.setattr("llm_clients.local_openai_client.httpx.AsyncClient", FakeAsyncClient)
    client = LocalOpenAIClient(
        api_key="local-token",
        base_url="http://localhost:1234/v1",
        model="local-model",
        timeout=10,
    )

    await client.chat([client.user_prompt("hi")])

    _url, headers, _payload = FakeAsyncClient.requests[0]
    assert headers["Authorization"] == "Bearer local-token"


def test_local_openai_client_rejects_external_base_url_by_default():
    with pytest.raises(ValueError, match="loopback"):
        LocalOpenAIClient(
            api_key="",
            base_url="https://api.openai.com/v1",
            model="gpt-4.1",
        )
