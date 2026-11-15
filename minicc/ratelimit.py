"""Rate limiting for gateway-facing endpoints.

The Python plane answers its own callers directly; the wkapi.pro lane that
RAG reads moves real tokens. This limiter is a sliding-window token bucket
— the same shape Resilience4j uses for its counter rolling window — with
two backends:

- **Redis** when `MINICC_REDIS_URL` points at a live server (same client
  pool and failure model as `minicc.redis_cache`), so every process in
  the workbench agrees on one count (for a multi-replica service plane
  this is the only honest choice).
- an in-process LRU window otherwise — honest, zero-config, good enough
  for a single-replica local-first workbench.

It never raises. When the limiter can't decide (Redis died mid-window,
import missing), the request is allowed and the failure is recorded —
failing open is the point of the fallback; failing closed would let a
network blip take the product down.
"""

from __future__ import annotations

import os
import threading
import time
from collections import OrderedDict
from typing import Any

_WINDOW_SECONDS = float(os.environ.get("MINICC_RATE_LIMIT_WINDOW", "60"))
_MAX_CALLS = int(os.environ.get("MINICC_RATE_LIMIT_PER_MINUTE", "20"))
_NAMESPACE = "minicc:rl:"

#: When the fallback path is exercised the whole process shares these
#: two structures; a dying Redis can transiently mint more windows until
#: the shared-client layer notices. Bounded for the same reason as
#: redis_cache: never let this dict grow by eviction discipline.
_LOCAL: OrderedDict[str, tuple[float, float]] = OrderedDict()
_LOCAL_LOCK = threading.RLock()
_LOCAL_CAP = 4096

#: Operator-honesty counters; read-only, never mutate from the hot path.
_DECISIONS: dict[str, int] = {"allowed_local": 0, "allowed_redis": 0, "denied": 0, "degraded_open": 0}
_DECISIONS_LOCK = threading.Lock()


def _bucket_key(route: str, client_key: str) -> str:
    return f"{_NAMESPACE}{route}:{client_key}"


def _local_hit(key: str) -> bool:
    now = time.monotonic()
    with _LOCAL_LOCK:
        bucket = _LOCAL.get(key)
        if bucket is None or bucket[1] < now:
            _LOCAL[key] = (1.0, now + _WINDOW_SECONDS)
            while len(_LOCAL) > _LOCAL_CAP:
                _LOCAL.popitem(last=False)
            return True
        count, expires = bucket
        if count >= _MAX_CALLS:
            _LOCAL[key] = (count, expires)
            return False
        _LOCAL[key] = (count + 1.0, expires)
        return True


def _shared_client() -> Any:
    try:
        from .redis_cache import _shared_client as _client

        return _client()
    except Exception:  # noqa: BLE001 - importing redis_cache must not break the limiter
        return None


def _redis_hit(client: Any, key: str) -> bool | None:
    try:
        count = client.incr(key)
        if int(count) == 1:
            client.pexpire(key, int(_WINDOW_SECONDS * 1000))
        return int(count) <= _MAX_CALLS
    except Exception:  # noqa: BLE001 - Redis failed mid-window; treat as undecided
        return None


def consume(route: str, client_key: str) -> tuple[bool, dict[str, Any]]:
    """Return (allowed, meta). `meta` names which backend decided and why."""
    key = _bucket_key(route, client_key)
    client = _shared_client()
    if client is not None:
        verdict = _redis_hit(client, key)
        if verdict is not None:
            with _DECISIONS_LOCK:
                _DECISIONS["allowed_redis" if verdict else "denied"] += 1
            return bool(verdict), {"backend": "redis", "window_seconds": _WINDOW_SECONDS, "limit": _MAX_CALLS}
        with _DECISIONS_LOCK:
            _DECISIONS["degraded_open"] += 1
        # Redis failed mid-window; fail open, stay honest, switch local so the
        # next call gets a deterministic answer instead of a coin flip.
    local = _local_hit(key)
    with _DECISIONS_LOCK:
        _DECISIONS["allowed_local" if local else "denied"] += 1
    return local, {"backend": "local", "window_seconds": _WINDOW_SECONDS, "limit": _MAX_CALLS}


def stats() -> dict[str, Any]:
    with _DECISIONS_LOCK:
        decisions = dict(_DECISIONS)
    return {
        "limit": _MAX_CALLS,
        "window_seconds": _WINDOW_SECONDS,
        "remaining_local_windows": len(_LOCAL),
        "decisions": decisions,
    }
