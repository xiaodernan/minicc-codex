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
import hashlib
import inspect
import json
import time
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

# The OpenAI SDK pulls in a very large module tree (hundreds of pydantic
# types); importing it eagerly made every importer -- including the
# web server and the test suite -- pay tens of seconds on start-up.
# Everything below is imported on first use instead.
_openai_sdk_cache = None


def _openai_sdk():
    global _openai_sdk_cache
    if _openai_sdk_cache is None:
        from openai import (
            APIConnectionError,
            APIError,
            APITimeoutError,
            AsyncOpenAI,
            BadRequestError,
            ConflictError,
            InternalServerError,
            NotFoundError,
            RateLimitError,
        )

        class _Sdk:
            pass

        sdk = _Sdk()
        sdk.APIConnectionError = APIConnectionError  # type: ignore[attr-defined]
        sdk.APIError = APIError  # type: ignore[attr-defined]
        sdk.APITimeoutError = APITimeoutError  # type: ignore[attr-defined]
        sdk.AsyncOpenAI = AsyncOpenAI  # type: ignore[attr-defined]
        sdk.BadRequestError = BadRequestError  # type: ignore[attr-defined]
        sdk.ConflictError = ConflictError  # type: ignore[attr-defined]
        sdk.InternalServerError = InternalServerError  # type: ignore[attr-defined]
        sdk.NotFoundError = NotFoundError  # type: ignore[attr-defined]
        sdk.RateLimitError = RateLimitError  # type: ignore[attr-defined]
        _openai_sdk_cache = sdk
    return _openai_sdk_cache


class AsyncOpenAI:
    """Lazy proxy for the real AsyncOpenAI.

    Keeps ``module.AsyncOpenAI(...)`` usable -- the test suite injects a
    factory via ``monkeypatch.setattr(provider_module, "AsyncOpenAI", factory)``
    -- while deferring the multi-megabyte ``openai`` import to first use.
    """

    def __new__(cls, *args, **kwargs):  # noqa: D102
        return _openai_sdk().AsyncOpenAI(*args, **kwargs)


from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception,
    stop_after_attempt,
)

from ..config import LLM_PROTOCOL_CHAT_COMPLETIONS, LLM_PROTOCOL_RESPONSES, LLM_PROTOCOLS, REASONING_EFFORT_ALIASES, TOOL_MODES
from .base import LLMResponse, is_nameless_tool_name, tool_call, unique_tool_call_id
from ..tools.schemas import tool_call_name
from ..trace import trace_event
from ..logging_setup import log_provider_event
from .envelope import EnvelopeParseError, _render_envelope_action, envelope_system_suffix, parse_envelope
from .stream_merge import AttemptTextAssembler, merge_retry_snapshot
from .base import retry_detail, stream_broke_message, stream_retry_summary
from .usage import (
    cache_summary,
    channel_counter,
    channel_status_payload,
    channel_switched_event,
    measured_usage,
    prefix_fingerprint,
    token_count,
)

_retryable_cache = None


def _retryable() -> tuple[type[BaseException], ...]:
    global _retryable_cache
    if _retryable_cache is None:
        sdk = _openai_sdk()
        _retryable_cache = (
            sdk.RateLimitError,
            sdk.ConflictError,
            sdk.InternalServerError,
            sdk.APITimeoutError,
            sdk.APIConnectionError,
        )
    return _retryable_cache

_stream_retryable_cache = None


def _stream_retryable() -> tuple[type[BaseException], ...]:
    global _stream_retryable_cache
    if _stream_retryable_cache is None:
        sdk = _openai_sdk()
        http_part = ()
        if httpx is not None:
            http_part = (
                httpx.RemoteProtocolError,
                httpx.ReadError,
                httpx.ReadTimeout,
                httpx.ConnectError,
                httpx.WriteError,
                httpx.PoolTimeout,
            )
        httpcore_part = tuple(
            getattr(httpcore, name)
            for name in ("RemoteProtocolError", "ReadError", "ReadTimeout", "ConnectError", "WriteError", "PoolTimeout")
            if httpcore is not None and hasattr(httpcore, name)
        )
        _stream_retryable_cache = _retryable() + http_part + httpcore_part
    return _stream_retryable_cache
_BUILTIN_STREAM_RETRYABLE = (ConnectionError, TimeoutError)
# M8-T897: tool-call/reasoning progress rides the status channel at most
# twice a second - enough to keep the workbench visibly alive during a
# multi-second planning turn, cheap enough not to flood the task timeline.
PROVIDER_PROGRESS_INTERVAL = 0.5
_MALFORMED_RESPONSE_HINTS = (
    "expecting value",
    "expecting property name enclosed",
    "expecting ',' delimiter",
    "unterminated string",
)

TOOLS_REJECTION_HINTS = ("tool", "function")
REASONING_WIRE_VALUES = {
    "low": "low",
    # Keep ``mid`` as the internal/UI label, but use the OpenAI/StepFun wire
    # spelling.  StepFun documents the middle tier as ``medium`` and rejects
    # ``mid`` instead of treating it as an alias.
    "mid": "medium",
    "high": "high",
    "xhigh": "xhigh",
    "max": "max",
    "ultra": "ultra",
}
REASONING_FALLBACKS = {
    "ultra": "max",
    "max": "xhigh",
    "xhigh": "high",
    "high": "mid",
    "mid": "low",
    "low": None,
}


