"""Anthropic native provider tests: wire format, caching, tool conversion."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from minicc.llm.anthropic_provider import (
    AnthropicProvider,
    messages_to_anthropic,
    response_to_llm,
    tools_to_anthropic,
)
from minicc.llm.base import assistant_msg, system_msg, tool_result_msg, user_msg


def test_messages_split_and_tool_roundtrip() -> None:
    messages = [
        system_msg("system rules"),
        user_msg("read the file"),
        assistant_msg(tool_calls=[{
            "id": "call-1", "type": "function",
            "function": {"name": "read_file", "arguments": '{"path": "a.py"}'},
        }]),
        tool_result_msg("call-1", "file body"),
        user_msg("总结一下"),
    ]
    system, converted = messages_to_anthropic(messages)
    assert "system rules" in system
    assert converted[0]["role"] == "user"
    assert converted[1]["role"] == "assistant"
    tool_use = converted[1]["content"][0]
    assert tool_use["type"] == "tool_use"
    assert tool_use["input"] == {"path": "a.py"}
    # Tool results merge into the following user turn.
    assert converted[2]["content"][0]["type"] == "tool_result"
    assert converted[2]["content"][0]["tool_use_id"] == "call-1"
    assert converted[3]["content"] == "总结一下"


def test_tools_conversion_marks_last_for_caching() -> None:
    schemas = [
        {"type": "function", "function": {"name": "read_file", "description": "d1", "parameters": {"type": "object"}}},
        {"type": "function", "function": {"name": "grep", "description": "d2", "parameters": {"type": "object"}}},
    ]
    converted = tools_to_anthropic(schemas)
    assert converted[0]["name"] == "read_file"
    assert "cache_control" not in converted[0]
    assert converted[-1]["cache_control"] == {"type": "ephemeral"}


def test_image_data_url_conversion() -> None:
    blocks = convert = None
    from minicc.llm.anthropic_provider import convert_user_content

    converted = convert_user_content([
        {"type": "text", "text": "看图"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,QUJD"}},
    ])
    assert converted[0]["type"] == "text"
    assert converted[1]["source"] == {"type": "base64", "media_type": "image/png", "data": "QUJD"}


def test_response_maps_usage_and_tool_use() -> None:
    payload: dict[str, Any] = {
        "model": "claude-x",
        "stop_reason": "tool_use",
        "content": [
            {"type": "text", "text": "让我先读文件"},
            {"type": "tool_use", "id": "tu-1", "name": "read_file", "input": {"path": "a.py"}},
        ],
        "usage": {"input_tokens": 100, "output_tokens": 20, "cache_read_input_tokens": 80, "cache_creation_input_tokens": 12},
    }
    response = response_to_llm(payload, "claude-x")
    assert response.text == "让我先读文件"
    assert response.finish_reason == "tool_calls"
    assert response.tool_calls[0]["function"]["name"] == "read_file"
    assert json.loads(response.tool_calls[0]["function"]["arguments"]) == {"path": "a.py"}
    usage = response.usage
    assert usage["prompt_tokens"] == 100
    assert usage["completion_tokens"] == 20
    assert usage["total_tokens"] == 120
    assert usage["prompt_cache_hit_tokens"] == 80
    assert usage["prompt_cache_write_tokens"] == 12


def _transport(recorder: list[httpx.Request], payload: dict[str, Any]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        recorder.append(request)
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handler)


@pytest.mark.asyncio()
async def test_chat_sends_headers_system_and_caching_breakpoint() -> None:
    requests: list[httpx.Request] = []
    payload = {
        "model": "claude-test",
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": "回答完成"}],
        "usage": {"input_tokens": 50, "output_tokens": 10},
    }
    provider = AnthropicProvider(
        api_key="sk-ant-test",
        model="claude-test",
        transport=_transport(requests, payload),
    )
    response = await provider.chat(
        [system_msg("system rules"), user_msg("hi")],
        tools=[{"type": "function", "function": {"name": "grep", "description": "", "parameters": {"type": "object"}}}],
    )
    await provider.close()
    assert response.text == "回答完成"
    assert len(requests) == 1
    request = requests[0]
    assert request.url.path.endswith("/v1/messages")
    assert request.headers["x-api-key"] == "sk-ant-test"
    assert request.headers["anthropic-version"] == "2023-06-01"
    body = json.loads(request.content.decode("utf-8"))
    assert body["model"] == "claude-test"
    assert body["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert body["tools"][-1]["cache_control"] == {"type": "ephemeral"}
    assert body["messages"][0]["content"] == "hi"


@pytest.mark.asyncio()
async def test_chat_raises_provider_error_on_http_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    provider = AnthropicProvider(api_key="bad", model="claude-test", transport=httpx.MockTransport(handler), max_retries=0)
    with pytest.raises(Exception, match="401"):
        await provider.chat([user_msg("hi")])
    await provider.close()


def _sse_bytes(*events: dict[str, Any]) -> bytes:
    return "".join(f"data: {json.dumps(event, ensure_ascii=False)}\n\n" for event in events).encode("utf-8")


TEXT_SSE = _sse_bytes(
    {"type": "message_start", "message": {"model": "claude-test", "usage": {"input_tokens": 4}}},
    {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
    {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "hello "}},
    {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "world"}},
    {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 2}},
    {"type": "message_stop"},
)

TOOL_SSE = _sse_bytes(
    {"type": "message_start", "message": {"model": "claude-test", "usage": {"input_tokens": 6}}},
    {
        "type": "content_block_start",
        "index": 0,
        "content_block": {"type": "tool_use", "id": "tu-1", "name": "read_file", "input": {}},
    },
    {"type": "content_block_delta", "index": 0, "delta": {"type": "input_json_delta", "partial_json": "{\"path\":"}},
    {"type": "content_block_delta", "index": 0, "delta": {"type": "input_json_delta", "partial_json": "\"a.py\"}"}},
    {"type": "message_delta", "delta": {"stop_reason": "tool_use"}, "usage": {"output_tokens": 8}},
    {"type": "message_stop"},
)


@pytest.mark.asyncio()
async def test_stream_calls_on_delta_for_text() -> None:
    requests: list[httpx.Request] = []
    deltas: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=TEXT_SSE, headers={"content-type": "text/event-stream"})

    provider = AnthropicProvider(
        api_key="sk-ant-test",
        model="claude-test",
        transport=httpx.MockTransport(handler),
        max_retries=0,
    )
    response = await provider.chat([user_msg("hi")], on_delta=deltas.append)
    await provider.close()
    assert deltas == ["hello ", "world"]
    assert response.text == "hello world"
    body = json.loads(requests[0].content.decode("utf-8"))
    assert body["stream"] is True


@pytest.mark.asyncio()
async def test_stream_aggregates_tool_use_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=TOOL_SSE, headers={"content-type": "text/event-stream"})

    provider = AnthropicProvider(
        api_key="sk-ant-test",
        model="claude-test",
        transport=httpx.MockTransport(handler),
        max_retries=0,
    )
    response = await provider.chat([user_msg("hi")], on_delta=lambda _chunk: None)
    await provider.close()
    assert response.finish_reason == "tool_calls"
    assert response.tool_calls[0]["function"]["name"] == "read_file"
    assert json.loads(response.tool_calls[0]["function"]["arguments"]) == {"path": "a.py"}


@pytest.mark.asyncio()
async def test_stream_retries_only_before_first_delta(monkeypatch: pytest.MonkeyPatch) -> None:
    async def no_sleep(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr("minicc.llm.anthropic_provider._backoff", no_sleep)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(500, text="try again")
        return httpx.Response(200, content=TEXT_SSE, headers={"content-type": "text/event-stream"})

    provider = AnthropicProvider(
        api_key="sk-ant-test",
        model="claude-test",
        transport=httpx.MockTransport(handler),
        max_retries=2,
    )
    response = await provider.chat([user_msg("hi")], on_delta=lambda _chunk: None)
    await provider.close()
    assert calls["n"] == 2
    assert response.text == "hello world"


@pytest.mark.asyncio()
async def test_chat_without_on_delta_stays_on_json_path() -> None:
    requests: list[httpx.Request] = []
    payload = {
        "model": "claude-test",
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": "atomic"}],
        "usage": {"input_tokens": 3, "output_tokens": 1},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=payload)

    provider = AnthropicProvider(
        api_key="sk-ant-test",
        model="claude-test",
        transport=httpx.MockTransport(handler),
        max_retries=0,
    )
    response = await provider.chat([user_msg("hi")])
    await provider.close()
    assert response.text == "atomic"
    body = json.loads(requests[0].content.decode("utf-8"))
    assert "stream" not in body or body["stream"] is not True
