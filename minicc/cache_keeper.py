"""M8-T1003: 前缀缓存守护 —— 把共享系统提示词在上游缓存里永远续命。

Measured on this gateway (wkapi.pro / gpt-6-sol, 2026-11-15):

* turns after turn 1 hit ~7,400 of ~7,500 shared-prefix tokens — the warm path works;
* a >5-minute gap between turns drops the upstream prefix cache cold — the
  next turn re-pays the whole prefix (one task showed a 60k-token full miss
  after a long tool run); compaction nukes it entirely;
* the system prompt is byte-stable per workspace, so one tiny request every
  few minutes re-warms the exact prefix the agent depends on.

The gateway gates raw clients (urllib/httpx) behind a browser fingerprint it
only answers OpenAI's SDK to, so the keeper calls the same route the agent
itself uses: the official ``AsyncOpenAI.responses.create`` with the same
``prompt_cache_key`` derivation.  Costs: one decision per warm is ~20 output
tokens (the input rides the warm cache), zero tool calls, zero memory of the
agent's context.  Failures are counted, never raised into the agent; every
warm is reported on ``/api/provider-ping``.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import threading
import time
from typing import Any

LOG = logging.getLogger(__name__)

# 60 s: measured 2026-11-18 on this gateway (aizzz.xyz / new key / terra): a
# byte-identical warm prefix is evicted in under 150 s of silence, so the old
# 220 s cadence could never keep the lane warm. 60 s sits comfortably under
# that measured eviction window; a warm costs ~20 output tokens.
_DEFAULT_INTERVAL = 60.0
_MIN_INTERVAL = 60.0
_MAX_INTERVAL = 900.0


def _interval() -> float:
    raw = (os.environ.get("MINICC_CACHE_KEEPER_INTERVAL") or "").strip()
    try:
        value = float(raw)
    except ValueError:
        return _DEFAULT_INTERVAL
    return min(_MAX_INTERVAL, max(_MIN_INTERVAL, value))


def enabled() -> bool:
    raw = (os.environ.get("MINICC_CACHE_KEEPER") or "1").strip().lower()
    return raw not in {"0", "off", "false", "no"}


def _derive_cache_key(base_url: str, model: str) -> str:
    digest = hashlib.sha256(f"{base_url}|{model}".encode("utf-8")).hexdigest()[:16]
    return f"minicc-{digest}"


def derive_family_cache_key(base_url: str, model: str, session_id: str) -> str:
    """Affinity key for a conversation family (codex thread-affinity shape).

    Precedence mirrors the provider's: an explicit MINICC_PROMPT_CACHE_KEY
    wins; a supplied ``session_id`` scopes the family; otherwise the legacy
    lane-derived key is returned unchanged so keeper status replies keep the
    same shape they always had.
    """
    explicit = (os.environ.get("MINICC_PROMPT_CACHE_KEY") or "").strip()
    if explicit:
        return explicit[:64]
    sid = (session_id or "").strip()
    if sid:
        digest = hashlib.sha256(sid.encode("utf-8")).hexdigest()[:16]
        return f"minicc-{digest}"
    return _derive_cache_key(base_url, model)


def anthropic_wire(provider_type: str) -> bool:
    return (provider_type or "").strip().lower() == "anthropic"


_STATE_GUARD = threading.Lock()
_STATE: dict[str, Any] = {
    "enabled": None,
    "interval_seconds": None,
    "started_at": None,
    "warms": 0,
    "failures": 0,
    "last_warm_at": None,
    "last_ok": None,
    "last_error": None,
    "last_prompt_tokens": None,
    "last_cached_tokens": None,
    "last_elapsed_ms": None,
}


def keeper_status() -> dict[str, Any]:
    with _STATE_GUARD:
        return dict(_STATE)


def _note_ok(elapsed: float, prompt_tokens: int, cached_tokens: int) -> None:
    with _STATE_GUARD:
        _STATE["warms"] += 1
        _STATE["last_warm_at"] = round(time.time(), 3)
        _STATE["last_ok"] = True
        _STATE["last_error"] = None
        _STATE["last_prompt_tokens"] = prompt_tokens
        _STATE["last_cached_tokens"] = cached_tokens
        _STATE["last_elapsed_ms"] = round(elapsed * 1000, 1)


def _note_fail(exc: BaseException) -> None:
    with _STATE_GUARD:
        _STATE["failures"] += 1
        _STATE["last_warm_at"] = round(time.time(), 3)
        _STATE["last_ok"] = False
        _STATE["last_error"] = type(exc).__name__


async def _call_gateway(
    *,
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    cache_key: str,
) -> dict[str, Any]:
    """One warm decision; isolated into its own async callable so tests stub it.

    The intended call is the shared system prefix + a “在” stub: a one-token
    user message, irrelevant to affinity, which keys on the shared prefix only.

    The wire shape this gateway accepts moved mid-flight (2026-11-18: the
    Responses endpoint downgraded to stream-required, and different account groups
    answer differently), so the call tries, in order:

    1. chat/completions with ``stream=True`` (this lane's stable, cache-friendly path,
       verified live: 91-100% of the shared prefix hits on the second call);
    2. chat/completions non-streaming (a fallback under the same wire);
    3. Responses streaming (last resort for lanes that only speak Responses).

    Every attempt parses whichever usage shape the answer carries:
    ``prompt_tokens_details`` (chat/completions) or ``input_tokens_details``
    (Responses).  The first attempt that answers is the verdict; a fully
    rejected sequence raises and is counted by ``_note_fail`` as usual.
    """
    from openai import AsyncOpenAI

    client = AsyncOpenAI(base_url=base_url.rstrip("/"), api_key=api_key, timeout=60, max_retries=0)
    try:
        warm = {
            "role": "user",
            "content": "在",
        }
        system = {"role": "system", "content": system_prompt}

        # -- attempt 1: chat/completions, streaming, include usage --------------
        try:
            stream = await client.chat.completions.create(
                model=model,
                messages=[system, warm],
                max_tokens=4,
                temperature=0,
                prompt_cache_key=cache_key,
                stream=True,
                stream_options={"include_usage": True},
            )
            usage = None
            async for chunk in stream:
                if getattr(chunk, "usage", None) is not None:
                    usage = chunk.usage
            details = getattr(usage, "prompt_tokens_details", None) if usage else None
            return {
                "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
                "cached_tokens": int(getattr(details, "cached_tokens", 0) or 0),
            }
        except Exception:  # noqa: BLE001 - attempt 2 exists so attempt 1 may fail without a verdict on warm fate
            pass

        # -- attempt 2: chat/completions, non-streaming ------------------------
        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=[system, warm],
                max_tokens=4,
                temperature=0,
                prompt_cache_key=cache_key,
            )
            usage = getattr(resp, "usage", None)
            details = getattr(usage, "prompt_tokens_details", None) if usage else None
            return {
                "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
                "cached_tokens": int(getattr(details, "cached_tokens", 0) or 0),
            }
        except Exception:  # noqa: BLE001 - attempt 3 exists so attempt 2 may fail without a verdict on warm fate
            pass

        # -- attempt 3: Responses streaming ------------------------------------
        stream = await client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "在"},
            ],
            store=False,
            stream=True,
            prompt_cache_key=cache_key,
        )
        usage = None
        async for event in stream:
            if getattr(event, "type", None) == "response.completed":
                response = getattr(event, "response", None)
                usage = getattr(response, "usage", None) if response else None
        details = getattr(usage, "input_tokens_details", None) if usage else None
        return {
            "prompt_tokens": int(getattr(usage, "input_tokens", 0) or 0),
            "cached_tokens": int(getattr(details, "cached_tokens", 0) or 0),
        }
    finally:
        try:
            await client.close()
        except Exception:  # noqa: BLE001 - closing a client must never crash the loop
            pass


class CacheKeeper:
    """A daemon thread that re-warms the upstream prefix cache forever."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str,
        system_prompt: str,
        interval: float | None = None,
        session_id: str | None = None,
    ) -> None:
        self._base = (base_url or "").rstrip("/")
        self._model = str(model or "")
        self._api_key = str(api_key or "")
        self._system = str(system_prompt or "")
        self._interval = max(_MIN_INTERVAL, float(interval if interval is not None else _interval()))
        self._session_id = str(session_id or "")
        self._cache_key = derive_family_cache_key(self._base, self._model, self._session_id)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._enabled = bool(enabled()) and bool(self._base) and bool(self._model) and bool(self._api_key) and bool(self._system)

    def start(self) -> None:
        with _STATE_GUARD:
            _STATE["enabled"] = self._enabled
            _STATE["interval_seconds"] = self._interval
            _STATE["started_at"] = round(time.time(), 3)
        if not self._enabled:
            LOG.info("cache keeper disabled (MINICC_CACHE_KEEPER=0 or provider config incomplete)")
            return
        self._thread = threading.Thread(target=self._loop, name="minicc-cache-keeper", daemon=True)
        self._thread.start()
        LOG.info("cache keeper enabled: interval=%.0fs model=%s", self._interval, self._model)

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        self._warm_once()
        while not self._stop.wait(self._interval):
            self._warm_once()

    def _warm_once(self) -> None:
        started = time.perf_counter()
        try:
            result = asyncio.run(_call_gateway(
                base_url=self._base,
                api_key=self._api_key,
                model=self._model,
                system_prompt=self._system,
                cache_key=self._cache_key,
            ))
        except Exception as exc:  # noqa: BLE001 - warming must never crash the daemon
            _note_fail(exc)
            LOG.info("cache keeper warm failed (%s) — will retry", type(exc).__name__)
            return
        elapsed = time.perf_counter() - started
        _note_ok(elapsed, int(result.get("prompt_tokens", 0)), int(result.get("cached_tokens", 0)))
        LOG.info(
            "cache keeper warmed ok cached_tokens=%d prompt_tokens=%d elapsed_ms=%.0f",
            result.get("cached_tokens", 0), result.get("prompt_tokens", 0), elapsed * 1000,
        )
