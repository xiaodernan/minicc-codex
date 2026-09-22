"""Rate-limit retry policy: a per-minute quota must not exhaust the attempt budget.

M6-4 evidence: the configured gateway allows 10 requests/minute. Plain
exponential backoff (1+2+4+8s) spends the entire budget inside the first 15
seconds, i.e. strictly before the limiter window can reset, so a 429 became a
task-level failure instead of a slow success.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from openai import APIConnectionError, AsyncOpenAI, RateLimitError

from minicc.llm.openai_provider import (
    OpenAICompatibleProvider,
    _is_rate_limit,
    _wait_retry_after_or_exponential,
)

MAX_RETRIES = 4


def _response(status: int, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(
        status,
        headers=headers or {},
        request=httpx.Request("POST", "https://gateway.test/v1/chat/completions"),
    )


def _rate_limit(headers: dict[str, str] | None = None) -> RateLimitError:
    return RateLimitError(
        "Error code: 429 - request limited RPM reached, current: 11, limit: 10.",
        body=None,
        response=_response(429, headers),
    )


def _wait_for(exc: Exception, attempt_number: int) -> float:
    state = SimpleNamespace(outcome=SimpleNamespace(exception=lambda: exc), attempt_number=attempt_number)
    return _wait_retry_after_or_exponential(state)  # type: ignore[arg-type]


def _budget(exc: Exception) -> list[float]:
    """Sleeps tenacity would take for one request under ``max_retries``."""
    # The final attempt raises rather than sleeping.
    return [_wait_for(exc, attempt) for attempt in range(1, MAX_RETRIES + 1)]


def test_rate_limit_backoff_budget_covers_a_minute_window() -> None:
    waits = _budget(_rate_limit())
    assert sum(waits) >= 60.0, f"retry budget {sum(waits)}s is shorter than the limiter window"
    assert waits == [15.0, 30.0, 60.0, 60.0]


def test_transient_transport_backoff_stays_fast() -> None:
    exc = APIConnectionError(message="connection reset", request=httpx.Request("POST", "https://gateway.test/v1/chat/completions"))
    assert _budget(exc) == [1.0, 2.0, 4.0, 8.0]


def test_server_retry_after_header_overrides_the_floor() -> None:
    assert _wait_for(_rate_limit({"retry-after": "3"}), 1) == 3.0
    assert _wait_for(_rate_limit({"retry-after": "120"}), 1) == 120.0


def test_rate_limit_detection_covers_a_gateway_that_hides_the_status() -> None:
    assert _is_rate_limit(_rate_limit()) is True
    hidden = RuntimeError("upstream failed")
    hidden.__cause__ = RuntimeError("HTTP 429 Too Many Requests: rpm limit reached")
    assert _is_rate_limit(hidden) is True
    assert _is_rate_limit(RuntimeError("Error code: 500 - server exploded")) is False


def _chat_payload() -> dict[str, Any]:
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 1,
        "model": "test-model",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "recovered"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
    }


@pytest.mark.asyncio()
async def test_provider_survives_a_quota_window_that_clears(monkeypatch: pytest.MonkeyPatch) -> None:
    # The floor itself is pinned by the budget test above; shrinking it here
    # keeps the wiring check (429 -> wait -> re-issue -> success) under a second.
    monkeypatch.setattr("minicc.llm.openai_provider._RATE_LIMIT_BACKOFF_BASE_SECONDS", 0.02)
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) < 3:
            return httpx.Response(429, json={"error": {"message": "request limited RPM reached, limit: 10"}})
        return httpx.Response(200, json=_chat_payload(), headers={"content-type": "application/json"})

    provider = OpenAICompatibleProvider(
        "https://gateway.test",
        "test-key",
        "test-model",
        protocol="chat_completions",
        max_retries=MAX_RETRIES,
        sdk_client=AsyncOpenAI(
            base_url="https://gateway.test/v1",
            api_key="test-key",
            max_retries=0,
            timeout=10,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        ),
    )
    response = await provider.chat([{"role": "user", "content": "hi"}])
    await provider.close()
    assert response.content == "recovered"
    assert len(attempts) == 3


@pytest.mark.asyncio()
async def test_a_persistent_quota_limit_still_becomes_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("minicc.llm.openai_provider._RATE_LIMIT_BACKOFF_BASE_SECONDS", 0.02)
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(429, json={"error": {"message": "request limited RPM reached, limit: 10"}})

    provider = OpenAICompatibleProvider(
        "https://gateway.test",
        "test-key",
        "test-model",
        protocol="chat_completions",
        max_retries=MAX_RETRIES,
        sdk_client=AsyncOpenAI(
            base_url="https://gateway.test/v1",
            api_key="test-key",
            max_retries=0,
            timeout=10,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        ),
    )
    with pytest.raises(RateLimitError):
        await provider.chat([{"role": "user", "content": "hi"}])
    await provider.close()
    assert len(attempts) == MAX_RETRIES + 1, "waiting longer must not mean retrying forever"
