"""Redis-backed distributed cache with an in-memory fallback.

Minicc runs as a single local process in the common case, but the web
surface and the verification loop can each spawn short-lived worker
processes.  An in-process ``OrderedDict`` cache cannot be shared across
them, so each worker recomputes gzip payloads and file digests that a
sibling already paid for.

This module offers one cache shape with two back ends:

* Redis (when a server is reachable at ``REDIS_URL``) — values are shared
  across every process that talks to the same instance, so a gzip payload
  or SHA-256 digest computed once is reused everywhere.
* An in-process ``OrderedDict`` LRU — always available, zero external
  dependency, used when Redis cannot be reached or the ``redis`` package
  is not installed.

Every public method swallows backend errors and degrades to the local
fallback: a Redis outage slows nothing down, it only loses cross-process
sharing.  The module never raises, so callers never need to wrap it.

Configuration is purely environmental — no pyproject change is required
to *use* the module; declaring ``redis`` in optional-dependencies merely
makes ``pip install -e ".[dev]`` pull the driver.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import OrderedDict
from typing import Any

_REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
_REDIS_KEY_PREFIX = os.environ.get("MINICC_REDIS_PREFIX", "minicc:")
_REDIS_TTL = float(os.environ.get("MINICC_REDIS_TTL_SECONDS", "3600"))
_LOCAL_CAP = int(os.environ.get("MINICC_REDIS_LOCAL_CAP", "4096"))


def _now() -> float:
    return time.monotonic()


# ---------------------------------------------------------------------------
# Backend selection: try importing redis; if absent or unreachable, local only.
# ---------------------------------------------------------------------------

_HAS_REDIS = False
try:  # pragma: no cover - import guard
    import redis as _redis  # type: ignore[import-not-found]

    _HAS_REDIS = True
except Exception:  # redis not installed
    _redis = None  # type: ignore[assignment]


def _redis_client() -> Any:
    """Best-effort Redis client; None when it cannot be reached or imported."""
    if not _HAS_REDIS or _redis is None:  # type: ignore[truthy-bool]
        return None
    try:
        client = _redis.Redis.from_url(_REDIS_URL, socket_connect_timeout=0.25, socket_timeout=0.25)
        client.ping()
        return client
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Local LRU fallback — identical shape to Redis so callers see one API.
# ---------------------------------------------------------------------------

_LOCAL: OrderedDict[str, tuple[Any, float | None]] = OrderedDict()
_LOCAL_LOCK = threading.RLock()


def _local_get(key: str) -> Any | None:
    with _LOCAL_LOCK:
        entry = _LOCAL.get(key)
        if entry is None:
            return None
        value, expiry = entry
        if expiry is not None and _now() > expiry:
            _LOCAL.pop(key, None)
            return None
        _LOCAL.move_to_end(key)
        return value


def _local_set(key: str, value: Any, ttl: float | None) -> None:
    expiry = None if ttl is None else _now() + ttl
    with _LOCAL_LOCK:
        if key in _LOCAL:
            _LOCAL.move_to_end(key)
        _LOCAL[key] = (value, expiry)
        while len(_LOCAL) > _LOCAL_CAP:
            _LOCAL.popitem(last=False)


def _local_delete(key: str) -> None:
    with _LOCAL_LOCK:
        _LOCAL.pop(key, None)


# ---------------------------------------------------------------------------
# Public cache — one home for get/set/delete/clear, Redis-first with local
# fallback on every call so a transient Redis hiccup is invisible.
# ---------------------------------------------------------------------------


class RedisCache:
    """Distributed cache: Redis when available, in-process LRU otherwise.

    Every method is safe to call on a cold instance; construction never
    connects.  The first operation lazily probes Redis and caches the
    client object, so later calls skip the handshake.
    """

    def __init__(self, namespace: str = "default", ttl: float | None = None) -> None:
        self.namespace = namespace
        self.ttl = ttl
        self._client: Any = None
        self._client_probed = False

    def _redis(self) -> Any:
        if not self._client_probed:
            self._client_probed = True
            self._client = _redis_client()
        return self._client

    def _key(self, key: str) -> str:
        return f"{_REDIS_KEY_PREFIX}{self.namespace}:{key}"

    def get(self, key: str) -> Any | None:
        """Return the cached value, or None when absent/expired."""
        client = self._redis()
        if client is not None:
            try:
                raw = client.get(self._key(key))
                if raw is not None:
                    return json.loads(raw.decode("utf-8"))
            except Exception:
                pass
        return _local_get(self._key(key))

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        """Store ``value`` under ``key`` with an optional TTL in seconds."""
        effective_ttl = self.ttl if ttl is None else ttl
        client = self._redis()
        if client is not None:
            try:
                payload = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                if effective_ttl is not None:
                    client.setex(self._key(key), int(effective_ttl), payload)
                else:
                    client.set(self._key(key), payload)
                return
            except Exception:
                pass
        _local_set(self._key(key), value, effective_ttl)

    def delete(self, key: str) -> None:
        client = self._redis()
        if client is not None:
            try:
                client.delete(self._key(key))
                return
            except Exception:
                pass
        _local_delete(self._key(key))

    def clear(self) -> None:
        client = self._redis()
        if client is not None:
            try:
                for k in client.scan_iter(f"{_REDIS_KEY_PREFIX}{self.namespace}:*"):
                    client.delete(k)
                return
            except Exception:
                pass
        with _LOCAL_LOCK:
            for k in list(_LOCAL):
                if k.startswith(f"{_REDIS_KEY_PREFIX}{self.namespace}:"):
                    _LOCAL.pop(k, None)

    def get_set(self, key: str, default: Any, ttl: float | None = None) -> Any:
        """Fetch-or-compute: return cached value or store ``default``."""
        cached = self.get(key)
        if cached is not None:
            return cached
        self.set(key, default, ttl)
        return default


#: Process-wide default cache.  Namespaces isolate unrelated concerns
#: (gzip payloads, file digests, search results) inside one Redis instance.
default_cache = RedisCache(namespace="default")
