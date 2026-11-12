"""M8-T804: minicc/redis_cache.py - Redis cache with local fallback tests.

Tests for:
- _now: current time function
- _json_safe / _json_unsafe: JSON serialization safety
- RedisCache: local fallback get/set/delete/clear
- default_cache: module-level cache instance
- Key prefix and TTL handling
"""

from __future__ import annotations

import time

import pytest

from minicc.redis_cache import (
    _LOCAL_CAP,
    _now,
    _json_safe,
    _json_unsafe,
    default_cache,
)


# ============================================================================
# _now
# ============================================================================

def test_now_returns_float() -> None:
    result = _now()
    assert isinstance(result, float)
    assert result > 0


def test_now_monotonic() -> None:
    t1 = _now()
    time.sleep(0.001)
    t2 = _now()
    assert t2 >= t1


# ============================================================================
# _json_safe and _json_unsafe
# ============================================================================

def test_json_safe_roundtrip() -> None:
    original = {"key": "value", "number": 42, "list": [1, 2, 3]}
    safe = _json_safe(original)
    assert isinstance(safe, dict)
    assert safe == original


def test_json_safe_bytes_wrapped() -> None:
    import base64
    safe = _json_safe(b"hello")
    assert isinstance(safe, dict)
    assert "__minicc_bytes__" in safe
    assert safe["__minicc_bytes__"] == base64.b64encode(b"hello").decode("ascii")


def test_json_safe_none() -> None:
    safe = _json_safe(None)
    assert safe is None


def test_json_unsafe_roundtrip() -> None:
    original = {"key": "value"}
    unsafe = _json_unsafe(original)
    assert unsafe == original


def test_json_unsafe_bytes_restored() -> None:
    import base64
    marker = {"__minicc_bytes__": base64.b64encode(b"hello").decode("ascii")}
    unsafe = _json_unsafe(marker)
    assert unsafe == b"hello"


def test_json_unsafe_passthrough() -> None:
    result = _json_unsafe("not json")
    assert result == "not json"


# ============================================================================
# default_cache
# ============================================================================

def test_default_cache_exists() -> None:
    assert default_cache is not None


def test_default_cache_get_missing() -> None:
    result = default_cache.get("nonexistent-key-xyz")
    assert result is None


def test_default_cache_set_and_get() -> None:
    default_cache.set("test-key-abc", {"value": 42}, ttl=60)
    result = default_cache.get("test-key-abc")
    assert result == {"value": 42}


def test_default_cache_delete() -> None:
    default_cache.set("test-key-del", "value", ttl=60)
    assert default_cache.get("test-key-del") == "value"
    default_cache.delete("test-key-del")
    assert default_cache.get("test-key-del") is None


def test_default_cache_contains() -> None:
    assert "nonexistent-key-xyz" not in default_cache
    default_cache.set("test-key-contains", "value", ttl=60)
    assert "test-key-contains" in default_cache


def test_default_cache_clear() -> None:
    default_cache.set("test-key-clear1", "value1", ttl=60)
    default_cache.set("test-key-clear2", "value2", ttl=60)
    default_cache.clear()
    assert default_cache.get("test-key-clear1") is None
    assert default_cache.get("test-key-clear2") is None


# ============================================================================
# Local cap
# ============================================================================

def test_local_cap() -> None:
    assert isinstance(_LOCAL_CAP, int)
    assert _LOCAL_CAP > 0


# ============================================================================
# Key prefix and TTL
# ============================================================================

def test_redis_url() -> None:
    from minicc.redis_cache import _REDIS_URL
    assert isinstance(_REDIS_URL, str)


def test_redis_key_prefix() -> None:
    from minicc.redis_cache import _REDIS_KEY_PREFIX
    assert isinstance(_REDIS_KEY_PREFIX, str)
    assert len(_REDIS_KEY_PREFIX) > 0
