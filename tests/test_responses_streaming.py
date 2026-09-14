"""Responses API streaming tests: delta delivery, final mapping, no-replay."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from minicc.llm.base import LLMResponse
from minicc.llm.openai_provider import OpenAICompatibleProvider, ResponsesPartialError


def _provider() -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        base_url="https://example.test/v1",
        api_key="test-key",
        model="test-model",
        timeout=10,
        tool_mode="native",
        protocol="responses",
    )


class FakeStream:
    def __init__(self, events: list[Any]) -> None:
        self._events = events

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for event in self._events:
            yield event

    async def get_final_response(self):  # pragma: no cover - should not be needed
        return None


class FakeResponsesAPI:
    def __init__(self, events: list[Any], calls: list[dict]) -> None:
        self._events = events
        self.calls = calls

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeStream(self._events)


def _completed_response(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        id="resp-1",
        status="completed",
        model="test-model",
        output=[
            SimpleNamespace(
                type="message",
                content=[SimpleNamespace(type="output_text", text=text)],
            ),
        ],
        usage=SimpleNamespace(
            input_tokens=100,
            output_tokens=20,
            input_tokens_details=SimpleNamespace(cached_tokens=60),
        ),
    )


@pytest.mark.asyncio()
async def test_stream_deltas_delivered_and_final_mapped() -> None:
    provider = _provider()
    events = [
        SimpleNamespace(type="response.output_text.delta", delta="你好"),
        SimpleNamespace(type="response.output_text.delta", delta="，世界"),
        SimpleNamespace(type="response.completed", response=_completed_response("你好，世界")),
    ]
    calls: list[dict] = []
    provider._client = SimpleNamespace(responses=FakeResponsesAPI(events, calls))
    deltas: list[str] = []
    response = await provider.chat(
        [{"role": "user", "content": "hi"}],
        tools=None,
        on_delta=deltas.append,
    )
    await provider.close()
    assert deltas == ["你好", "，世界"]
    assert response.text == "你好，世界"
    assert response.usage["prompt_cache_hit_tokens"] == 60
    assert calls[0].get("stream") is True


@pytest.mark.asyncio()
async def test_mid_stream_break_not_retried_and_raises_partial() -> None:
    provider = _provider()
    provider._max_retries = 3

    class BrokenStream:
        def __aiter__(self):
            return self._iterate()

        async def _iterate(self):
            yield SimpleNamespace(type="response.output_text.delta", delta="部分")
            raise RuntimeError("incomplete chunked read")  # stream-retryable text

    calls: list[dict] = []
    provider._client = SimpleNamespace(responses=FakeResponsesAPI.__new__(FakeResponsesAPI))
    provider._client.responses = type("R", (), {"create": None})()
    seen_calls: list[dict] = []

    async def create(**kwargs):
        seen_calls.append(kwargs)
        return BrokenStream()

    provider._client.responses.create = create

    deltas: list[str] = []
    with pytest.raises(ResponsesPartialError):
        await provider.chat([{"role": "user", "content": "hi"}], tools=None, on_delta=deltas.append)
    await provider.close()
    # Deltas were delivered, the stream broke, and no retry duplicated them.
    assert deltas == ["部分"]
    assert len(seen_calls) == 1


@pytest.mark.asyncio()
async def test_stream_failure_before_delta_is_retried() -> None:
    provider = _provider()
    provider._max_retries = 2
    attempts = {"n": 0}
    calls: list[dict] = []

    async def create(**kwargs):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RuntimeError("server disconnected")
        return FakeStream([
            SimpleNamespace(type="response.output_text.delta", delta="答案"),
            SimpleNamespace(type="response.completed", response=_completed_response("答案")),
        ])

    api = type("R", (), {})()
    api.create = create
    provider._client = SimpleNamespace(responses=api)

    deltas: list[str] = []
    response = await provider.chat([{"role": "user", "content": "hi"}], tools=None, on_delta=deltas.append)
    await provider.close()
    assert attempts["n"] == 2
    assert deltas == ["答案"]
    assert response.text == "答案"


@pytest.mark.asyncio()
async def test_atomic_path_unchanged_without_delta_callback() -> None:
    provider = _provider()
    response_obj = _completed_response("一次性返回")
    calls: list[dict] = []

    async def create(**kwargs):
        calls.append(kwargs)
        assert not kwargs.get("stream")
        return response_obj

    api = type("R", (), {})()
    api.create = create
    provider._client = SimpleNamespace(responses=api)
    response = await provider.chat([{"role": "user", "content": "hi"}], tools=None)
    await provider.close()
    assert response.text == "一次性返回"
    assert len(calls) == 1
