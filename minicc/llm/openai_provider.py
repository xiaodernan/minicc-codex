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

TOOLS_REJECTION_HINTS = ("tool", "function")
REASONING_WIRE_VALUES = {
    "standard": "medium",
    "high": "high",
    # Some gateways expose OpenAI's xhigh spelling for the maximum budget.
    # chat() automatically falls back to high when the gateway does not.
    "max": "xhigh",
}


def _is_retryable(exc: BaseException) -> bool:
    return isinstance(exc, _RETRYABLE)


def _is_stream_retryable(exc: BaseException) -> bool:
    """The gateway can fail while an already-open chunked body is read."""
    if isinstance(exc, _STREAM_RETRYABLE):
        return True
    # A few compatible gateways leak the transport error as a generic SDK
    # exception while the response body is being consumed.
    text = str(exc).lower()
    return any(
        marker in text
        for marker in (
            "incomplete chunked read",
            "peer closed connection",
            "remote protocol error",
            "connection reset",
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
    return min(4.0, float(2 ** max(0, attempt - 1)))


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
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    parsed: dict[str, Any] = {
        "prompt_tokens": _read_field(usage, "prompt_tokens", 0),
        "completion_tokens": _read_field(usage, "completion_tokens", 0),
        "total_tokens": _read_field(usage, "total_tokens", 0),
    }
    for field in ("prompt_cache_hit_tokens", "prompt_cache_miss_tokens"):
        value = _read_field(usage, field)
        if value is not None:
            parsed[field] = value
    details = _read_field(usage, "completion_tokens_details")
    reasoning = _read_field(details, "reasoning_tokens") if details is not None else None
    if reasoning is None:
        reasoning = _read_field(usage, "reasoning_tokens")
    if reasoning is not None:
        parsed["reasoning_tokens"] = reasoning
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
        max_retries: int = 2,
        tool_mode: str = "auto",
        reasoning_effort: str = "high",
        on_status: Callable[[dict[str, Any]], None] | None = None,
        sdk_client: Any = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._api_key = api_key
        self._max_retries = max(0, max_retries)
        if tool_mode not in ("auto", "native", "envelope"):
            raise ValueError(f"tool_mode 非法: {tool_mode!r}")
        self._mode = "envelope" if tool_mode == "envelope" else "native"
        self._mode_locked = tool_mode != "auto"
        normalized_effort = str(reasoning_effort or "high").strip().lower().replace("_", "-").replace(" ", "-")
        normalized_effort = {
            "low": "standard",
            "medium": "standard",
            "very-high": "max",
            "very high": "max",
            "veryhigh": "max",
            "xhigh": "max",
            "maximum": "max",
            "高": "high",
            "极高": "max",
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

    def reasoning_status(self) -> dict[str, Any]:
        """Expose adapter state without exposing provider reasoning text."""
        return {
            "requested": self._requested_reasoning_effort,
            "active": self._active_reasoning_effort if self._reasoning_enabled else "off",
            "wire_value": REASONING_WIRE_VALUES.get(self._active_reasoning_effort) if self._reasoning_enabled else None,
            "fallback": self._active_reasoning_effort != self._requested_reasoning_effort or not self._reasoning_enabled,
        }

    async def close(self) -> None:
        if self._client is not None and hasattr(self._client, "close"):
            await self._client.close()
        self._client = None

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
        for _ in range(4):
            use_native = self._mode == "native" and bool(tools)
            try:
                return await self._chat_once(messages, tools, on_delta, use_native)
            except BadRequestError as exc:
                if use_native and self._looks_like_tools_rejection(exc):
                    self._mode = "envelope"
                    continue
                if self._reasoning_enabled and self._looks_like_reasoning_rejection(exc):
                    if self._active_reasoning_effort == "max":
                        self._active_reasoning_effort = "high"
                    elif self._active_reasoning_effort == "high":
                        self._active_reasoning_effort = "standard"
                    else:
                        self._reasoning_enabled = False
                    continue
                raise
        raise RuntimeError("模型协商失败：工具调用或推理参数无法降级")

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

    async def _chat_once(
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

        if on_delta is None:
            response = await self._create(kwargs)
            return self._finalize(self._to_response(response), tools)
        return await self._create_stream(kwargs, on_delta, tools)

    # -- request plumbing ------------------------------------------------------

    async def _create(self, kwargs: dict[str, Any]) -> Any:
        retryer = AsyncRetrying(
            retry=retry_if_exception(_is_retryable),
            wait=_wait_retry_after_or_exponential,
            stop=stop_after_attempt(self._max_retries + 1),
            reraise=True,
        )

        async def _attempt() -> Any:
            return await self.client.chat.completions.create(**kwargs)

        return await retryer(_attempt)

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
                    delta = getattr(choice, "delta", None)
                    if delta is None:
                        continue
                    content = getattr(delta, "content", None)
                    if content:
                        attempt_text += content
                        committed_text, suffix = _merge_stream_text(committed_text, attempt_text)
                        if suffix:
                            on_delta(suffix)
                    reasoning = getattr(delta, "reasoning_content", None)
                    if reasoning:
                        attempt_reasoning += reasoning
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
                                slot["name"] += function.name
                            if getattr(function, "arguments", None):
                                slot["arguments"] += function.arguments

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
