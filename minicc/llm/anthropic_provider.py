"""Anthropic native Messages API provider.

Same duck-typed interface as ``OpenAICompatibleProvider`` (``await
chat(messages=..., tools=..., on_delta=...)`` -> ``LLMResponse``), so the agent
loop can use either without changes. Messages arrive in OpenAI wire format and
are converted to/from Anthropic content blocks:

- system messages -> ``system`` parameter (with a cache_control breakpoint);
- assistant ``tool_calls`` -> ``tool_use`` blocks, tool results -> ``tool_result``;
- OpenAI function schemas -> Anthropic ``tools`` input_schema (last tool gets a
  cache_control breakpoint);
- multimodal ``image_url`` data URLs -> Anthropic base64 image blocks.

Prompt caching is proactive: the system prompt and tool set are marked
``ephemeral`` so long agent sessions hit the cache. Usage counters are
normalized to the shared usage vocabulary (cache_read -> prompt_cache_hit_tokens,
cache_creation -> prompt_cache_write_tokens).

Streaming is not implemented yet: ``on_delta`` is accepted and ignored (same
contract as the non-streaming Responses mode of the OpenAI provider).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

try:  # httpx ships with the OpenAI SDK dependency; keep the import guarded.
    import httpx
except ModuleNotFoundError:  # pragma: no cover - depends on the HTTP stack.
    httpx = None  # type: ignore[assignment]

from .base import LLMResponse

ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_BASE_URL = "https://api.anthropic.com"
MAX_RETRIES_DEFAULT = 3
_RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504, 529}


class AnthropicProviderError(RuntimeError):
    """Anthropic API transport or protocol failure."""


def _endpoint(base_url: str) -> str:
    root = (base_url or DEFAULT_BASE_URL).rstrip("/")
    if root.endswith("/v1"):
        return f"{root}/messages"
    return f"{root}/v1/messages"


def _split_data_url(url: str) -> dict[str, str] | None:
    prefix = "data:"
    if not url.startswith(prefix):
        return None
    header, _, payload = url[len(prefix):].partition(",")
    media_type, _, is_base64 = header.partition(";")
    if not is_base64:
        return None
    return {"type": "base64", "media_type": media_type or "image/png", "data": payload}


def convert_user_content(content: Any) -> Any:
    """Convert one OpenAI user content (str or block list) to Anthropic form."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content)
    blocks: list[dict[str, Any]] = []
    for item in content:
        if not isinstance(item, dict):
            blocks.append({"type": "text", "text": str(item)})
            continue
        kind = item.get("type")
        if kind == "text":
            blocks.append({"type": "text", "text": str(item.get("text") or "")})
        elif kind == "image_url":
            source = _split_data_url(str((item.get("image_url") or {}).get("url") or ""))
            if source is not None:
                blocks.append({"type": "image", "source": source})
        else:  # unknown block: degrade to text instead of failing the run
            blocks.append({"type": "text", "text": json.dumps(item, ensure_ascii=False)})
    return blocks or ""


