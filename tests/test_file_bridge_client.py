import asyncio
import json
from pathlib import Path

import pytest

from llm_clients.base import Message
from llm_clients.file_bridge_client import FileBridgeClient


async def wait_for_request(request_dir: Path) -> dict:
    for _ in range(100):
        requests = sorted(request_dir.glob("request_*.json"))
        if requests:
            return json.loads(requests[0].read_text(encoding="utf-8"))
        await asyncio.sleep(0.01)
    raise AssertionError("file_bridge request was not written")


@pytest.mark.asyncio
async def test_file_bridge_client_writes_request_and_reads_json_response(tmp_path):
    request_dir = tmp_path / "bridge"
    client = FileBridgeClient(
        api_key="",
        base_url=str(request_dir),
        model="codex-file-bridge",
        poll_interval=0.01,
        timeout=1,
    )

    async def responder() -> None:
        request = await wait_for_request(request_dir)
        assert request["model"] == "codex-file-bridge"
        assert request["messages"] == [{"role": "user", "content": "hello"}]
        assert request["temperature"] == 0.0
        assert request["max_tokens"] == 16
        Path(request["response_json_path"]).write_text(
            json.dumps(
                {
                    "content": "world",
                    "usage": {"total_tokens": 3},
                    "finish_reason": "stop",
                }
            ),
            encoding="utf-8",
        )

    response_task = asyncio.create_task(responder())
    response = await client.chat(
        [Message(role="user", content="hello")],
        temperature=0.0,
        max_tokens=16,
    )
    await response_task

    assert response.content == "world"
    assert response.usage == {"total_tokens": 3}
    assert response.model == "codex-file-bridge"
    assert response.finish_reason == "stop"


@pytest.mark.asyncio
async def test_file_bridge_client_accepts_plain_text_response(tmp_path):
    request_dir = tmp_path / "bridge"
    client = FileBridgeClient(
        api_key="",
        base_url=str(request_dir),
        model="codex-file-bridge",
        poll_interval=0.01,
        timeout=1,
    )

    async def responder() -> None:
        request = await wait_for_request(request_dir)
        Path(request["response_text_path"]).write_text("plain response", encoding="utf-8")

    response_task = asyncio.create_task(responder())
    response = await client.chat([Message(role="user", content="hello")])
    await response_task

    assert response.content == "plain response"
    assert response.finish_reason == "file_bridge_text"


@pytest.mark.asyncio
async def test_file_bridge_client_times_out_waiting_for_response(tmp_path):
    client = FileBridgeClient(
        api_key="",
        base_url=str(tmp_path / "bridge"),
        model="codex-file-bridge",
        poll_interval=0.01,
        timeout=0.03,
    )

    with pytest.raises(TimeoutError, match="file_bridge response timed out"):
        await client.chat([Message(role="user", content="hello")])
