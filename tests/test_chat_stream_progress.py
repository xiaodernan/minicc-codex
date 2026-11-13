"""M8-T900: chat-completions streaming carries the same progress contract
as the Responses path (M8-T897).

Tool-call turns on the chat protocol used to be radio silence too - the
workbench's "not streaming" reading was protocol-symmetric, so the fix has
to be. These tests pin:

* tool-call name/argument fragments ride the status channel
  (provider_tool_call_start / provider_tool_call_progress with a done
  tail), never ``on_delta`` - the answer stream stays byte-clean;
* reasoning_content fragments count into provider_reasoning_progress the
  same way the Responses reasoning summaries do.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from minicc.llm.openai_provider import OpenAICompatibleProvider


class FakeChatStream:
    def __init__(self, chunks: list[Any]) -> None:
        self._chunks = chunks

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for chunk in self._chunks:
            yield chunk


class FakeCompletions:
    def __init__(self, chunks: list[Any]) -> None:
        self._chunks = chunks
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeChatStream(self._chunks)


def _provider() -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        "https://example.test/v1",
        "test-key",
        "test-model",
        protocol="chat_completions",
        max_retries=0,
        timeout=10,
    )


def _chunk(delta: Any, finish: str | None = None, usage: Any = None) -> SimpleNamespace:
    return SimpleNamespace(
        model="test-model",
        choices=[SimpleNamespace(finish_reason=finish, delta=delta)],
        usage=usage,
    )


@pytest.mark.asyncio()
async def test_chat_tool_call_progress_rides_status_channel_not_answer() -> None:
    provider = _provider()
    chunks = [
        _chunk(SimpleNamespace(content=None, reasoning_content=None, tool_calls=[
            SimpleNamespace(index=0, id="c1", function=SimpleNamespace(name="ls", arguments="")),
        ])),
        _chunk(SimpleNamespace(content=None, reasoning_content=None, tool_calls=[
            SimpleNamespace(index=0, id=None, function=SimpleNamespace(name=None, arguments='{"p')),
        ])),
        _chunk(SimpleNamespace(content=None, reasoning_content=None, tool_calls=[
            SimpleNamespace(index=0, id=None, function=SimpleNamespace(name=None, arguments='":1}')),
        ])),
        _chunk(SimpleNamespace(content=None, reasoning_content=None, tool_calls=None), finish="tool_calls"),
    ]
    provider._client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions(chunks)))
    traces: list[dict] = []
    provider._on_status = traces.append
    deltas: list[str] = []
    response = await provider.chat(
        [{"role": "user", "content": "list"}],
        tools=[{"type": "function", "function": {"name": "ls", "description": "list", "parameters": {"type": "object", "properties": {}}}}],
        on_delta=deltas.append,
    )
    await provider.close()
    assert deltas == [], "tool-call JSON fragments must never leak into the answer stream"
    codes = [str(t.get("code")) for t in traces]
    assert "provider_tool_call_start" in codes
    assert "provider_tool_call_progress" in codes
    start = next(t for t in traces if t.get("code") == "provider_tool_call_start")
    assert start["detail"]["tool"] == "ls"
    done = [t for t in traces if t.get("code") == "provider_tool_call_progress" and t["detail"].get("done")]
    assert done and done[-1]["detail"]["chars"] == len('{"p":1}')
    assert response.tool_calls and response.tool_calls[0]["function"]["name"] == "ls"


@pytest.mark.asyncio()
async def test_chat_reasoning_progress_counts_without_touching_answer() -> None:
    provider = _provider()
    chunks = [
        _chunk(SimpleNamespace(content=None, reasoning_content="想", tool_calls=None)),
        _chunk(SimpleNamespace(content=None, reasoning_content="考", tool_calls=None)),
        _chunk(SimpleNamespace(content="答案", reasoning_content=None, tool_calls=None), finish="stop"),
    ]
    provider._client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions(chunks)))
    traces: list[dict] = []
    provider._on_status = traces.append
    deltas: list[str] = []
    response = await provider.chat([{"role": "user", "content": "hi"}], on_delta=deltas.append)
    await provider.close()
    codes = [str(t.get("code")) for t in traces]
    assert codes.count("provider_reasoning_progress") >= 1
    assert deltas == ["答案"]
    assert response.text == "答案"
