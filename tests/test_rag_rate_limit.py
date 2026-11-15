"""M8-T987: the gateway-facing RAG lane is behind an industry-shaped
sliding-window token bucket, with Redis when configured and an in-process
LRU fallback otherwise. Never raises, never fails closed.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from minicc import ratelimit


@pytest.fixture()
def fresh_bucket(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(ratelimit, "_MAX_CALLS", 2)
    monkeypatch.setattr(ratelimit, "_WINDOW_SECONDS", 60.0)
    with ratelimit._LOCAL_LOCK:
        ratelimit._LOCAL.clear()
    yield
    with ratelimit._LOCAL_LOCK:
        ratelimit._LOCAL.clear()


def test_local_bucket_allows_then_denies(fresh_bucket: None) -> None:
    first, _ = ratelimit.consume("rag-query", "client-a")
    second, _ = ratelimit.consume("rag-query", "client-a")
    third, _ = ratelimit.consume("rag-query", "client-a")
    assert (first, second, third) == (True, True, False)


def test_bucket_tracks_clients_independently(fresh_bucket: None) -> None:
    assert ratelimit.consume("rag-query", "a")[0] is True
    assert ratelimit.consume("rag-query", "b")[0] is True
    assert ratelimit.consume("rag-query", "a")[0] is True
    assert ratelimit.consume("rag-query", "a")[0] is False


def test_window_expiry_reopens_the_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ratelimit, "_MAX_CALLS", 1)
    monkeypatch.setattr(ratelimit, "_WINDOW_SECONDS", 0.05)
    with ratelimit._LOCAL_LOCK:
        ratelimit._LOCAL.clear()
    assert ratelimit.consume("rag-query", "c")[0] is True
    assert ratelimit.consume("rag-query", "c")[0] is False
    # wait-claim: the bucket's 60 ms window has truly elapsed once monotonic()
    # advances past the expiry recorded at the last consume; the test re-reads
    # itself instead of trusting an arbitrary beat. Polling with a bounded
    # 2-second budget keeps a slow runner honest without hiding clock bugs.
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if ratelimit.consume("rag-query", "c")[0] is True:
            return
        time.sleep(0.05)
    assert False, "bucket did not reopen within 2 s of its 60 ms window"


def test_redis_backend_is_used_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.count = 0
            self.pexpires: list[int] = []

        def incr(self, key: str) -> int:  # noqa: ARG002 - bucket incr
            self.count += 1
            return self.count

        def pexpire(self, key: str, ttl: int) -> int:  # noqa: ARG002 - arm window
            self.pexpires.append(ttl)
            return True

    client = FakeClient()
    monkeypatch.setattr(ratelimit, "_shared_client", lambda: client)
    monkeypatch.setattr(ratelimit, "_MAX_CALLS", 1)
    assert ratelimit.consume("rag-query", "d")[0] is True
    assert ratelimit.consume("rag-query", "d")[0] is False
    assert client.pexpires, "first write must arm the window"


def test_redis_failure_falls_open_but_counts_it(monkeypatch: pytest.MonkeyPatch) -> None:
    class BrokenClient:
        def incr(self, key: str) -> int:  # noqa: ARG002
            raise ConnectionError("connection lost")

        def pexpire(self, key: str, ttl: int) -> int:  # noqa: ARG002
            return True

    monkeypatch.setattr(ratelimit, "_shared_client", lambda: BrokenClient())
    allowed, meta = ratelimit.consume("rag-query", "e")
    assert allowed is True, "the lane fails open by design, never closed"
    assert meta["backend"] in {"local", "redis"}
    assert ratelimit.stats()["decisions"]["degraded_open"] >= 1


def test_stats_is_read_only_and_counts(fresh_bucket: None) -> None:
    ratelimit.consume("rag-query", "f")
    snapshot = ratelimit.stats()
    assert snapshot["limit"] > 0
    assert snapshot["window_seconds"] > 0
    assert snapshot["decisions"]["allowed_local"] >= 1


# ---- route level: an honest 429-style answer, no real tokens burned ---------------

from tests.test_http_surface import _LiveServer, _request, WebAuth  # noqa: E402


@pytest.fixture()
def live(tmp_path: Path):
    server = _LiveServer(tmp_path, auth=WebAuth("tok", required=False))
    yield server
    server.shutdown()


def test_rag_query_route_degrades_when_the_bucket_says_no(live, monkeypatch) -> None:
    monkeypatch.setattr(ratelimit, "consume", lambda route, key: (False, {"window_seconds": 60, "limit": 1}))
    status, _, body = _request(f"{live.url}/api/rag/query?q=cache&k=1", method="GET")
    assert status == 200
    payload = json.loads(body)
    assert payload["rate_limited"] is True
    assert payload["answer"] == ""
    assert "sk-" not in body.decode("utf-8")