def messages_to_anthropic(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Split OpenAI wire messages into (system, anthropic_messages)."""
    system_parts: list[str] = []
    converted: list[dict[str, Any]] = []
    pending_results: list[dict[str, Any]] = []

    def flush_results() -> None:
        nonlocal pending_results
        if pending_results:
            converted.append({"role": "user", "content": pending_results})
            pending_results = []

    for message in messages:
        role = message.get("role")
        if role == "system":
            text = message.get("content")
            if isinstance(text, list):
                text = "\n".join(str(part.get("text") or "") for part in text if isinstance(part, dict))
            if str(text or "").strip():
                system_parts.append(str(text))
        elif role == "user":
            flush_results()
            converted.append({"role": "user", "content": convert_user_content(message.get("content"))})
        elif role == "assistant":
            flush_results()
            blocks: list[dict[str, Any]] = []
            text = message.get("content")
            if isinstance(text, str) and text.strip():
                blocks.append({"type": "text", "text": text})
            for call in message.get("tool_calls") or []:
                function = call.get("function") or {}
                raw_arguments = function.get("arguments") or "{}"
                try:
                    tool_input = json.loads(raw_arguments) if isinstance(raw_arguments, str) else dict(raw_arguments)
                except json.JSONDecodeError:
                    tool_input = {"_raw": str(raw_arguments)}
                blocks.append({
                    "type": "tool_use",
                    "id": str(call.get("id") or ""),
                    "name": str(function.get("name") or ""),
                    "input": tool_input,
                })
            if blocks:
                converted.append({"role": "assistant", "content": blocks})
        elif role == "tool":
            content = message.get("content")
            if isinstance(content, str):
                result_content: Any = content
            else:
                result_content = json.dumps(content, ensure_ascii=False, default=str)
            pending_results.append({
                "type": "tool_result",
                "tool_use_id": str(message.get("tool_call_id") or ""),
                "content": result_content,
            })
    flush_results()
    return "\n\n".join(system_parts), converted


def tools_to_anthropic(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Convert OpenAI function schemas and mark the tail for prompt caching."""
    converted: list[dict[str, Any]] = []
    for tool in tools or []:
        function = tool.get("function") or {}
        converted.append({
            "name": str(function.get("name") or ""),
            "description": str(function.get("description") or ""),
            "input_schema": function.get("parameters") or {"type": "object", "properties": {}},
        })
    if converted:
        converted[-1]["cache_control"] = {"type": "ephemeral"}
    return converted


def response_to_llm(payload: dict[str, Any], model: str) -> LLMResponse:
    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    for block in payload.get("content") or []:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            text_parts.append(str(block.get("text") or ""))
        elif block.get("type") == "tool_use":
            tool_calls.append({
                "id": str(block.get("id") or ""),
                "type": "function",
                "function": {
                    "name": str(block.get("name") or ""),
                    "arguments": json.dumps(block.get("input") or {}, ensure_ascii=False),
                },
            })
    usage = payload.get("usage") or {}
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    cache_read = usage.get("cache_read_input_tokens")
    cache_write = usage.get("cache_creation_input_tokens")
    normalized: dict[str, Any] = {
        "prompt_tokens": input_tokens,
        "completion_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
    }
    if cache_read is not None:
        normalized["prompt_cache_hit_tokens"] = int(cache_read)
    if cache_write is not None:
        normalized["prompt_cache_write_tokens"] = int(cache_write)
    stop_reason = str(payload.get("stop_reason") or "end_turn")
    return LLMResponse(
        content="\n".join(part for part in text_parts if part) or None,
        tool_calls=tool_calls,
        usage=normalized,
        finish_reason="tool_calls" if stop_reason == "tool_use" else "stop",
        model=str(payload.get("model") or model),
    )


class AnthropicProvider:
    """Native Anthropic Messages client with proactive prompt caching."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 180.0,
        max_retries: int = MAX_RETRIES_DEFAULT,
        on_status: Any | None = None,
        transport: Any | None = None,
    ) -> None:
        if httpx is None:  # pragma: no cover - depends on the HTTP stack
            raise AnthropicProviderError("httpx 不可用，无法使用 Anthropic provider")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url or DEFAULT_BASE_URL
        self.timeout = float(timeout)
        self.max_retries = max(0, int(max_retries))
        self.on_status = on_status
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout, connect=15.0),
            transport=transport,
            headers={
                "x-api-key": api_key,
                "anthropic-version": ANTHROPIC_VERSION,
                "Content-Type": "application/json",
            },
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        on_delta: Any | None = None,
    ) -> LLMResponse:
        system, converted = messages_to_anthropic(messages)
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 8192,
            "messages": converted,
        }
        if system:
            # Prompt caching: one breakpoint on the (stable) system prompt.
            payload["system"] = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
        anthropic_tools = tools_to_anthropic(tools)
        if anthropic_tools:
            payload["tools"] = anthropic_tools
        attempt = 0
        while True:
            attempt += 1
            try:
                response = await self._client.post(_endpoint(self.base_url), json=payload)
            except httpx.HTTPError as exc:
                if attempt > self.max_retries:
                    raise AnthropicProviderError(f"Anthropic 请求失败: {exc}") from exc
                await _backoff(attempt)
                continue
            if response.status_code in _RETRYABLE_STATUS and attempt <= self.max_retries:
                retry_after = response.headers.get("retry-after")
                await _backoff(attempt, retry_after)
                continue
            if response.status_code >= 400:
                detail = response.text[:500]
                raise AnthropicProviderError(f"Anthropic HTTP {response.status_code}: {detail}")
            return response_to_llm(response.json(), self.model)


async def _backoff(attempt: int, retry_after: str | None = None) -> None:
    if retry_after:
        try:
            await asyncio.sleep(max(0.0, float(retry_after)))
            return
        except ValueError:
            pass
    await asyncio.sleep(min(60.0, 2.0 ** (attempt - 1)))


__all__ = [
    "AnthropicProvider",
    "AnthropicProviderError",
    "messages_to_anthropic",
    "response_to_llm",
    "tools_to_anthropic",
]
