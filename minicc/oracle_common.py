"""Shared plumbing for the model-duty endpoints (workspace brief / diagnosis).

Everything the live wires need to talk to the configured gateway exactly once per
configurable budget, and honestly report when it cannot — in one place so the two
endpoints cannot drift from each other.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .llm.usage import measured_usage as _measured_usage
from .llm.usage import token_count
from .redis_cache import default_cache

_TTL_SECONDS = 600


def prompt_cache_key(base_url: str, model: str, explicit: str = "") -> str:
    """Same affinity-key discipline as the provider: explicit key wins,
    otherwise a salted hash of gateway+model — stable across processes."""
    explicit = (explicit or "").strip()[:64]
    if explicit:
        return explicit
    return f"minicc-{hashlib.sha256(f'{base_url}|{model}'.encode('utf-8')).hexdigest()[:16]}"


def parse_json_object(text: str) -> Any:
    """Tolerate a fenced block without pretending it was clean JSON."""
    text = (text or "").strip()
    if text.startswith("```"):
        inner = text.split("\n", 1)[-1]
        text = inner.rsplit("```", 1)[0].strip()
    try:
        return json.loads(text)
    except ValueError:
        return None


def measured_usage(usage_obj: Any) -> dict[str, Any]:
    """Token counts as the gateway surfaced them — absence stays absent.

    The shape itself lives in minicc/llm/usage.py; this only reads the gateway's
    wire object against that home (cached_tokens rides as a fourth key when the
    gateway actually reported it, never fabricated).
    """
    pt = token_count(getattr(usage_obj, "prompt_tokens", 0), 0) or 0
    ct = token_count(getattr(usage_obj, "completion_tokens", 0), 0) or 0
    tt = token_count(getattr(usage_obj, "total_tokens", None), None)
    record = _measured_usage(pt, ct, tt)
    details = getattr(usage_obj, "prompt_tokens_details", None)
    cached = getattr(details, "cached_tokens", None) if details is not None else None
    if cached is not None:
        record["cached_tokens"] = token_count(cached, 0) or 0
    return record


def call_model(*, config: Any, prompt: str, max_tokens: int = 280, temperature: float = 0.2) -> dict[str, Any]:
    """One model call against the configured gateway. Raises on transport failure."""
    from openai import OpenAI

    model_name = str(getattr(config, "model", "") or "")
    base_url = str(getattr(config, "base_url", "") or "")
    api_key = str(getattr(config, "api_key", "") or "")
    explicit_key = str(getattr(config, "prompt_cache_key", "") or "")
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=60, max_retries=0)
    response = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=temperature,
        prompt_cache_key=prompt_cache_key(base_url, model_name, explicit_key),
    )
    text = (response.choices[0].message.content or "").strip()
    usage = measured_usage(getattr(response, "usage", None))
    return {"text": text, "usage": usage, "model": model_name}


def error_payload(kind: str, exc: Exception, *, lists: bool = False) -> dict[str, Any]:
    return {
        "live": False,
        "zh": [] if lists else "",
        "en": [] if lists else "",
        "model": None,
        "usage": None,
        "error": f"{kind}: {type(exc).__name__}: {exc}",
    }


def memo_read(key: str):
    try:
        return default_cache.get(key)
    except Exception:  # noqa: BLE001 - a cache read failure falls through to a fresh brief
        return None


def memo_write(key: str, payload: dict[str, Any]) -> None:
    try:
        default_cache.set(key, payload, ttl=_TTL_SECONDS)
    except Exception:  # noqa: BLE001 - memo write failure never breaks the answer
        pass


def cached_zh_en(text: str) -> dict[str, str]:
    """Parse the zh/en contract; on failure ship the raw text as both sides."""
    parsed = parse_json_object(text)
    if not isinstance(parsed, dict):
        return {"zh": text, "en": text} if text else {"zh": "", "en": ""}
    zh = str(parsed.get("zh") or "").strip()
    en = str(parsed.get("en") or "").strip()
    return {"zh": zh or text, "en": en or zh or text}
