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

Reads treat a *negative* answer from Redis as authoritative: when the shared
store says "absent", the local copy is not consulted, so a value deleted or
evicted in another process cannot be resurrected out of this process's stale
LRU.  The local copy answers only when the driver is unreachable.  Writes
report whether they reached the shared store, so a value that could not cross
the wire is visible as ``False`` instead of silently staying local.

Configuration is purely environmental — no pyproject change is required
to *use* the module; declaring ``redis`` in optional-dependencies merely
makes ``pip install -e ".[dev]`` pull the driver.
"""

from __future__ import annotations

import base64
import json
import os
import threading
import time
from collections import OrderedDict
from typing import Any

_REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
_REDIS_KEY_PREFIX = os.environ.get("MINICC_REDIS_PREFIX", "minicc:")
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
except Exception:  # noqa: BLE001 - redis not installed; local fallback handles it
    _redis = None  # type: ignore[assignment]


def _redis_client() -> Any:
    """Probe once and return a live Redis client; None when it cannot be reached.

    This is the only place a connection is attempted, so the timeout budget and
    the "is it up?" question each have exactly one home.
    """
    if not _HAS_REDIS or _redis is None:  # type: ignore[truthy-bool]
        return None
    try:
        client = _redis.Redis.from_url(_REDIS_URL, socket_connect_timeout=0.25, socket_timeout=0.25)
        client.ping()
        return client
    except Exception:  # noqa: BLE001 - Redis unreachable; local fallback handles it
        return None


# One client — and therefore one connection pool — per process.  Building a
# client per RedisCache instance multiplied pools by the number of namespaces
# (digest, default, …) and paid a fresh handshake for each.  A failed probe is
# remembered for a short window rather than forever, so a Redis that starts
# after the first request is picked up without restarting the agent.
_CLIENT_LOCK = threading.Lock()
_CLIENT: Any = None
_CLIENT_DEAD_UNTIL = 0.0
_CLIENT_RETRY_SECONDS = float(os.environ.get("MINICC_REDIS_RETRY_SECONDS", "15"))


def _shared_client() -> Any:
    """The process-wide client, or None while the retry window is open."""
    global _CLIENT, _CLIENT_DEAD_UNTIL
    now = _now()
    with _CLIENT_LOCK:
        if _CLIENT is not None:
            return _CLIENT
        if now < _CLIENT_DEAD_UNTIL:
            return None
        client = _redis_client()
        if client is None:
            _CLIENT_DEAD_UNTIL = now + _CLIENT_RETRY_SECONDS
            return None
        _CLIENT = client
        return client


def _reset_client_cache() -> None:
    """Forget the memoised client; the seam tests use to swap a backend."""
    global _CLIENT, _CLIENT_DEAD_UNTIL
    with _CLIENT_LOCK:
        _CLIENT = None
        _CLIENT_DEAD_UNTIL = 0.0


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
    """Distributed cache: Redis is the one truth, the local LRU is the degraded copy.

    Read semantics are the part that matters.  A *negative* answer from the
    shared store is authoritative: when Redis says "absent", the local copy is
    not consulted, so a value evicted (or deleted) in another process cannot be
    resurrected out of this process's stale LRU.  Only a transport failure -
    no client, or the driver raised - lets the local copy answer.

    Every method is safe to call on a cold instance; construction never
    connects.  Writes return whether the value actually reached the shared
    store, which turns "silently not shared" into an observable fact.
    """

    def __init__(self, namespace: str = "default", ttl: float | None = None) -> None:
        self.namespace = namespace
        self.ttl = ttl
        self._client: Any = None
        self._client_probed = False

    def _redis(self) -> Any:
        if not self._client_probed:
            self._client_probed = True
            self._client = _shared_client()
        return self._client

    def _key(self, key: Any) -> str:
        return f"{_REDIS_KEY_PREFIX}{self.namespace}:{key}"

    def _shared_get(self, key: str) -> tuple[bool, Any]:
        """Return ``(answered, value)``: did the shared store give a verdict?

        ``answered`` is True for both a hit and an authoritative miss.  It is
        False only when no backend is reachable, which is the single case where
        the local copy is allowed to speak.
        """
        client = self._redis()
        if client is None:
            return False, None
        try:
            raw = client.get(self._key(key))
        except Exception:  # noqa: BLE001 - transport failure; degrade to local
            return False, None
        if raw is None:
            return True, None
        try:
            return True, _decode(raw)
        except Exception:  # noqa: BLE001 - unreadable payload is a miss, never a crash
            return True, None

    def get(self, key: str) -> Any | None:
        """Return the cached value, or None when absent/expired."""
        answered, value = self._shared_get(key)
        if answered:
            return value
        return _local_get(self._key(key))

    def set(self, key: str, value: Any, ttl: float | None = None) -> bool:
        """Store ``value`` under ``key``; return True when it is shared.

        The local copy is written only when the value did not reach the shared
        store.  Mirroring every shared write would double the resident bytes of
        a payload cache (the asset cache holds compressed blobs) and would put a
        copy in this process that no other process can invalidate.
        """
        effective_ttl = self.ttl if ttl is None else ttl
        client = self._redis()
        if client is not None:
            payload: bytes | None = None
            try:
                payload = _encode(value)
            except Exception:  # noqa: BLE001 - value cannot cross the wire; local stands
                payload = None
            if payload is not None:
                try:
                    if effective_ttl is not None:
                        client.setex(self._key(key), int(effective_ttl), payload)
                    else:
                        client.set(self._key(key), payload)
                    return True
                except Exception:  # noqa: BLE001 - Redis write failed; local copy stands
                    pass
        _local_set(self._key(key), value, effective_ttl)
        return False

    def delete(self, key: str) -> bool:
        """Drop ``key`` from both backends; never leave a resurrectable copy."""
        _local_delete(self._key(key))
        client = self._redis()
        if client is None:
            return False
        try:
            client.delete(self._key(key))
            return True
        except Exception:  # noqa: BLE001 - Redis delete failed; local already gone
            return False

    def clear(self) -> bool:
        """Drop the whole namespace from both backends."""
        with _LOCAL_LOCK:
            for k in list(_LOCAL):
                if k.startswith(f"{_REDIS_KEY_PREFIX}{self.namespace}:"):
                    _LOCAL.pop(k, None)
        client = self._redis()
        if client is None:
            return False
        try:
            for k in client.scan_iter(f"{_REDIS_KEY_PREFIX}{self.namespace}:*"):
                client.delete(k)
            return True
        except Exception:  # noqa: BLE001 - Redis clear failed; local already gone
            return False

    def get_set(self, key: str, default: Any, ttl: float | None = None) -> Any:
        """Fetch-or-compute: return cached value or store ``default``."""
        cached = self.get(key)
        if cached is not None:
            return cached
        self.set(key, default, ttl)
        return default

    # --- dict-like access (for tests and callers that expect []
    #     semantics) ------------------------------------------------

    def __getitem__(self, key: str) -> Any:
        value = self.get(key)
        if value is None:
            raise KeyError(key)
        return value

    def __setitem__(self, key: str, value: Any) -> None:
        self.set(key, value)

    def __delitem__(self, key: str) -> None:
        self.delete(key)

    def __contains__(self, key: str) -> bool:
        return self.get(key) is not None


# --- JSON-safe value transformation (bytes → base64 marker dict) ---


def _json_safe(value: Any) -> Any:
    """Convert ``value`` to a JSON-serializable form, wrapping bytes."""
    if isinstance(value, bytes):
        return {"__minicc_bytes__": base64.b64encode(value).decode("ascii")}
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def _json_unsafe(value: Any) -> Any:
    """Reverse ``_json_safe``: restore bytes from marker dicts."""
    if (
        isinstance(value, dict)
        and len(value) == 1
        and "__minicc_bytes__" in value
    ):
        return base64.b64decode(value["__minicc_bytes__"])
    if isinstance(value, dict):
        return {k: _json_unsafe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_unsafe(v) for v in value]
    return value


# --- The one wire codec -----------------------------------------------------
#
# Both write paths (``set`` and ``[]=``) and both read paths (``get`` and
# ``[]``) go through these two functions.  Before this, ``set`` serialised with
# a bare ``json.dumps`` while ``__setitem__`` used ``_json_safe`` and ``get``
# decoded with a bare ``json.loads``: bytes written through one path came back
# as a marker dict through the other, and gzip payloads (the module's own
# stated use case) could not be written at all.


def _encode(value: Any) -> bytes:
    """Project ``value`` onto the wire form shared by every writer."""
    projected = _json_safe(value)
    return json.dumps(projected, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _decode(raw: bytes | str) -> Any:
    """Inverse of ``_encode``: restore bytes wrapped by ``_json_safe``.

    Accepts ``str`` as well: ``decode_responses=True`` clients hand back text,
    and treating that as an unreadable payload would turn every hit into a miss.
    """
    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    return _json_unsafe(json.loads(text))


#: Process-wide default cache.  Namespaces isolate unrelated concerns
#: (gzip payloads, file digests, search results) inside one Redis instance.
default_cache = RedisCache(namespace="default")
