"""M8-T832: the cache has one wire encoding and one source of truth.

Before this batch the Redis branch had never been executed by any test — the
``redis`` driver is not installed in the default environment, so every existing
test drove only the local fallback.  Five defects survived behind that blind
spot:

1. ``set`` serialised with a bare ``json.dumps``, so bytes (the module's own
   stated use case: gzip payloads) and tuples raised ``TypeError``, the Redis
   write was abandoned, and the value silently stayed in one process.
2. ``__setitem__`` wrote through ``_json_safe`` while ``get`` decoded with a
   bare ``json.loads``: bytes came back as a marker dict.
3. An authoritative miss from Redis fell through to the local copy, so another
   process's eviction could be undone by this process's stale LRU.
4. ``delete`` returned as soon as Redis succeeded and left the local copy, so a
   deleted value resurrected on the next read.
5. Four dunder methods sat unreachable after a ``return`` in ``_json_unsafe``.

Every test below drives the Redis branch through an in-memory stand-in for the
wire protocol, so the branch stays covered without the driver or a server.
"""

from __future__ import annotations

import ast
import gzip
from pathlib import Path

import pytest

from minicc import redis_cache as rc

REPO_ROOT = Path(__file__).resolve().parents[1]


class _Wire:
    """In-memory stand-in for the small Redis surface this module uses."""

    def __init__(self) -> None:
        self.data: dict[str, object] = {}
        self.ttls: dict[str, int] = {}

    def get(self, key: str) -> object | None:
        return self.data.get(key)

    def set(self, key: str, value: object) -> None:
        self.data[key] = value

    def setex(self, key: str, ttl: int, value: object) -> None:
        self.data[key] = value
        self.ttls[key] = ttl

    def delete(self, key: str) -> None:
        self.data.pop(key, None)
        self.ttls.pop(key, None)

    def scan_iter(self, pattern: str) -> list[str]:
        prefix = pattern.rstrip("*")
        return [k for k in list(self.data) if k.startswith(prefix)]


def _bind(cache: rc.RedisCache, wire: object) -> rc.RedisCache:
    """Attach a backend the way a live probe would, without touching sockets."""
    cache._client = wire
    cache._client_probed = True
    return cache


@pytest.fixture(autouse=True)
def _isolated_backends():
    """Keep each test's local LRU and memoised client to itself."""
    saved_local = dict(rc._LOCAL)
    saved_client, saved_until = rc._CLIENT, rc._CLIENT_DEAD_UNTIL
    rc._reset_client_cache()
    yield
    with rc._LOCAL_LOCK:
        rc._LOCAL.clear()
        rc._LOCAL.update(saved_local)
    rc._CLIENT = saved_client
    rc._CLIENT_DEAD_UNTIL = saved_until


# ---------------------------------------------------------------------------
# 1. Sharing actually happens
# ---------------------------------------------------------------------------


def test_a_gzip_payload_crosses_the_process_boundary() -> None:
    """The module's stated use case: a compressed asset shared across processes."""
    wire = _Wire()
    writer = _bind(rc.RedisCache("assets"), wire)
    payload = gzip.compress(b"console.log(1)", compresslevel=6, mtime=0)

    assert writer.set("app.js", (payload, '"etag"')) is True

    # A second process has its own local LRU; only the wire is shared.
    rc._local_delete(writer._key("app.js"))
    reader = _bind(rc.RedisCache("assets"), wire)

    got = reader.get("app.js")
    assert got is not None
    assert got[0] == payload
    assert gzip.decompress(got[0]) == b"console.log(1)"


def test_both_write_paths_produce_values_the_other_path_can_read() -> None:
    """``set`` and ``[]=`` must agree, or a reader gets a type it did not store."""
    wire = _Wire()
    cache = _bind(rc.RedisCache("types"), wire)
    cache.set("via-set", b"\x00\xffbytes")
    cache["via-item"] = b"\x00\xffbytes"

    rc._local_delete(cache._key("via-set"))
    rc._local_delete(cache._key("via-item"))
    reader = _bind(rc.RedisCache("types"), wire)

    for key in ("via-set", "via-item"):
        value = reader[key]
        assert isinstance(value, bytes), f"{key} came back as {type(value).__name__}"
        assert value == b"\x00\xffbytes"


def test_the_codec_round_trips_nested_bytes_through_one_home() -> None:
    value = {"a": [b"\x00", ("t", 1)], "b": None}
    assert rc._decode(rc._encode(value)) == {"a": [b"\x00", ["t", 1]], "b": None}


# ---------------------------------------------------------------------------
# 2. Read semantics: a negative answer is authoritative
# ---------------------------------------------------------------------------


def test_a_negative_answer_from_the_shared_store_is_authoritative() -> None:
    wire = _Wire()
    cache = _bind(rc.RedisCache("truth"), wire)
    # A local copy from before another process evicted the entry.
    rc._local_set(cache._key("stale"), "yesterday", None)

    assert cache.get("stale") is None


def test_delete_removes_the_local_copy_too() -> None:
    wire = _Wire()
    cache = _bind(rc.RedisCache("truth"), wire)
    cache.set("k", "v")
    # A copy left by a write that happened while the driver was down.
    rc._local_set(cache._key("k"), "v", None)
    assert cache.get("k") == "v"

    assert cache.delete("k") is True
    assert cache.get("k") is None
    assert wire.data == {}
    assert rc._local_get(cache._key("k")) is None

    class _Down(_Wire):
        def get(self, key: str) -> object | None:
            raise ConnectionError("down")

    # Even with the driver down, a deleted value must not come back.
    assert _bind(rc.RedisCache("truth"), _Down()).get("k") is None