def _status_logging_callback(
    callback: Callable[[dict[str, Any]], Any] | None,
    model: Callable[[], str],
) -> Callable[[dict[str, Any]], Any]:
    """Mirror every provider trace into the structured log (M8-T5).

    Logging happens before forwarding, so a status callback that raises cannot
    hide the retry record, and the propagation behaviour of the wrapped
    callback is unchanged. The wrapper is installed even with *no* callback:
    the CLI passes none, and without this a CLI provider retry would leave no
    trace anywhere on disk.
    """

    def _emit(event: dict[str, Any]) -> Any:
        log_provider_event(event, model=str(model() or ""))
        if callback is None:
            return None
        return callback(event)

    return _emit


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


class ResponsesPartialError(RuntimeError):
    """The Responses stream broke after deltas were already delivered.

    Retrying here would replay text the user has already seen, so the
    task-level recovery path (non-streaming replay) owns this failure.
    """


def _is_retryable(exc: BaseException) -> bool:
    return (
        isinstance(exc, _retryable())
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


class StreamProtocolError(RuntimeError):
    """The stream ended without a finish_reason: a protocol violation.

    This is never a transient transport failure — retrying would resend the
    full context and tool schemas (up to 5x per turn by default) against a
    gateway that can never complete. Fail fast with one request instead.
    """


def _is_stream_retryable(exc: BaseException) -> bool:
    """The gateway can fail while an already-open chunked body is read."""
    if isinstance(exc, StreamProtocolError):
        return False
    if isinstance(exc, _stream_retryable()) or isinstance(exc, _BUILTIN_STREAM_RETRYABLE):
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
        )
    )


def protocol_fallback_detail(exc: BaseException) -> dict[str, str]:
    """Trace detail for a fallback to the chat_completions protocol.

    Both fallback emitters (endpoint-level and transport-level) report the
    same fact: the Responses API path was abandoned in favour of Chat
    Completions because of this exception type. Keeping the shape here means
    the two traces stay comparable and a change to the reported protocol or
    error key lands once.
    """
    return {"protocol": LLM_PROTOCOL_CHAT_COMPLETIONS, "error_type": type(exc).__name__}


