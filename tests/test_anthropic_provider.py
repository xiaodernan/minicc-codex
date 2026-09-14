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
