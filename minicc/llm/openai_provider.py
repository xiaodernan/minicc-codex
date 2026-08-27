"""OpenAICompatibleProvider — one async client for any OpenAI /v1 endpoint.

Adapted from specproof providers/openai_compatible.py, keeping the parts a
coding agent actually needs and dropping the platform policy layers:

- tenacity-owned retries (SDK max_retries=0, so retries are counted once);
  429 honors the gateway's Retry-After header, otherwise capped exponential;
- native streaming with on_delta callbacks and full tool_call delta
  aggregation — the caller sees one complete LLMResponse per turn;
- honest degradation to the JSON Action Envelope when the gateway rejects
  the `tools` parameter (mode auto). The switch is sticky per provider
  instance and reported via tool_mode();
- DeepSeek-style usage fields (prompt_cache_hit/miss_tokens, reasoning
  tokens) are parsed when present, never fabricated;
- reasoning_content stays on LLMResponse and never enters content.

Envelope-mode wire conversion: gateways without tool support also reject
`role:"tool"` messages, so tool results are replayed as user messages and
assistant tool_calls collapse to their text content.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

try:
    import httpx
except ModuleNotFoundError:  # OpenAI SDK adapters do not all expose httpx.
    httpx = None  # type: ignore[assignment]
try:
    import httpcore
except ModuleNotFoundError:  # pragma: no cover - depends on the HTTP stack.
    httpcore = None  # type: ignore[assignment]
from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    BadRequestError,
    ConflictError,
    InternalServerError,
    NotFoundError,
    RateLimitError,
)
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception,
    stop_after_attempt,
)

from .base import LLMResponse
from .envelope import envelope_system_suffix, parse_envelope
from .usage import cache_summary

_RETRYABLE = (
    RateLimitError,
    ConflictError,
    InternalServerError,
    APITimeoutError,
    APIConnectionError,
)

_HTTPX_STREAM_RETRYABLE = (
    (
        httpx.RemoteProtocolError,
        httpx.ReadError,
        httpx.ReadTimeout,
        httpx.ConnectError,
        httpx.WriteError,
        httpx.PoolTimeout,
    )
    if httpx is not None
    else ()
)
_HTTPCORE_STREAM_RETRYABLE = tuple(
    getattr(httpcore, name)
    for name in ("RemoteProtocolError", "ReadError", "ReadTimeout", "ConnectError", "WriteError", "PoolTimeout")
    if httpcore is not None and hasattr(httpcore, name)
)
_STREAM_RETRYABLE = _RETRYABLE + _HTTPX_STREAM_RETRYABLE + _HTTPCORE_STREAM_RETRYABLE
_BUILTIN_STREAM_RETRYABLE = (ConnectionError, TimeoutError)
_MALFORMED_RESPONSE_HINTS = (
    "expecting value",
    "expecting property name enclosed",
    "expecting ',' delimiter",
    "unterminated string",
)

TOOLS_REJECTION_HINTS = ("tool", "function")
REASONING_WIRE_VALUES = {
    "low": "low",
    "mid": "mid",
    "high": "high",
    "xhigh": "xhigh",
    "max": "max",
}
REASONING_FALLBACKS = {
    "max": "xhigh",
    "xhigh": "high",
    "high": "mid",
    "mid": "low",
    "low": None,
}


def _exception_text(exc: BaseException) -> str:
    """Include wrapped transport/parser causes exposed by compatible SDKs."""
    parts: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while isinstance(current, BaseException) and id(current) not in seen:
        seen.add(id(current))
        parts.append(str(current))
        current = current.__cause__ or current.__context__
    return " ".join(parts).lower()


def _is_retryable(exc: BaseException) -> bool:
    return (
        isinstance(exc, _RETRYABLE)
        or isinstance(exc, _BUILTIN_STREAM_RETRYABLE)
        or _is_gateway_event_source_error(exc)
        or _is_malformed_response_error(exc)
    )


def _is_gateway_event_source_error(exc: BaseException) -> bool:
    """Recognize transient event-source failures leaked by compatible gateways."""
    text = _exception_text(exc)
    return any(
        marker in text
        for marker in (
            "kernel event source lost",
            "kernel_source_unavailable",
            "replay_gap_source",
            "event source lost",
            "stream disconnected",
            "disconnected before completion",
        )
    )


def _is_malformed_response_error(exc: BaseException) -> bool:
    """Recognize truncated JSON bodies reported by an SDK decoder."""
    if isinstance(exc, json.JSONDecodeError):
        return True
    text = _exception_text(exc)
    return any(marker in text for marker in _MALFORMED_RESPONSE_HINTS)


def _is_stream_retryable(exc: BaseException) -> bool:
    """The gateway can fail while an already-open chunked body is read."""
    if isinstance(exc, _STREAM_RETRYABLE) or isinstance(exc, _BUILTIN_STREAM_RETRYABLE):
        return True
    # A few compatible gateways leak the transport error as a generic SDK
    # exception while the response body is being consumed.
    text = _exception_text(exc)
    return any(
        marker in text
        for marker in (
            "incomplete chunked read",
            "incomplete read",
            "peer closed connection",
            "remote protocol error",
            "connection reset",
            "connection closed",
            "connection aborted",
            "server disconnected",
            "reset by peer",
            "broken pipe",
            "connection error",
            "network error",
            "request timed out",
            "timed out",
            "temporarily unavailable",
            "service unavailable",
            "bad gateway",
            "gateway timeout",
            "read operation timed out",
            "stream disconnected",
            "disconnected before completion",
            "kernel event source lost",
            "kernel_source_unavailable",
            "replay_gap_source",
            "event source lost",
            # Some gateways return a truncated/non-JSON error body. The SDK
            # exposes only the JSON decoder message, so treat it like a
            # transient response failure and let the bounded recovery path
            # decide whether to retry or stop.
            *_MALFORMED_RESPONSE_HINTS,
            "stream ended before completion",
        )
    )


def _retry_after_seconds(exc: BaseException) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers or not hasattr(headers, "get"):
        return None
    raw = headers.get("retry-after")
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return None


def _wait_retry_after_or_exponential(retry_state: RetryCallState) -> float:
    outcome = retry_state.outcome
    exception = outcome.exception() if outcome is not None else None
    retry_after = _retry_after_seconds(exception) if exception is not None else None
    if retry_after is not None:
        return retry_after
    return min(60.0, float(2 ** max(0, retry_state.attempt_number - 1)))


def _stream_retry_delay(exc: BaseException, attempt: int) -> float:
    retry_after = _retry_after_seconds(exc)
    if retry_after is not None:
        return min(8.0, retry_after)
    return min(12.0, float(2 ** max(0, attempt - 1)))


def _merge_stream_text(previous: str, current: str) -> tuple[str, str]:
    """Merge a retried full response and return only the new suffix."""
    if not previous:
        return current, current
    if not current:
        return previous, ""
    if current.startswith(previous):
        return current, current[len(previous):]
    if previous.startswith(current):
        return previous, ""
    max_overlap = min(len(previous), len(current))
    for size in range(max_overlap, 0, -1):
        if previous[-size:] == current[:size]:
            return previous + current[size:], current[size:]
    return previous + current, current


def _read_field(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _parse_usage(usage: Any) -> dict[str, Any]:
    if usage is None:
        parsed = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        parsed.update(cache_summary(parsed))
        return parsed
    prompt_tokens = _read_field(usage, "prompt_tokens", _read_field(usage, "input_tokens", 0))
    completion_tokens = _read_field(usage, "completion_tokens", _read_field(usage, "output_tokens", 0))
    total_tokens = _read_field(usage, "total_tokens", 0)
    if not total_tokens:
        total_tokens = (prompt_tokens or 0) + (completion_tokens or 0)
    parsed: dict[str, Any] = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }
    prompt_details = _read_field(usage, "prompt_tokens_details")
    input_details = _read_field(usage, "input_tokens_details")

    def first_present(*candidates: tuple[Any, str]) -> Any:
        for obj, field in candidates:
            value = _read_field(obj, field)
            if value is not None:
                return value
        return None

    cache_hit = first_present(
        (usage, "prompt_cache_hit_tokens"),
        (usage, "cache_read_input_tokens"),
        (prompt_details, "cached_tokens"),
        (input_details, "cached_tokens"),
        (usage, "cached_tokens"),
    )
    cache_miss = first_present(
        (usage, "prompt_cache_miss_tokens"),
        (usage, "cache_miss_input_tokens"),
        (prompt_details, "cache_miss_tokens"),
        (input_details, "cache_miss_tokens"),
    )
    cache_write = first_present(
        (usage, "prompt_cache_write_tokens"),
        (usage, "cache_write_tokens"),
        (usage, "cache_write_input_tokens"),
        (usage, "cache_creation_input_tokens"),
        (prompt_details, "cache_write_tokens"),
        (input_details, "cache_write_tokens"),
        (prompt_details, "cache_creation_input_tokens"),
        (input_details, "cache_creation_input_tokens"),
    )
    if cache_hit is not None:
        parsed["prompt_cache_hit_tokens"] = cache_hit
    if cache_miss is not None:
        parsed["prompt_cache_miss_tokens"] = cache_miss
    if cache_write is not None:
        parsed["prompt_cache_write_tokens"] = cache_write
    details = _read_field(usage, "completion_tokens_details") or _read_field(usage, "output_tokens_details")
    reasoning = _read_field(details, "reasoning_tokens") if details is not None else None
    if reasoning is None:
        reasoning = _read_field(usage, "reasoning_tokens")
    if reasoning is not None:
        parsed["reasoning_tokens"] = reasoning
    parsed.update(cache_summary(parsed))
    return parsed


def _sdk_base_url(base_url: str) -> str:
    """Normalize a provider root without breaking path-qualified gateways."""
    value = base_url.rstrip("/")
    parsed = urlparse(value)
    if parsed.path and parsed.path != "/":
        return value
    return value + "/v1"


class OpenAICompatibleProvider:
    """The single LLM entry point used by the agent loop."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 180.0,
        max_retries: int = 4,
        tool_mode: str = "auto",
        protocol: str = "auto",
        reasoning_effort: str = "high",
        on_status: Callable[[dict[str, Any]], None] | None = None,
        sdk_client: Any = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._api_key = api_key
        self._max_retries = max(0, max_retries)
        if protocol not in ("auto", "responses", "chat_completions"):
            raise ValueError(f"protocol 非法: {protocol!r}")
        self._protocol = "responses" if protocol in ("auto", "responses") else "chat_completions"
        self._protocol_locked = protocol != "auto"
        if tool_mode not in ("auto", "native", "envelope"):
            raise ValueError(f"tool_mode 非法: {tool_mode!r}")
        self._mode = "envelope" if tool_mode == "envelope" else "native"
        self._mode_locked = tool_mode != "auto"
        normalized_effort = str(reasoning_effort or "high").strip().lower().replace("_", "-").replace(" ", "-")
        normalized_effort = {
            "standard": "mid",
            "medium": "mid",
            "very-high": "xhigh",
            "very high": "xhigh",
            "veryhigh": "xhigh",
            "maximum": "max",
            "高": "high",
            "极高": "xhigh",
            "最高": "max",
        }.get(normalized_effort, normalized_effort)
        if normalized_effort not in REASONING_WIRE_VALUES:
            raise ValueError(f"reasoning_effort 非法: {reasoning_effort!r}")
        self._requested_reasoning_effort = normalized_effort
        self._active_reasoning_effort = normalized_effort
        self._reasoning_enabled = True
        self._on_status = on_status
        self._client: Any = sdk_client

    # -- client --------------------------------------------------------------

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = AsyncOpenAI(
                base_url=_sdk_base_url(self.base_url),
                api_key=self._api_key,
                timeout=self.timeout,
                max_retries=0,
            )
        return self._client

    def tool_mode(self) -> str:
        return self._mode

    def protocol(self) -> str:
        """Return the active wire protocol after any automatic fallback."""
        return self._protocol

    def protocol_status(self) -> dict[str, str]:
        return {"active": self._protocol, "requested": "auto" if not self._protocol_locked else self._protocol}

    def reasoning_status(self) -> dict[str, Any]:
        """Expose adapter state without exposing provider reasoning text."""
        return {
            "requested": self._requested_reasoning_effort,
            "active": self._active_reasoning_effort if self._reasoning_enabled else "off",
            "wire_value": REASONING_WIRE_VALUES.get(self._active_reasoning_effort) if self._reasoning_enabled else None,
            "fallback": self._active_reasoning_effort != self._requested_reasoning_effort or not self._reasoning_enabled,
        }

    async def close(self) -> None:
        client, self._client = self._client, None
        if client is not None and hasattr(client, "close"):
            try:
                await client.close()
            except Exception:
                # A poisoned pool must never prevent task-level recovery from
                # replacing it. Closing is best effort after cancellation or
                # a broken event source.
                pass

    # -- public API ------------------------------------------------------------

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        on_delta: Callable[[str], None] | None = None,
    ) -> LLMResponse:
        """One assistant turn; streams text through on_delta when possible.

        Envelope conversion happens transparently: in envelope mode tool
        results are replayed as user messages and the model's JSON action
        is returned as a synthetic tool_call.
        """
        # max may negotiate through four lower levels before disabling the
        # optional parameter, so leave enough attempts for the full chain.
        for _ in range(6):
            use_native = self._mode == "native" and bool(tools)
            try:
                if self._protocol == "responses":
                    return await self._responses_once(messages, tools, on_delta, use_native)
                return await self._chat_completions_once(messages, tools, on_delta, use_native)
            except Exception as exc:
                if self._protocol == "responses" and not self._protocol_locked and self._looks_like_responses_rejection(exc):
                    self._protocol = "chat_completions"
                    self._emit_protocol_fallback(exc)
                    continue
                if (
                    self._protocol == "responses"
                    and not self._protocol_locked
                    and self._looks_like_responses_transport_failure(exc)
                ):
                    self._protocol = "chat_completions"
                    self._emit_transport_protocol_fallback(exc)
                    continue
                if not isinstance(exc, BadRequestError):
                    raise
                if use_native and self._looks_like_tools_rejection(exc):
                    self._mode = "envelope"
                    continue
                if self._reasoning_enabled and self._looks_like_reasoning_rejection(exc):
                    fallback = REASONING_FALLBACKS[self._active_reasoning_effort]
                    if fallback is None:
                        self._reasoning_enabled = False
                    else:
                        self._active_reasoning_effort = fallback
                    continue
                raise
        raise RuntimeError("模型协商失败：工具调用或推理参数无法降级")

    def _emit_protocol_fallback(self, exc: BaseException) -> None:
        if self._on_status is not None:
            self._on_status({
                "kind": "trace",
                "name": "provider",
                "status": "error",
                "phase": "planning",
                "code": "provider_protocol_fallback",
                "summary": "当前网关不支持 Responses API，已自动回退到 Chat Completions 并继续任务",
                "detail": {"protocol": "chat_completions", "error_type": type(exc).__name__},
            })

    def _emit_transport_protocol_fallback(self, exc: BaseException) -> None:
        if self._on_status is not None:
            self._on_status({
                "kind": "trace",
                "name": "provider",
                "status": "error",
                "phase": "planning",
                "code": "provider_transport_fallback",
                "summary": "Responses 连接在响应体阶段中断，已切换到 Chat Completions 继续任务",
                "detail": {"protocol": "chat_completions", "error_type": type(exc).__name__},
            })

    @staticmethod
    def _looks_like_responses_rejection(exc: BaseException) -> bool:
        if isinstance(exc, NotFoundError):
            return True
        text = str(exc).lower()
        return any(marker in text for marker in (
            "responses endpoint", "responses api", "unsupported endpoint",
            "not implemented", "method not allowed", "404", "405",
        ))

    @staticmethod
    def _looks_like_responses_transport_failure(exc: BaseException) -> bool:
        return _is_stream_retryable(exc) or _is_gateway_event_source_error(exc)

    @staticmethod
    def is_transient_failure(value: BaseException | str) -> bool:
        """Whether a failed model turn can be retried without replaying tools."""
        exc = value if isinstance(value, BaseException) else RuntimeError(str(value))
        return _is_retryable(exc) or _is_stream_retryable(exc)

    @staticmethod
    def _looks_like_tools_rejection(exc: BadRequestError) -> bool:
        text = str(exc).lower()
        return any(hint in text for hint in TOOLS_REJECTION_HINTS)

    @staticmethod
    def _looks_like_reasoning_rejection(exc: BadRequestError) -> bool:
        text = str(exc).lower()
        return "reasoning" in text and any(
            marker in text
            for marker in (
                "effort",
                "unsupported",
                "unknown",
                "invalid",
                "not support",
                "does not support",
            )
        )

    async def _chat_completions_once(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        on_delta: Callable[[str], None] | None,
        use_native: bool,
    ) -> LLMResponse:
        wire: list[dict[str, Any]]
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": None,  # set below
            "timeout": self.timeout,
        }
        if use_native and tools:
            wire = messages
            kwargs["tools"] = tools
        elif tools:
            wire = self._to_envelope_wire(messages, tools)
        else:
            wire = messages
        kwargs["messages"] = wire
        if self._reasoning_enabled:
            kwargs["reasoning_effort"] = REASONING_WIRE_VALUES[self._active_reasoning_effort]

        # Envelope actions are machine protocol, not user-facing output.  An
        # atomic request also prevents malformed JSON from flashing through the
        # live answer before the loop gets a chance to request a repair.
        if on_delta is None or (tools and self._mode == "envelope"):
            response = await self._create(kwargs)
            return self._finalize(self._to_response(response), tools)
        return await self._create_stream(kwargs, on_delta, tools)

    async def _responses_once(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        on_delta: Callable[[str], None] | None,
        use_native: bool,
    ) -> LLMResponse:
        """Run a durable Responses request and adapt it to the agent's wire shape.

        Responses requests deliberately complete atomically here.  This avoids
        tying a long model turn to a gateway SSE event source; tool progress
        still streams through the task timeline between model turns.
        """
        kwargs: dict[str, Any] = {
            "model": self.model,
            "input": self._to_responses_input(messages, tools if not use_native else None),
            "timeout": self.timeout,
        }
        if use_native and tools:
            kwargs["tools"] = self._to_responses_tools(tools)
        if self._reasoning_enabled:
            kwargs["reasoning"] = {"effort": REASONING_WIRE_VALUES[self._active_reasoning_effort]}
        response = await self._create_responses(kwargs)
        parsed = self._responses_to_response(response)
        if on_delta is not None and parsed.content and not (tools and self._mode == "envelope"):
            on_delta(parsed.content)
        return self._finalize(parsed, tools)

    async def _create_responses(self, kwargs: dict[str, Any]) -> Any:
        retryer = AsyncRetrying(
            # Some gateways expose Responses as an event-backed endpoint and
            # surface a body disconnect as a generic transport exception.
            retry=retry_if_exception(lambda exc: _is_retryable(exc) or _is_stream_retryable(exc)),
            wait=_wait_retry_after_or_exponential,
            stop=stop_after_attempt(self._max_retries + 1),
            before_sleep=self._emit_request_retry,
            reraise=True,
        )

        async def _attempt() -> Any:
            return await self.client.responses.create(**kwargs)

        return await retryer(_attempt)

    @staticmethod
    def _to_responses_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert Chat Completions function schemas to Responses function tools."""
        converted: list[dict[str, Any]] = []
        for tool in tools:
            function = tool.get("function") if isinstance(tool, dict) else None
            if not isinstance(function, dict):
                continue
            converted.append({
                "type": "function",
                "name": str(function.get("name") or ""),
                "description": str(function.get("description") or ""),
                "parameters": dict(function.get("parameters") or {"type": "object", "properties": {}}),
            })
        return converted

    def _to_responses_input(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None
    ) -> list[dict[str, Any]]:
        """Convert persisted Chat Completions history into Responses input items."""
        wire = self._to_envelope_wire(messages, tools) if tools else messages
        result: list[dict[str, Any]] = []
        for message in wire:
            role = str(message.get("role") or "user")
            if role == "tool":
                result.append({
                    "type": "function_call_output",
                    "call_id": str(message.get("tool_call_id") or ""),
                    "output": str(message.get("content") or ""),
                })
                continue
            if role == "assistant" and message.get("tool_calls"):
                content = message.get("content")
                if content:
                    result.append({"role": "assistant", "content": self._responses_content(content)})
                for call in message.get("tool_calls") or ():
                    function = call.get("function") if isinstance(call, dict) else None
                    if not isinstance(function, dict):
                        continue
                    result.append({
                        "type": "function_call",
                        "call_id": str(call.get("id") or ""),
                        "name": str(function.get("name") or ""),
                        "arguments": str(function.get("arguments") or "{}"),
                    })
                continue
            result.append({"role": role, "content": self._responses_content(message.get("content") or "")})
        return result

    @staticmethod
    def _responses_content(content: Any) -> Any:
        if not isinstance(content, list):
            return str(content)
        parts: list[dict[str, Any]] = []
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text":
                parts.append({"type": "input_text", "text": str(part.get("text") or "")})
            elif part.get("type") == "image_url":
                image = part.get("image_url")
                url = image.get("url") if isinstance(image, dict) else ""
                if url:
                    parts.append({"type": "input_image", "image_url": str(url)})
        return parts or ""

    @staticmethod
    def _responses_to_response(response: Any) -> LLMResponse:
        output = _read_field(response, "output", []) or []
        text_parts: list[str] = []
        calls: list[dict[str, Any]] = []
        for item in output:
            item_type = str(_read_field(item, "type", ""))
            if item_type == "function_call":
                calls.append({
                    "id": str(_read_field(item, "call_id", "") or _read_field(item, "id", "call-0")),
                    "type": "function",
                    "function": {
                        "name": str(_read_field(item, "name", "")),
                        "arguments": str(_read_field(item, "arguments", "{}")),
                    },
                })
                continue
            if item_type != "message":
                continue
            for part in _read_field(item, "content", []) or []:
                if str(_read_field(part, "type", "")) == "output_text":
                    value = _read_field(part, "text", "")
                    if value:
                        text_parts.append(str(value))
        if not text_parts:
            value = _read_field(response, "output_text", "")
            if value:
                text_parts.append(str(value))
        status = str(_read_field(response, "status", "completed"))
        return LLMResponse(
            content="".join(text_parts) or None,
            tool_calls=calls,
            usage=_parse_usage(_read_field(response, "usage")),
            finish_reason="stop" if status == "completed" else status,
            model=str(_read_field(response, "model", "") or ""),
        )

    # -- request plumbing ------------------------------------------------------

    async def _create(self, kwargs: dict[str, Any]) -> Any:
        retryer = AsyncRetrying(
            retry=retry_if_exception(lambda exc: _is_retryable(exc) or _is_stream_retryable(exc)),
            wait=_wait_retry_after_or_exponential,
            stop=stop_after_attempt(self._max_retries + 1),
            before_sleep=self._emit_request_retry,
            reraise=True,
        )

        async def _attempt() -> Any:
            return await self.client.chat.completions.create(**kwargs)

        return await retryer(_attempt)

    def _emit_request_retry(self, retry_state: RetryCallState) -> None:
        if self._on_status is None:
            return
        outcome = retry_state.outcome
        exception = outcome.exception() if outcome is not None else None
        try:
            self._on_status({
                "kind": "trace",
                "name": "provider",
                "status": "error",
                "phase": "planning",
                "code": "provider_request_retry",
                "summary": f"模型请求暂时失败，正在进行第 {retry_state.attempt_number + 1} 次尝试",
                "detail": {
                    "attempt": retry_state.attempt_number + 1,
                    "retry_limit": self._max_retries + 1,
                    "error_type": type(exception).__name__ if exception is not None else "unknown",
                },
            })
        except Exception:
            # Status reporting must never turn a recoverable provider failure
            # into a task failure.
            return

    async def _create_stream(
        self,
        kwargs: dict[str, Any],
        on_delta: Callable[[str], None],
        tools: list[dict[str, Any]] | None,
    ) -> LLMResponse:
        request_kwargs = dict(kwargs, stream=True)
        request_kwargs.setdefault("stream_options", {"include_usage": True})
        committed_text = ""
        committed_reasoning = ""

        for attempt in range(1, self._max_retries + 2):
            stream = None
            attempt_text = ""
            attempt_reasoning = ""
            tool_acc: dict[int, dict[str, Any]] = {}
            usage: dict[str, Any] = {}
            finish_reason = "stop"
            stream_completed = False
            model_name = self.model
            try:
                # Some gateways reject stream_options but support streaming.
                # Retry that negotiation independently from transport retries.
                try:
                    stream = await self._create(request_kwargs)
                except BadRequestError as exc:
                    detail = str(exc).lower()
                    if "stream_options" not in detail and "include_usage" not in detail:
                        raise
                    request_kwargs.pop("stream_options", None)
                    stream = await self._create(request_kwargs)

                async for chunk in stream:
                    model_name = getattr(chunk, "model", None) or model_name
                    chunk_usage = getattr(chunk, "usage", None)
                    if chunk_usage is not None:
                        usage = _parse_usage(chunk_usage)
                    choices = getattr(chunk, "choices", None)
                    if not choices:
                        continue
                    choice = choices[0]
                    if getattr(choice, "finish_reason", None):
                        finish_reason = choice.finish_reason
                        stream_completed = True
                    delta = getattr(choice, "delta", None)
                    if delta is None:
                        continue
                    content = getattr(delta, "content", None)
                    if content:
                        attempt_text, _ = _merge_stream_text(attempt_text, str(content))
                        committed_text, suffix = _merge_stream_text(committed_text, attempt_text)
                        if suffix:
                            on_delta(suffix)
                    reasoning = getattr(delta, "reasoning_content", None)
                    if reasoning:
                        attempt_reasoning, _ = _merge_stream_text(attempt_reasoning, str(reasoning))
                        committed_reasoning, _ = _merge_stream_text(committed_reasoning, attempt_reasoning)
                    for tc in getattr(delta, "tool_calls", None) or ():
                        index = getattr(tc, "index", 0) or 0
                        slot = tool_acc.setdefault(
                            index, {"id": "", "type": "function", "name": "", "arguments": ""}
                        )
                        if getattr(tc, "id", None):
                            slot["id"] = tc.id
                        function = getattr(tc, "function", None)
                        if function is not None:
                            if getattr(function, "name", None):
                                slot["name"], _ = _merge_stream_text(slot["name"], str(function.name))
                            if getattr(function, "arguments", None):
                                slot["arguments"], _ = _merge_stream_text(slot["arguments"], str(function.arguments))

                if not stream_completed:
                    raise RuntimeError("stream ended before completion")
                response = LLMResponse(
                    content=committed_text or None,
                    reasoning_content=committed_reasoning or None,
                    tool_calls=self._assembled_tool_calls(tool_acc),
                    usage=usage,
                    finish_reason=finish_reason,
                    model=model_name,
                )
                return self._finalize(response, tools)
            except Exception as exc:
                if stream is not None and hasattr(stream, "aclose"):
                    try:
                        await stream.aclose()
                    except Exception:
                        pass
                if attempt > self._max_retries or not _is_stream_retryable(exc):
                    raise
                if self._on_status is not None:
                    self._on_status({
                        "kind": "trace",
                        "name": "provider",
                        "status": "error",
                        "phase": "planning",
                        "code": "provider_retry",
                        "summary": f"模型流中断，正在进行第 {attempt + 1} 次重试",
                        "detail": {"attempt": attempt + 1, "retry_limit": self._max_retries + 1},
                    })
                await asyncio.sleep(_stream_retry_delay(exc, attempt))

        raise RuntimeError("stream retry loop exhausted")

    @staticmethod
    def _assembled_tool_calls(acc: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
        calls: list[dict[str, Any]] = []
        for index in sorted(acc):
            slot = acc[index]
            if not slot["name"]:
                continue
            calls.append(
                {
                    "id": slot["id"] or f"call-{index}",
                    "type": "function",
                    "function": {
                        "name": slot["name"],
                        "arguments": slot["arguments"] or "{}",
                    },
                }
            )
        return calls

    def _finalize(
        self, response: LLMResponse, tools: list[dict[str, Any]] | None
    ) -> LLMResponse:
        """Envelope mode: lift the JSON action out of content into tool_calls."""
        if self._mode == "envelope" and tools and not response.tool_calls:
            if response.content:
                synthetic = parse_envelope(response.content)
                if synthetic is not None:
                    response.tool_calls = [synthetic]
        return response

    @staticmethod
    def _to_response(response: Any) -> LLMResponse:
        choice = response.choices[0]
        msg = choice.message
        reasoning = getattr(msg, "reasoning_content", None)
        if not reasoning:
            reasoning = getattr(choice, "reasoning_content", None)
        tool_calls = []
        for tc in getattr(msg, "tool_calls", None) or ():
            function = getattr(tc, "function", None)
            tool_calls.append(
                {
                    "id": getattr(tc, "id", None) or "call-0",
                    "type": "function",
                    "function": {
                        "name": getattr(function, "name", "") if function else "",
                        "arguments": (
                            getattr(function, "arguments", "{}") if function else "{}"
                        ),
                    },
                }
            )
        return LLMResponse(
            content=getattr(msg, "content", None),
            reasoning_content=reasoning,
            tool_calls=tool_calls,
            usage=_parse_usage(getattr(response, "usage", None)),
            finish_reason=getattr(choice, "finish_reason", None) or "stop",
            model=getattr(response, "model", "") or "",
        )

    # -- envelope wire conversion ---------------------------------------------

    def _to_envelope_wire(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        tools_json = json.dumps(tools, indent=2, ensure_ascii=False)
        wire: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": envelope_system_suffix(tools_json),
            }
        ]
        pending_results: list[str] = []

        def flush_results() -> None:
            if pending_results:
                wire.append(
                    {
                        "role": "user",
                        "content": "\n\n".join(pending_results),
                    }
                )
                pending_results.clear()

        for msg in messages:
            role = msg.get("role")
            if role == "tool":
                name = msg.get("name") or msg.get("tool_call_id", "")
                pending_results.append(
                    f"TOOL_RESULT[{name}]: {msg.get('content', '')}"
                )
                continue
            flush_results()
            if role == "assistant" and msg.get("tool_calls"):
                # The envelope turn's JSON action already lives in content.
                wire.append({"role": "assistant", "content": msg.get("content") or ""})
                continue
            wire.append(dict(msg))
        flush_results()
        return wire