def redact_outbound_messages(messages: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Sanitize every message before it leaves the process (M8-T907).

    One home for the send-boundary shape: every dict/list/string is rebuilt
    through ``redact_message`` so the shipped bytes and the session store's
    bytes agree, the caller's live list is never touched, and a suspected
    secret is replaced before it reaches the gateway rather than only when
    it reaches the disk.
    """
    from ..tools.registry import redact_message

    return [redact_message(item) for item in (messages or [])]


def classify_provider_failure(exc: BaseException) -> bool | None:
    """Whether re-issuing a request to the provider could change the outcome.

    ``True`` covers transport and quota failures, ``False`` covers a request the
    provider rejected on purpose (content policy, bad credentials, unsupported
    parameter) - resending the same text gets the same answer.  ``None`` means
    the exception did not come through this HTTP stack at all, e.g. the
    Anthropic path raises its own ``RuntimeError`` or a caller raised while
    building the prompt, so no verdict is available and the caller must keep
    its conservative bounded retry.
    """
    if _is_retryable(exc) or _is_stream_retryable(exc):
        return True
    if isinstance(exc, _openai_sdk().APIError):
        return False
    if httpx is not None and isinstance(exc, httpx.HTTPError):
        return False
    return None


async def _close_stream(stream: Any) -> None:
    """Close a stream we may have stopped consuming early.

    Two spellings exist across the SDK's own types and both must be tried:
    async generators expose ``aclose()``, while ``AsyncStream`` only has an
    async ``close()`` that releases the underlying httpx response. An object
    left unclosed is closed later by ``asyncio.run()``'s shutdown hook, and
    httpcore2 answers that with "RuntimeError: generator didn't stop after
    athrow()" dumped to stderr - after an otherwise correct, exit-0 answer, so
    it reads as a crash. Teardown never propagates: it must not mask the real
    outcome.
    """
    for name in ("aclose", "close"):
        closer = getattr(stream, name, None)
        if closer is None:
            continue
        try:
            result = closer()
            if inspect.isawaitable(result):
                await result
        except Exception:  # noqa: BLE001 - teardown noise is not the user's error
            pass
        return


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


# A per-minute quota cannot be cleared by waiting seconds - the window itself is
# 60s. Plain exponential backoff (1+2+4+8) spends the whole attempt budget before
# the limiter resets, so a 10-RPM gateway turned tasks into hard failures.
_BACKOFF_CAP_SECONDS = 60.0
_RATE_LIMIT_BACKOFF_BASE_SECONDS = 15.0


def _is_rate_limit(exc: BaseException) -> bool:
    if isinstance(exc, _openai_sdk().RateLimitError):
        return True
    text = _exception_text(exc).lower()
    return "429" in text and any(
        marker in text for marker in ("rate limit", "too many requests", "rpm", "qps")
    )


def _wait_retry_after_or_exponential(retry_state: RetryCallState) -> float:
    outcome = retry_state.outcome
    exception = outcome.exception() if outcome is not None else None
    retry_after = _retry_after_seconds(exception) if exception is not None else None
    if retry_after is not None:
        return retry_after
    attempts_so_far = max(0, retry_state.attempt_number - 1)
    if exception is not None and _is_rate_limit(exception):
        return min(
            _BACKOFF_CAP_SECONDS,
            _RATE_LIMIT_BACKOFF_BASE_SECONDS * float(2**attempts_so_far),
        )
    return min(_BACKOFF_CAP_SECONDS, float(2**attempts_so_far))


def _stream_retry_delay(exc: BaseException, attempt: int) -> float:
    retry_after = _retry_after_seconds(exc)
    if retry_after is not None:
        return min(8.0, retry_after)
    return min(12.0, float(2 ** max(0, attempt - 1)))


def _merge_stream_text(previous: str, current: str) -> tuple[str, str]:
    """Merge a retried full response and return only the new suffix.

    Kept for backwards compatibility (tests import it directly); new code
    should use :mod:`minicc.llm.stream_merge` — ``append_delta`` for
    incremental fragments, ``merge_retry_snapshot`` for retry snapshots.
    """
    return merge_retry_snapshot(previous, current)


#: M8-T356: the id repair lives in ``minicc.llm.base`` now (both wire
#: readers ask it).  The old name stays importable because the M1-T2
#: contract test imports it from here.
_unique_tool_call_id = unique_tool_call_id


def _read_field(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _parse_usage(usage: Any) -> dict[str, Any]:
    if usage is None:
        parsed = measured_usage(0, 0)
        parsed.update(cache_summary(parsed))
        return parsed
    # M8-T358: the gateway's counters are untrusted input.  The totals used
    # to be summed straight from them, so a dict in one field raised
    # TypeError and killed the turn; the cache counters were already
    # guarded, which is why the same malformed usage crashed on one field
    # and not on another.  The shared reader has two defaults: 0 for a
    # counter we cannot read (both wires agree on that number) and None
    # for the cache counters the OpenAI-compatible wire simply omits.
    prompt_tokens = token_count(
        _read_field(usage, "prompt_tokens", _read_field(usage, "input_tokens", 0)), 0
    ) or 0
    completion_tokens = token_count(
        _read_field(usage, "completion_tokens", _read_field(usage, "output_tokens", 0)), 0
    ) or 0
    total_tokens = token_count(_read_field(usage, "total_tokens", 0), 0) or 0
    if not total_tokens:
        total_tokens = (prompt_tokens or 0) + (completion_tokens or 0)
    parsed: dict[str, Any] = measured_usage(prompt_tokens, completion_tokens, total_tokens)
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
        count = token_count(cache_hit)
        if count is not None:
            parsed["prompt_cache_hit_tokens"] = count
    if cache_miss is not None:
        count = token_count(cache_miss)
        if count is not None:
            parsed["prompt_cache_miss_tokens"] = count
    if cache_write is not None:
        count = token_count(cache_write)
        if count is not None:
            parsed["prompt_cache_write_tokens"] = count
    details = _read_field(usage, "completion_tokens_details") or _read_field(usage, "output_tokens_details")
    reasoning = _read_field(details, "reasoning_tokens") if details is not None else None
    if reasoning is None:
        reasoning = _read_field(usage, "reasoning_tokens")
    if reasoning is not None:
        count = token_count(reasoning)
        if count is not None:
            parsed["reasoning_tokens"] = count
    parsed.update(cache_summary(parsed))
    return parsed


#: Error codes the gateway returns when a quota pool is empty (docs:
#: api-reference/error-codes — 402 insufficient balance, 429 credit-limit
#: variants). A plain rate-limit 429 is NOT here: it means "slow down", not
#: "this channel has no money left", and must keep its own retry semantics.
_QUOTA_EXHAUSTED_CODES = (
    "insufficient_credit",
    "project_credit_limit_exceeded",
    "member_project_credit_limit_exceeded",
)


#: 其余协议家族的工具调用标记——信封模式下出现即视为「想调工具但格式
#: 不对」，进协议修复而不是当最终答案交付。
_FOREIGN_TOOL_CALL_MARKERS = ("<tool_call>", "<function=", "</function>")


def _exc_body_text(exc: BaseException) -> str:
    body = getattr(exc, "body", None)
    if isinstance(body, str):
        text = body
    elif body is not None:
        try:
            text = json.dumps(body, ensure_ascii=False)
        except (TypeError, ValueError):
            text = str(body)
    else:
        text = str(exc)
    message = str(getattr(exc, "message", "") or "")
    return f"{text}\n{message}"


def _is_quota_exhausted(exc: BaseException) -> bool:
    """True when the error says this channel's quota pool is empty.

    402 is unambiguous (余额不足). A 429 only counts when the body carries one
    of the credit-limit codes — a bare rate-limit 429 means the caller should
    retry slower, not that the channel is dead.
    """
    status = getattr(exc, "status_code", None)
    if status == 402:
        return True
    if status == 429 or type(exc).__name__ == "RateLimitError":
        text = _exc_body_text(exc)
        return any(code in text for code in _QUOTA_EXHAUSTED_CODES)
    return False


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
        plan_base_url: str = "",
        plan_api_key: str = "",
        prompt_cache_key: str = "",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        # M8-T878: explicit cache-affinity key, or one derived from the
        # gateway+model pair.  Gateways with several upstream shards (the
        # common OpenAI-compatible proxy shape) route similar requests to the
        # same shard by this key; without it the same 22k-token system prompt
        # can land on a cold shard on every call.  Empty means "derive".
        self._prompt_cache_key = str(prompt_cache_key or "").strip()[:64]
        self._api_key = api_key
        self._max_retries = max(0, max_retries)
        if protocol not in LLM_PROTOCOLS:
            raise ValueError(f"protocol 非法: {protocol!r}")
        self._protocol = LLM_PROTOCOL_RESPONSES if protocol in ("auto", LLM_PROTOCOL_RESPONSES) else LLM_PROTOCOL_CHAT_COMPLETIONS
        self._protocol_locked = protocol != "auto"
        if tool_mode not in TOOL_MODES:
            raise ValueError(f"tool_mode 非法: {tool_mode!r}")
        self._mode = "envelope" if tool_mode == "envelope" else "native"
        self._mode_locked = tool_mode != "auto"
        normalized_effort = str(reasoning_effort or "high").strip().lower().replace("_", "-").replace(" ", "-")
        normalized_effort = REASONING_EFFORT_ALIASES.get(normalized_effort, normalized_effort)
        if normalized_effort not in REASONING_WIRE_VALUES:
            raise ValueError(f"reasoning_effort 非法: {reasoning_effort!r}")
        self._requested_reasoning_effort = normalized_effort
        self._active_reasoning_effort = normalized_effort
        self._reasoning_enabled = True
        self._on_status = _status_logging_callback(on_status, lambda: self.model)
        self._client: Any = sdk_client
        self._init_plan_channel(plan_base_url, plan_api_key)

    # -- dual channel (M8-T55) ------------------------------------------------

    def _init_plan_channel(self, plan_base_url: str, plan_api_key: str) -> None:
        """Optional second channel that takes over when the primary quota dies.

        Step Plan (subscription Credit pool) and the pay-as-you-go API share
        the same API key type but live on different base URLs with independent
        quotas. ``paid`` exhausts mid-task with HTTP 402 / credit-flavoured
        429; the provider then flips to the plan channel sticky for the rest
        of the process instead of killing the task.
        """
        self._plan_base_url = (plan_base_url or "").rstrip("/")
        self._plan_api_key = plan_api_key or ""
        self._channel = "paid"
        self._plan_client: Any = None
        self._channel_usage: dict[str, dict[str, int]] = {
            "paid": channel_counter(),
            "plan": channel_counter(),
        }

    def _has_plan_channel(self) -> bool:
        return bool(getattr(self, "_plan_base_url", "")) and bool(getattr(self, "_plan_api_key", ""))

    def _effective_prompt_cache_key(self) -> str:
        """Stable affinity key for the gateway's upstream prefix cache.

        The derived default is a salted hash of gateway+model — opaque and
        free of workspace paths, but stable across processes so a warm cache
        survives restarts.  An explicit MINICC_PROMPT_CACHE_KEY always wins.
        """
        if self._prompt_cache_key:
            return self._prompt_cache_key
        digest = hashlib.sha256(f"{self.base_url}|{self.model}".encode("utf-8")).hexdigest()[:16]
        return f"minicc-{digest}"

    @property
    def active_channel(self) -> str:
        return getattr(self, "_channel", "paid")

    def channel_status(self) -> dict[str, Any]:
        """Mirror protocol_status(): what the wire is doing right now."""
        return channel_status_payload(
            self.active_channel,
            self._has_plan_channel(),
            getattr(self, "_channel_usage", {}),
        )

    def _active_client(self) -> Any:
        if self.active_channel == "plan":
            if self._plan_client is None:
                self._plan_client = AsyncOpenAI(
                    base_url=_sdk_base_url(self._plan_base_url),
                    api_key=self._plan_api_key,
                    timeout=self.timeout,
                    max_retries=0,
                )
            return self._plan_client
        return self.client

    def _record_channel_usage(self, response: LLMResponse) -> None:
        usage = response.usage if isinstance(response.usage, dict) else {}
        usage["channel"] = self.active_channel
        try:
            tokens = int(usage.get("total_tokens") or 0)
        except (TypeError, ValueError):
            tokens = 0
        counters = self._channel_usage.setdefault(self.active_channel, channel_counter())
        counters["requests"] += 1
        if tokens > 0:
            counters["total_tokens"] += tokens

    def _emit_channel_switch(self, exc: BaseException) -> None:
        if self._on_status is not None:
            self._on_status(channel_switched_event(
                getattr(exc, "status_code", None), type(exc).__name__,
            ))

    async def _attempt_once(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        on_delta: Callable[[str], None] | None,
        use_native: bool,
    ) -> LLMResponse:
        """One negotiation attempt, with a one-shot sticky flip to the plan channel.

        The flip lives here rather than in the negotiation loop above so a
        quota death cannot be mistaken for a protocol/tool fallback, and so
        the plan retry inherits the same loop guards.

        M8-T907: the outbound copy is sanitized before it leaves the
        process. The session store sanitizes at save time; a store-only
        redaction meant the disk history diverged from the bytes shipped
        one turn earlier and the gateway's prefix cache died from the first
        redacted message onward. Sanitizing at the send boundary makes the
        shipped shape and the stored shape byte-identical - and a secret
        never reaches the gateway at all. The caller's list is never
        mutated: the copy rides this attempt only.
        """
        outbound = redact_outbound_messages(messages)
        try:
            if self._protocol == LLM_PROTOCOL_RESPONSES:
                response = await self._responses_once(outbound, tools, on_delta, use_native)
            else:
                response = await self._chat_completions_once(outbound, tools, on_delta, use_native)
            # M8-T907: ship the prefix shape with the usage record so a dead
            # prefix cache is diagnosable from the task snapshot alone. The
            # fingerprint reads the sanitized shape - the bytes that actually
            # left the process.
            if isinstance(response.usage, dict):
                response.usage.update(prefix_fingerprint(outbound, tools))
            self._record_channel_usage(response)
            return response
        except Exception as exc:
            if (
                self.active_channel != "paid"
                or not self._has_plan_channel()
                or not _is_quota_exhausted(exc)
            ):
                raise
            self._channel = "plan"
            self._emit_channel_switch(exc)
            if self._protocol == LLM_PROTOCOL_RESPONSES:
                response = await self._responses_once(outbound, tools, on_delta, use_native)
            else:
                response = await self._chat_completions_once(outbound, tools, on_delta, use_native)
            if isinstance(response.usage, dict):
                response.usage.update(prefix_fingerprint(outbound, tools))
            self._record_channel_usage(response)
            return response

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
        plan_client, self._plan_client = getattr(self, "_plan_client", None), None
        for candidate in (client, plan_client):
            if candidate is not None and hasattr(candidate, "close"):
                try:
                    await candidate.close()
                except Exception:
                    # A poisoned pool must never prevent task-level recovery
                    # from replacing it. Closing is best effort after
                    # cancellation or a broken event source.
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
        # Allow every effort level, disabling reasoning, and the independent
        # protocol/tool fallbacks to negotiate before exhausting attempts.
        for _ in range(len(REASONING_FALLBACKS) + 3):
            use_native = self._mode == "native" and bool(tools)
            try:
                return await self._attempt_once(messages, tools, on_delta, use_native)
            except Exception as exc:
                if self._protocol == LLM_PROTOCOL_RESPONSES and not self._protocol_locked and self._looks_like_responses_rejection(exc):
                    self._protocol = LLM_PROTOCOL_CHAT_COMPLETIONS
                    self._emit_protocol_fallback(exc)
                    continue
                if (
                    self._protocol == LLM_PROTOCOL_RESPONSES
                    and not self._protocol_locked
                    and self._looks_like_responses_transport_failure(exc)
                ):
                    self._protocol = LLM_PROTOCOL_CHAT_COMPLETIONS
                    self._emit_transport_protocol_fallback(exc)
                    continue
                if not isinstance(exc, _openai_sdk().BadRequestError):
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
        from ..agent.protocol import PHASE_PLANNING

        if self._on_status is not None:
            self._on_status(trace_event(
                name="provider",
                status="error",
                phase=PHASE_PLANNING,
                code="provider_protocol_fallback",
                summary="当前网关不支持 Responses API，已自动回退到 Chat Completions 并继续任务",
                detail=protocol_fallback_detail(exc),
            ))

    def _emit_transport_protocol_fallback(self, exc: BaseException) -> None:
        from ..agent.protocol import PHASE_PLANNING

        if self._on_status is not None:
            self._on_status(trace_event(
                name="provider",
                status="error",
                phase=PHASE_PLANNING,
                code="provider_transport_fallback",
                summary="Responses 连接在响应体阶段中断，已切换到 Chat Completions 继续任务",
                detail=protocol_fallback_detail(exc),
            ))

    @staticmethod
    def _looks_like_responses_rejection(exc: BaseException) -> bool:
        if isinstance(exc, _openai_sdk().NotFoundError):
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
            "prompt_cache_key": self._effective_prompt_cache_key(),
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
            "store": False,
            "timeout": self.timeout,
            "prompt_cache_key": self._effective_prompt_cache_key(),
        }
        if use_native and tools:
            kwargs["tools"] = self._to_responses_tools(tools)
        if self._reasoning_enabled:
            kwargs["reasoning"] = {"effort": REASONING_WIRE_VALUES[self._active_reasoning_effort]}
        if on_delta is not None and not (tools and self._mode == "envelope"):
            return await self._create_responses_stream(kwargs, on_delta, tools)
        response = await self._create_responses(kwargs)
        parsed = self._responses_to_response(response)
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
            return await self._active_client().responses.create(**kwargs)

        return await retryer(_attempt)

    async def _create_responses_stream(
        self,
        kwargs: dict[str, Any],
        on_delta: Callable[[str], None],
        tools: list[dict[str, Any]] | None,
    ) -> LLMResponse:
        """Stream Responses text deltas to the UI while returning the final
        structured response (tool calls, usage) from the completed event.

        Retries only before the first delta is delivered; a mid-stream break
        raises ResponsesPartialError so the recovery path replays atomically
        instead of duplicating visible text.
        """
        retryer = AsyncRetrying(
            retry=retry_if_exception(
                lambda exc: not isinstance(exc, ResponsesPartialError)
                and (_is_retryable(exc) or _is_stream_retryable(exc))
            ),
            wait=_wait_retry_after_or_exponential,
            stop=stop_after_attempt(self._max_retries + 1),
            before_sleep=self._emit_request_retry,
            reraise=True,
        )
        emitted = {"chars": 0}

        async def _attempt() -> LLMResponse:
            emitted["chars"] = 0
            # M8-T897: planning turns emit function calls, not text - without
            # this bookkeeping the model turn is radio silence for tens of
            # seconds and the workbench reads as "not streaming".  Tool-call
            # progress rides the status channel (trace events), never
            # on_delta, so the answer stream stays byte-clean.
            tool_progress = {"tool": "", "chars": 0, "last": 0.0, "announced": False}
            reasoning_progress = {"chars": 0, "last": 0.0}
            stream_kwargs = dict(kwargs)
            stream_kwargs["stream"] = True
            stream = await self._active_client().responses.create(**stream_kwargs)
            final = None
            try:
                async for event in stream:
                    event_type = str(getattr(event, "type", "") or "")
                    if event_type == "response.output_text.delta":
                        delta = str(getattr(event, "delta", "") or "")
                        if delta:
                            emitted["chars"] += len(delta)
                            on_delta(delta)
                    elif event_type == "response.output_item.added":
                        item = getattr(event, "item", None)
                        if item is not None and str(getattr(item, "type", "") or "") == "function_call":
                            tool_progress["tool"] = str(getattr(item, "name", "") or "")
                            tool_progress["chars"] = 0
                            tool_progress["announced"] = True
                            self._emit_provider_progress(
                                code="provider_tool_call_start",
                                summary=f"正在生成工具调用 {tool_progress['tool']}" if tool_progress["tool"] else "正在生成工具调用",
                                detail={"tool": tool_progress["tool"]},
                                )
                    elif event_type == "response.function_call_arguments.delta":
                        delta = str(getattr(event, "delta", "") or "")
                        if delta:
                            tool_progress["chars"] += len(delta)
                            now = time.monotonic()
                            if now - tool_progress["last"] >= PROVIDER_PROGRESS_INTERVAL:
                                tool_progress["last"] = now
                                self._emit_provider_progress(
                                    code="provider_tool_call_progress",
                                    summary=f"工具参数流式生成中 · {tool_progress['tool'] or '?'} · {tool_progress['chars']} 字符",
                                    detail={"tool": tool_progress["tool"], "chars": tool_progress["chars"]},
                                    )
                    elif event_type == "response.function_call_arguments.done":
                        if tool_progress["announced"] and tool_progress["chars"]:
                            self._emit_provider_progress(
                                code="provider_tool_call_progress",
                                summary=f"工具调用已成形 · {tool_progress['tool'] or '?'} · {tool_progress['chars']} 字符",
                                detail={"tool": tool_progress["tool"], "chars": tool_progress["chars"], "done": True},
                                )
                    elif event_type in {
                        "response.reasoning_summary_text.delta",
                        "response.reasoning_text.delta",
                    }:
                        delta = str(getattr(event, "delta", "") or "")
                        if delta:
                            reasoning_progress["chars"] += len(delta)
                            now = time.monotonic()
                            if now - reasoning_progress["last"] >= PROVIDER_PROGRESS_INTERVAL:
                                reasoning_progress["last"] = now
                                self._emit_provider_progress(
                                    code="provider_reasoning_progress",
                                    summary=f"推理进行中 · {reasoning_progress['chars']} 字符",
                                    detail={"chars": reasoning_progress["chars"]},
                                    )
                    elif event_type in {"response.completed", "response.incomplete", "response.failed"}:
                        final = getattr(event, "response", None)
                if final is None:
                    get_final = getattr(stream, "get_final_response", None)
                    if get_final is not None:
                        final = await get_final()
            except ResponsesPartialError:
                raise
            except Exception as exc:
                if emitted["chars"] == 0:
                    raise
                raise ResponsesPartialError(
                    stream_broke_message(LLM_PROTOCOL_RESPONSES, emitted["chars"], exc)
                ) from exc
            finally:
                await _close_stream(stream)
            if final is None:
                if emitted["chars"] == 0:
                    raise RuntimeError("Responses 流式请求未返回最终响应")
                raise ResponsesPartialError(
                    f"responses stream ended without a final response after {emitted['chars']} chars"
                )
            return self._responses_to_response(final)

        parsed = await retryer(_attempt)
        return self._finalize(parsed, tools)

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
                        # M8-T347: the Responses wire carries the name the
                        # dispatcher used - one home for a wire name
                        # (``tool_call_name``).  The API only accepts the
                        # names it was told about.
                        "name": tool_call_name(call),
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
        seen_ids: set[str] = set()
        for index, item in enumerate(output):
            item_type = str(_read_field(item, "type", ""))
            if item_type == "function_call":
                # M8-T820: ask the one-home predicate about the **raw** value
                # before stringifying.  A real gateway (wkapi.pro /v1,
                # gpt-6-sol) sometimes emits ``name: null``; ``str(None)``
                # is the literal ``"None"`` - a non-empty string that sails
                # past ``is_nameless_tool_name`` and becomes a paid
                # ``[UNKNOWN_TOOL] 'None'`` + ``[DUPLICATE_TOOL_CALL]`` pair.
                # The predicate already knows ``None`` is nameless; give it
                # the None instead of laundering it into a fake tool name.
                raw_name = _read_field(item, "name", "")
                if is_nameless_tool_name(raw_name):
                    # M8-T335: the rule M8-T334 settled on the two
                    # chat-completions paths also binds here - a "function
                    # call" that names no tool is noise, not a call for a
                    # tool the registry does not have.
                    continue
                name = str(raw_name)
                calls.append(tool_call(
                    _unique_tool_call_id(
                        str(_read_field(item, "call_id", "") or _read_field(item, "id", "")),
                        f"responses-{index}",
                        seen_ids,
                    ),
                    name,
                    str(_read_field(item, "arguments", "{}")),
                ))
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
            return await self._active_client().chat.completions.create(**kwargs)

        return await retryer(_attempt)

    def _emit_provider_progress(self, code: str, summary: str, detail: dict[str, Any]) -> None:
        """One throttled planning-turn progress event on the status channel.

        M8-T897: the responses stream answers a tool-call turn with
        ``function_call_arguments.delta`` events that carry no answer text -
        before this channel existed the workbench sat silent for the whole
        planning turn and read as a non-streaming gateway.  Progress must
        never fail the turn, so every failure path stays silent.
        """
        if self._on_status is None:
            return
        try:
            from ..agent.protocol import PHASE_PLANNING

            self._on_status(trace_event(
                name="provider",
                status="ok",
                phase=PHASE_PLANNING,
                code=code,
                summary=summary,
                detail=detail,
            ))
        except Exception:
            # Progress reporting must never turn a streaming model turn
            # into a task failure - same contract as _emit_request_retry.
            return

    def _emit_request_retry(self, retry_state: RetryCallState) -> None:
        from ..agent.protocol import PHASE_PLANNING

        if self._on_status is None:
            return
        outcome = retry_state.outcome
        exception = outcome.exception() if outcome is not None else None
        try:
            self._on_status(trace_event(
                name="provider",
                status="error",
                phase=PHASE_PLANNING,
                code="provider_request_retry",
                summary=f"模型请求暂时失败，正在进行第 {retry_state.attempt_number + 1} 次尝试",
                detail={
                    "attempt": retry_state.attempt_number + 1,
                    "retry_limit": self._max_retries + 1,
                    "error_type": type(exception).__name__ if exception is not None else "unknown",
                },
            ))
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
        from ..agent.protocol import PHASE_PLANNING, PROVIDER_RETRY_CODE
        request_kwargs = dict(kwargs, stream=True)
        request_kwargs.setdefault("stream_options", {"include_usage": True})
        committed_text = ""
        committed_reasoning = ""

        for attempt in range(1, self._max_retries + 2):
            stream = None
            iterator: Any = None
            attempt_text = AttemptTextAssembler()
            attempt_reasoning = AttemptTextAssembler()
            tool_acc: dict[int, dict[str, Any]] = {}
            usage: dict[str, Any] = {}
            finish_reason = "stop"
            stream_completed = False
            model_name = self.model
            # M8-T900: same progress contract as the Responses path (T897) -
            # planning turns must be visibly alive on every protocol, with
            # the answer stream untouched.
            tool_stream_chars = 0
            tool_stream_last = 0.0
            reasoning_stream_chars = 0
            reasoning_stream_last = 0.0
            try:
                # Some gateways reject stream_options but support streaming.
                # Retry that negotiation independently from transport retries.
                try:
                    stream = await self._create(request_kwargs)
                except _openai_sdk().BadRequestError as exc:
                    detail = str(exc).lower()
                    if "stream_options" not in detail and "include_usage" not in detail:
                        raise
                    request_kwargs.pop("stream_options", None)
                    stream = await self._create(request_kwargs)

                # AsyncStream.__aiter__ is itself an async generator, so the
                # object iterated here is a second thing that must be closed.
                iterator = stream.__aiter__() if hasattr(stream, "__aiter__") else stream
                async for chunk in iterator:
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
                        # M1-T3: one attempt may carry incremental fragments
                        # (append) or cumulative snapshots (streak-detected).
                        # Never overlap-dedup incremental fragments (P0-1).
                        merged = attempt_text.feed(str(content))
                        committed_text, suffix = merge_retry_snapshot(committed_text, merged)
                        if attempt_text.latched_now:
                            # The snapshot is the truth for this attempt, so
                            # rebase the buffer onto it; the suffix above is
                            # still emitted, because hiding what was already
                            # streamed would shorten the visible answer.
                            committed_text = merged
                        if suffix:
                            on_delta(suffix)
                    reasoning = getattr(delta, "reasoning_content", None)
                    if reasoning:
                        merged_reasoning = attempt_reasoning.feed(str(reasoning))
                        if attempt_reasoning.latched_now:
                            committed_reasoning = merged_reasoning
                        else:
                            committed_reasoning, _ = merge_retry_snapshot(
                                committed_reasoning, merged_reasoning
                            )
                        reasoning_stream_chars += len(str(reasoning))
                        now = time.monotonic()
                        if now - reasoning_stream_last >= PROVIDER_PROGRESS_INTERVAL:
                            reasoning_stream_last = now
                            self._emit_provider_progress(
                                code="provider_reasoning_progress",
                                summary=f"推理进行中 · {reasoning_stream_chars} 字符",
                                detail={"chars": reasoning_stream_chars},
                                )
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
                                incoming = str(function.name)
                                if not slot["name"]:
                                    slot["name"] = incoming
                                    self._emit_provider_progress(
                                        code="provider_tool_call_start",
                                        summary=f"正在生成工具调用 {incoming}",
                                        detail={"tool": incoming},
                                        )
                                else:
                                    slot["name"] = slot["name"] + incoming
                            if getattr(function, "arguments", None):
                                fragment = str(function.arguments)
                                slot["arguments"] = slot["arguments"] + fragment
                                tool_stream_chars += len(fragment)
                                now = time.monotonic()
                                if now - tool_stream_last >= PROVIDER_PROGRESS_INTERVAL:
                                    tool_stream_last = now
                                    self._emit_provider_progress(
                                        code="provider_tool_call_progress",
                                        summary=f"工具参数流式生成中 · {slot['name'] or '?'} · {tool_stream_chars} 字符",
                                        detail={"tool": slot["name"], "chars": tool_stream_chars},
                                        )

                if not stream_completed:
                    raise StreamProtocolError("stream ended before completion")
                if tool_stream_chars:
                    names = [str(slot.get("name") or "") for slot in tool_acc.values() if slot.get("name")]
                    self._emit_provider_progress(
                        code="provider_tool_call_progress",
                        summary=f"工具调用已成形 · {', '.join(names) or '?'} · {tool_stream_chars} 字符",
                        detail={"tool": names[0] if len(names) == 1 else ",".join(names), "chars": tool_stream_chars, "done": True},
                        )
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
                if attempt > self._max_retries or not _is_stream_retryable(exc):
                    raise
                if self._on_status is not None:
                    self._on_status(trace_event(
                        name="provider",
                        status="error",
                        phase=PHASE_PLANNING,
                        code=PROVIDER_RETRY_CODE,
                        summary=stream_retry_summary(attempt + 1),
                        detail=retry_detail(attempt + 1, self._max_retries + 1),
                    ))
                await asyncio.sleep(_stream_retry_delay(exc, attempt))
            finally:
                # Every exit path - delivered response, raised protocol error,
                # retry - abandons this attempt's stream, so close both the
                # iteration and the stream that produced it.
                await _close_stream(iterator)
                await _close_stream(stream)

        raise RuntimeError("stream retry loop exhausted")

    @staticmethod
    def _assembled_tool_calls(acc: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
        calls: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for index in sorted(acc):
            slot = acc[index]
            if is_nameless_tool_name(slot["name"]):
                continue
            call_id = _unique_tool_call_id(str(slot["id"] or ""), f"call-{index}", seen_ids)
            calls.append(
                tool_call(
                    call_id,
                    slot["name"],
                    slot["arguments"] or "{}",
                )
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
                # M8-T61: 信封模式里模型输出了**其他格式的工具调用**（如
                # 训练带来的 <tool_call> XML）而没有任何 JSON 动作——这些
                # 文本不是最终答案，静默交付会让整个任务空转（真网关实测：
                # 4 轮零工具调用，完成评审到上限）。抛给循环的协议修复
                # 路径，带上模型自己的输出作为纠错上下文。
                if any(marker in response.content for marker in _FOREIGN_TOOL_CALL_MARKERS):
                    raise EnvelopeParseError(
                        "模型输出了非信封格式的工具调用（检测到 <tool_call>/<function> 标记）。"
                        '信封模式下工具调用必须是单个 JSON 对象：{"action":"工具名","params":{...}}。',
                        content=response.content,
                    )
        return response

    @staticmethod
    def _to_response(response: Any) -> LLMResponse:
        choices = getattr(response, "choices", None) or []
        if not choices:
            # M8-T334: a gateway can answer with an empty ``choices``.  The
            # streaming path skips such a chunk (``if not choices:
            # continue``) and the Responses path handles it gracefully - but
            # the one-shot path indexed ``choices[0]`` and raised a bare
            # ``IndexError`` out of the provider.  An empty answer is an
            # answer.
            return LLMResponse(content="", finish_reason="stop")
        choice = choices[0]
        msg = choice.message
        reasoning = getattr(msg, "reasoning_content", None)
        if not reasoning:
            reasoning = getattr(choice, "reasoning_content", None)
        tool_calls = []
        seen_ids: set[str] = set()
        for index, tc in enumerate(getattr(msg, "tool_calls", None) or ()):
            function = getattr(tc, "function", None)
            name = getattr(function, "name", "") if function else ""
            if is_nameless_tool_name(name):
                # M8-T334, home in ``minicc/llm/base.py`` since M8-T335: a
                # **nameless** call is dropped by every wire reader via
                # ``is_nameless_tool_name``.  The two paths used to disagree:
                # this one kept it, the loop dispatched a call for the
                # tool "" and the model spent a round on "[TOOL_ERROR]
                # 未知工具 ''".
                continue
            tool_calls.append(
                tool_call(
                    _unique_tool_call_id(str(getattr(tc, "id", None) or ""), f"call-{index}", seen_ids),
                    name,
                    getattr(function, "arguments", "{}") if function else "{}",
                )
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
                # M1-T7: the envelope turn's JSON action must survive the
                # replay — previously this collapsed to empty content.
                actions = [_render_envelope_action(call) for call in msg.get("tool_calls") or []]
                prior = str(msg.get("content") or "").strip()
                body = "\n".join([prior, *actions]) if prior else "\n".join(actions)
                wire.append({"role": "assistant", "content": body})
                continue
            wire.append(dict(msg))
        flush_results()
        return wire
