"""M8-T776 — ``minicc/redis_cache.py``: distributed cache with in-memory fallback.

The cache has two back ends — Redis (shared across processes) and an
in-process LRU (always available).  Every method swallows backend errors
and degrades to the local fallback, so a Redis outage is invisible.

These tests run against the local fallback (no Redis server required) and
assert the shared API shape: get/set/delete/clear/get_set, TTL expiry,
namespace isolation, and the LRU cap.
"""

from __future__ import annotations

import time

import pytest

from minicc.redis_cache import RedisCache, default_cache, _LOCAL, _LOCAL_CAP


def test_get_set_round_trip():
    c = RedisCache(namespace="roundtrip")
    assert c.get("missing") is None
    c.set("k", {"a": 1, "b": [2, 3]})
    assert c.get("k") == {"a": 1, "b": [2, 3]}


def test_ttl_expires():
    c = RedisCache(namespace="ttl", ttl=0.05)
    c.set("k", "v")
    assert c.get("k") == "v"
    time.sleep(0.1)
    assert c.get("k") is None


def test_set_ttl_overrides_default():
    c = RedisCache(namespace="override", ttl=0.05)
    c.set("short", "bye", ttl=0.05)
    c.set("long", "hello", ttl=10)
    time.sleep(0.1)
    assert c.get("short") is None
    assert c.get("long") == "hello"


def test_delete_removes_key():
    c = RedisCache(namespace="delete")
    c.set("k", "v")
    assert c.get("k") == "v"
    c.delete("k")
    assert c.get("k") is None


def test_clear_removes_namespace_keys():
    c = RedisCache(namespace="cleartest")
    c.set("a", "1")
    c.set("b", "2")
    other = RedisCache(namespace="other")
    other.set("x", "9")
    c.clear()
    assert c.get("a") is None
    assert c.get("b") is None
    assert other.get("x") == "9"


def test_get_set_fetch_or_compute():
    c = RedisCache(namespace="getset")
    assert c.get_set("k", "computed") == "computed"
    assert c.get("k") == "computed"
    assert c.get_set("k", "overwritten") == "computed"


def test_default_cache_is_shared():
    assert default_cache.namespace == "default"
    default_cache.set("dc_key", "dc_val")
    assert default_cache.get("dc_key") == "dc_val"
    default_cache.delete("dc_key")


def test_local_lru_respects_cap():
    # Directly exercise the local fallback path with many keys.
    c = RedisCache(namespace="captest")
    for i in range(_LOCAL_CAP + 50):
        c.set(f"k{i}", i)
    # The first keys should have been evicted.
    assert c.get("k0") is None
    assert c.get(f"k{_LOCAL_CAP + 49}") == _LOCAL_CAP + 49


def test_local_cache_is_thread_safe():
    c = RedisCache(namespace="threads")
    errors: list[Exception] = []

    def worker(start: int) -> None:
        try:
            for i in range(start, start + 200):
                c.set(f"t{i}", i)
            for i in range(start, start + 200):
                assert c.get(f"t{i}") == i
        except Exception as exc:  # pragma: no cover - defensive
            errors.append(exc)

    import threading

    ts = [threading.Thread(target=worker, args=(i * 200,)) for i in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert not errors


def test_never_raises_on_backend_error(monkeypatch):
    """A Redis client that raises on every op must not propagate."""
    import minicc.redis_cache as rc

    class Boom:
        def get(self, key):
            raise RuntimeError("redis down")

        def setex(self, key, ttl, val):
            raise RuntimeError("redis down")

        def set(self, key, val):
            raise RuntimeError("redis down")

        def delete(self, key):
            raise RuntimeError("redis down")

        def scan_iter(self, match):
            raise RuntimeError("redis down")

    c = RedisCache(namespace="boom")
    monkeypatch.setattr(c, "_redis", lambda: Boom())
    # All of these must return gracefully (local fallback path).
    assert c.get("anything") is None
    c.set("k", "v")
    assert c.get("k") == "v"
    c.delete("k")
    assert c.get("k") is None
    c.clear()
