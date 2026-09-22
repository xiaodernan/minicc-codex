"""模型接口核心测试：envelope 协议、provider 重试与流式归一化、usage 与推理档位。

M8-T6 拆分说明：测试本体逐字搬迁，未改断言。"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import asyncio
import pytest
from minicc.config import normalize_reasoning_effort
from minicc.llm.envelope import EnvelopeParseError, extract_json_object, parse_envelope
from minicc.llm.openai_provider import OpenAICompatibleProvider, _is_stream_retryable, _merge_stream_text, _parse_usage
from minicc.tools.editor import Editor
from minicc.tools.schemas import ToolCall
from minicc.tools import build_registry


def test_envelope_parser_handles_fenced_json() -> None:
    obj = extract_json_object('说明 {"action":"read_file","params":{"path":"a.py"}}')
    assert obj == {"action": "read_file", "params": {"path": "a.py"}}
    call = parse_envelope('{"action":"read_file","params":{"path":"a.py"}}')
    assert call is not None
    assert ToolCall.from_openai(call).tool == "read_file"


def test_envelope_parser_accepts_model_dict_dialect_and_action_objects() -> None:
    call = parse_envelope("```json\n{'action': {'command': 'npm run test:web', 'timeout': 180}}\n```")
    assert call is not None
    parsed = ToolCall.from_openai(call)
    assert parsed.tool == "bash"
    assert parsed.arguments == {"command": "npm run test:web", "timeout": 180}
    assert parsed.parse_error is None


def test_envelope_parser_accepts_nested_named_action_arguments() -> None:
    call = parse_envelope(
        "{'action': {'name': 'grep', 'arguments': "
        "{'pattern': 'function (render|addAssistantMessage|syncLiveEvents|updateLiveTask', "
        "'path': 'web/app.js'}}}"
    )
    assert call is not None
    parsed = ToolCall.from_openai(call)
    assert parsed.tool == "grep"
    assert parsed.arguments == {
        "pattern": "function (render|addAssistantMessage|syncLiveEvents|updateLiveTask",
        "path": "web/app.js",
    }
    assert parsed.parse_error is None


def test_envelope_parser_reports_incomplete_output_as_repairable_error() -> None:
    with pytest.raises(EnvelopeParseError) as caught:
        parse_envelope("{'action': 'bash', 'params': {'command': 'npm run test:web'}")
    assert "不完整" in str(caught.value)
    assert caught.value.content.startswith("{")


def test_invalid_native_tool_arguments_become_model_feedback(tmp_path: Path) -> None:
    call = ToolCall.from_openai({
        "id": "bad-args",
        "type": "function",
        "function": {"name": "read_file", "arguments": "{'path': 'note.txt'"},
    })
    result = build_registry(Editor(tmp_path)).execute(call)
    assert result.status == "error"
    assert "INVALID_TOOL_ARGUMENTS" in result.summary


def test_reasoning_effort_aliases_are_normalized() -> None:
    assert normalize_reasoning_effort("standard") == "mid"
    assert normalize_reasoning_effort("low") == "low"
    assert normalize_reasoning_effort("mid") == "mid"
    assert normalize_reasoning_effort("high") == "high"
    assert normalize_reasoning_effort("xhigh") == "xhigh"
    assert normalize_reasoning_effort("very-high") == "xhigh"


def test_provider_sends_reasoning_budget() -> None:
    seen: dict[str, object] = {}
    provider = OpenAICompatibleProvider(
        "https://example.com/v1",
        "test-key",
        "test-model",
        reasoning_effort="max",
        protocol="chat_completions",
        sdk_client=object(),
    )

    async def fake_create(kwargs: dict[str, object]) -> object:
        seen.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content="done", tool_calls=[]),
                finish_reason="stop",
            )],
            usage=None,
            model="test-model",
        )

    provider._create = fake_create  # type: ignore[method-assign]
    response = asyncio.run(provider.chat([{"role": "user", "content": "test"}], tools=None))
    assert response.content == "done"
    assert seen["reasoning_effort"] == "max"


def test_provider_normalizes_cache_usage_across_gateway_shapes() -> None:
    chat_usage = _parse_usage({
        "prompt_tokens": 2174,
        "completion_tokens": 18,
        "total_tokens": 2192,
        "prompt_tokens_details": {"cached_tokens": 1792},
    })
    assert chat_usage["prompt_cache_hit_tokens"] == 1792
    assert chat_usage["prompt_cache_miss_tokens"] == 382
    assert chat_usage["cache_hit_rate"] == round(1792 / 2174, 6)
    assert chat_usage["cache_status"] == "hit"

    responses_usage = _parse_usage(SimpleNamespace(
        input_tokens=2174,
        output_tokens=18,
        total_tokens=2192,
        input_tokens_details=SimpleNamespace(cached_tokens=0),
    ))
    assert responses_usage["prompt_cache_hit_tokens"] == 0
    assert responses_usage["prompt_cache_miss_tokens"] == 2174
    assert responses_usage["cache_hit_rate"] == 0.0
    assert responses_usage["cache_status"] == "miss"

    deepseek_usage = _parse_usage({
        "prompt_tokens": 100,
        "completion_tokens": 10,
        "prompt_cache_hit_tokens": 60,
        "prompt_cache_miss_tokens": 40,
        "cache_write_tokens": 12,
    })
    assert deepseek_usage["prompt_cache_write_tokens"] == 12
    assert deepseek_usage["cache_hit_rate"] == 0.6

    unreported = _parse_usage({"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110})
    assert unreported["cache_status"] == "unreported"
    assert unreported["cache_hit_rate"] is None
    assert "prompt_cache_hit_tokens" not in unreported


def test_provider_deduplicates_cumulative_stream_chunks() -> None:
    class FakeStream:
        def __init__(self, chunks: list[object]) -> None:
            self.chunks = iter(chunks)

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self.chunks)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

        async def aclose(self) -> None:
            return None

    chunks = [
        SimpleNamespace(model="test-model", usage=None, choices=[SimpleNamespace(finish_reason=None, delta=SimpleNamespace(content=value, reasoning_content=None, tool_calls=[]))])
        for value in ("aa", "aab", "aabc")
    ] + [SimpleNamespace(model="test-model", usage=None, choices=[SimpleNamespace(finish_reason="stop", delta=SimpleNamespace(content=None, reasoning_content=None, tool_calls=[]))])]
    provider = OpenAICompatibleProvider(
        "https://example.com/v1", "test-key", "test-model", protocol="chat_completions", sdk_client=object()
    )

    async def fake_create(_kwargs: dict[str, object]) -> FakeStream:
        return FakeStream(chunks)

    provider._create = fake_create  # type: ignore[method-assign]
    deltas: list[str] = []
    response = asyncio.run(provider.chat([{"role": "user", "content": "test"}], on_delta=deltas.append))
    # M8-T11 (decision A): cumulative snapshots are only reinterpreted after a
    # second consecutive whole-prefix grow, so the visible stream may repeat
    # text - that is the accepted cost of never dropping characters. Nothing is
    # ever withheld from the stream, and the delivered response is exactly the
    # gateway's snapshot.
    assert deltas == ["aa", "aab", "c"]
    assert response.content == "aabc"
    assert _merge_stream_text("aa", "aab") == ("aab", "b")


def _content_chunk(text: str):
    return SimpleNamespace(
        model="test-model",
        usage=None,
        choices=[SimpleNamespace(
            finish_reason=None,
            delta=SimpleNamespace(content=text, reasoning_content=None, tool_calls=[]),
        )],
    )


def _stop_chunk():
    return SimpleNamespace(
        model="test-model",
        usage=None,
        choices=[SimpleNamespace(
            finish_reason="stop",
            delta=SimpleNamespace(content=None, reasoning_content=None, tool_calls=[]),
        )],
    )


class _WatchedStream:
    """Faithful stand-in for the SDK's ``AsyncStream``.

    Two details matter and were both wrong in the first version of this
    double: ``__aiter__`` is an *async generator function*, so the object being
    iterated is a second thing that can leak; and the only closer is an async
    ``close()`` - there is no ``aclose()`` to call.
    """

    def __init__(self, chunks: list[object]) -> None:
        self._chunks = list(chunks)
        self.closed = False
        self.iterators_closed = 0

    async def __aiter__(self):
        try:
            for chunk in self._chunks:
                yield chunk
        finally:
            self.iterators_closed += 1

    async def close(self) -> None:
        self.closed = True


def _chat_completions_provider(stream_factory):
    class Completions:
        async def create(self, **kwargs):
            return stream_factory()

    return OpenAICompatibleProvider(
        "https://example.test/v1", "test-key", "test-model",
        protocol="chat_completions", max_retries=0,
        sdk_client=SimpleNamespace(chat=SimpleNamespace(completions=Completions())),
    )


def test_provider_closes_a_stream_even_after_a_clean_response() -> None:
    """The live symptom: a correct answer, exit code 0, then a teardown traceback.

    ``asyncio.run()`` closes whatever stream is still open when the loop ends,
    and httpcore2 answers with "generator didn't stop after athrow()" on
    stderr - which reads as a crash to anyone who just got a good answer.
    """
    stream = _WatchedStream([_content_chunk("KX91"), _content_chunk("-DELTA"), _stop_chunk()])
    provider = _chat_completions_provider(lambda: stream)

    async def deltas():
        seen: list[str] = []
        response = await provider.chat(
            [{"role": "user", "content": "编号？"}], on_delta=seen.append
        )
        return response, seen

    response, seen = asyncio.run(deltas())
    assert response.content == "KX91-DELTA"
    assert stream.closed, "an unclosed stream leaks into loop teardown"
    assert stream.iterators_closed == 1, "the async generator __aiter__ created also leaks"


def test_provider_closes_a_stream_it_abandons_on_error() -> None:
    from minicc.llm.openai_provider import StreamProtocolError

    stream = _WatchedStream([_content_chunk("half a sentence")])
    provider = _chat_completions_provider(lambda: stream)
    with pytest.raises(StreamProtocolError):
        asyncio.run(provider.chat([{"role": "user", "content": "hi"}], on_delta=lambda text: None))
    assert stream.closed and stream.iterators_closed == 1


def test_provider_retries_silent_incomplete_stream() -> None:
    # M1-T5: a stream chunk without finish_reason is a protocol violation,
    # not a transient failure — fail fast with 1 request (no 5x retry).
    from minicc.llm.openai_provider import StreamProtocolError

    class FakeStream:
        def __init__(self, chunks: list[object]) -> None:
            self.chunks = iter(chunks)

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self.chunks)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

        async def aclose(self) -> None:
            return None

    calls = 0
    provider = OpenAICompatibleProvider(
        "https://example.com/v1", "test-key", "test-model", protocol="chat_completions", max_retries=1, sdk_client=object()
    )

    async def fake_create(_kwargs: dict[str, object]) -> FakeStream:
        nonlocal calls
        calls += 1
        return FakeStream([
            SimpleNamespace(
                model="test-model",
                usage=None,
                choices=[SimpleNamespace(
                    finish_reason=None,
                    delta=SimpleNamespace(content="partial", reasoning_content=None, tool_calls=[]),
                )],
            )
        ])

    provider._create = fake_create  # type: ignore[method-assign]
    deltas: list[str] = []
    with pytest.raises(StreamProtocolError):
        asyncio.run(provider.chat([{"role": "user", "content": "test"}], on_delta=deltas.append))
    assert calls == 1


def test_stream_transport_error_is_retryable() -> None:
  assert _is_stream_retryable(RuntimeError("peer closed connection without sending complete message body (incomplete chunked read)"))
  assert _is_stream_retryable(RuntimeError("kernel event source lost: cause=kernel_source_unavailable replay_gap_source=reconnect_floor"))
  assert _is_stream_retryable(RuntimeError("stream disconnected before completion: error sending request for url (https://example.test/v1/responses)"))


def test_stream_transport_error_checks_wrapped_causes_and_truncated_json() -> None:
    wrapped = RuntimeError("provider request failed")
    wrapped.__cause__ = ConnectionResetError("connection reset by peer")
    assert _is_stream_retryable(wrapped)
    assert _is_stream_retryable(json.JSONDecodeError("Expecting value", "{", 1))
    assert OpenAICompatibleProvider.is_transient_failure("LLM 调用失败: Connection error.")


def test_auto_provider_falls_back_after_responses_transport_disconnect() -> None:
    seen: list[str] = []

    class FailingResponses:
        async def create(self, **kwargs):
            seen.append("responses")
            raise RuntimeError("stream disconnected before completion")

    class WorkingCompletions:
        async def create(self, **kwargs):
            seen.append("chat_completions")
            return SimpleNamespace(
                model="test-model",
                usage=SimpleNamespace(prompt_tokens=2, completion_tokens=1, total_tokens=3),
                choices=[SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(content="recovered", reasoning_content=None, tool_calls=[]),
                )],
            )

    provider = OpenAICompatibleProvider(
        "https://example.com/v1",
        "test-key",
        "test-model",
        protocol="auto",
        max_retries=0,
        sdk_client=SimpleNamespace(
            responses=FailingResponses(),
            chat=SimpleNamespace(completions=WorkingCompletions()),
        ),
    )
    response = asyncio.run(provider.chat([{"role": "user", "content": "recover"}]))
    assert response.content == "recovered"
    assert seen == ["responses", "chat_completions"]
    assert provider.protocol() == "chat_completions"


def test_provider_adapts_responses_api_tool_calls() -> None:
    seen: dict[str, object] = {}

    class FakeResponses:
        async def create(self, **kwargs):
            seen.update(kwargs)
            return SimpleNamespace(
                model="test-model",
                status="completed",
                usage=SimpleNamespace(input_tokens=12, output_tokens=4, total_tokens=16),
                output=[
                    SimpleNamespace(
                        type="message",
                        content=[SimpleNamespace(type="output_text", text="I will inspect the file.")],
                    ),
                    SimpleNamespace(type="function_call", call_id="call-read", name="read_file", arguments='{"path":"README.md"}'),
                ],
            )

    provider = OpenAICompatibleProvider(
        "https://example.com/v1", "test-key", "test-model", protocol="responses", sdk_client=SimpleNamespace(responses=FakeResponses())
    )
    tools = [{"type": "function", "function": {"name": "read_file", "description": "Read a file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}}]
    response = asyncio.run(provider.chat([{"role": "user", "content": "Read README.md"}], tools=tools))
    assert seen["reasoning"] == {"effort": "high"}
    assert seen["tools"][0]["type"] == "function"
    assert response.content == "I will inspect the file."
    assert response.tool_calls[0]["function"]["name"] == "read_file"
    assert response.usage["total_tokens"] == 16