def test_clear_empties_the_namespace_on_both_backends() -> None:
    wire = _Wire()
    scoped = _bind(rc.RedisCache("ns"), wire)
    scoped.set("one", 1)
    scoped.set("two", 2)
    bystander = _bind(rc.RedisCache("other"), wire)
    bystander.set("keep", 3)

    assert scoped.clear() is True

    assert scoped.get("one") is None
    assert scoped.get("two") is None
    assert bystander.get("keep") == 3
    assert list(wire.data) == [bystander._key("keep")]


# ---------------------------------------------------------------------------
# 3. Degradation is honest about which copy answered
# ---------------------------------------------------------------------------


def test_a_value_that_cannot_cross_the_wire_is_reported_not_silently_local() -> None:
    """A write that never reached Redis must say so, and must not fake a hit."""
    wire = _Wire()
    cache = _bind(rc.RedisCache("local"), wire)
    sentinel = object()

    assert cache.set("opaque", sentinel) is False
    assert wire.data == {}, "an unencodable value must not be half-written"
    # Redis is answering, and it has nothing: the authoritative answer wins.
    assert cache.get("opaque") is None

    # The local copy is still there for the case it exists for — an outage.
    class _Down(_Wire):
        def get(self, key: str) -> object | None:
            raise ConnectionError("down")

    assert _bind(rc.RedisCache("local"), _Down()).get("opaque") is sentinel

    # And it was never shared, so a sibling process cannot see it.
    rc._local_delete(cache._key("opaque"))
    assert _bind(rc.RedisCache("local"), wire).get("opaque") is None


def test_a_shared_value_is_not_mirrored_into_the_local_lru() -> None:
    """No in-process L1: a copy only Redis can invalidate is a stale-read bug."""
    wire = _Wire()
    cache = _bind(rc.RedisCache("l1"), wire)
    assert cache.set("k", "v") is True

    assert cache.get("k") == "v"
    assert rc._local_get(cache._key("k")) is None


def test_a_dead_driver_degrades_to_the_local_copy_instead_of_raising() -> None:
    class _Down(_Wire):
        def get(self, key: str) -> object | None:
            raise ConnectionError("down")

        def set(self, key: str, value: object) -> None:
            raise ConnectionError("down")

        def setex(self, key: str, ttl: int, value: object) -> None:
            raise ConnectionError("down")

    cache = _bind(rc.RedisCache("outage"), _Down())
    assert cache.set("k", {"v": [1, b"b"]}) is False
    assert cache.get("k") == {"v": [1, b"b"]}


def test_writes_report_whether_they_reached_the_shared_store() -> None:
    wire = _Wire()
    assert _bind(rc.RedisCache("report"), wire).set("k", "v") is True

    lonely = rc.RedisCache("report-none")
    lonely._client_probed = True
    lonely._client = None
    assert lonely.set("k", "v") is False


# ---------------------------------------------------------------------------
# 4. TTL and connection budget
# ---------------------------------------------------------------------------


def test_ttl_reaches_the_wire_as_whole_seconds() -> None:
    wire = _Wire()
    cache = _bind(rc.RedisCache("ttl", ttl=90), wire)
    cache.set("inherits", "v")
    cache.set("explicit", "v", ttl=7)

    assert wire.ttls[cache._key("inherits")] == 90
    assert wire.ttls[cache._key("explicit")] == 7

    plain = _bind(rc.RedisCache("ttl-plain"), wire)
    plain.set("forever", "v")
    assert plain._key("forever") in wire.data
    assert plain._key("forever") not in wire.ttls


def test_every_cache_in_the_process_shares_one_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """One pool per process, not one per namespace."""
    wire = _Wire()
    probes: list[int] = []

    def _probe() -> object:
        probes.append(1)
        return wire

    monkeypatch.setattr(rc, "_redis_client", _probe)
    rc._reset_client_cache()

    first = rc.RedisCache("a")
    second = rc.RedisCache("b")
    assert first._redis() is wire
    assert second._redis() is wire
    assert len(probes) == 1


def test_a_failed_probe_is_retried_after_the_window(monkeypatch: pytest.MonkeyPatch) -> None:
    """A Redis that starts later must be picked up without a restart."""
    probes: list[int] = []

    def _probe() -> None:
        probes.append(1)
        return None

    monkeypatch.setattr(rc, "_redis_client", _probe)
    rc._reset_client_cache()

    assert rc.RedisCache("a")._redis() is None
    assert rc.RedisCache("b")._redis() is None
    assert len(probes) == 1, "a failure inside the window must not re-probe"

    rc._CLIENT_DEAD_UNTIL = 0.0
    assert rc.RedisCache("c")._redis() is None
    assert len(probes) == 2, "an expired window must re-probe"


# ---------------------------------------------------------------------------
# 5. The shape of the shipped module
# ---------------------------------------------------------------------------


def test_the_shipped_module_has_no_unreachable_dunder_definitions() -> None:
    tree = ast.parse((REPO_ROOT / "minicc/redis_cache.py").read_text("utf8"))
    dunders = {"__getitem__", "__setitem__", "__delitem__", "__contains__"}
    nested: list[tuple[str, int]] = []

    def walk(node: ast.AST, inside_function: bool = False) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef):
                if inside_function and child.name in dunders:
                    nested.append((child.name, child.lineno))
                walk(child, True)
            else:
                walk(child, inside_function)

    walk(tree)
    assert nested == [], f"unreachable dunder definitions came back: {nested}"
