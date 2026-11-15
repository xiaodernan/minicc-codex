"""M8-T1051: the storm — 24 threads hit the loopback HTTP surface at once.

The Doctor panel ships a Load Lab (24 workers × 24 requests) that proves the
*running* app can take a synthetic surge; this module proves the same in pytest,
deterministically, from real requests against the real ``ThreadingHTTPServer`` +
real ``AgentService`` on an ephemeral port — the same harness ``test_http_surface``
uses. No live network, no wall-clock sleeps, no virtual provider.

Mega-spec §十一 asks for exactly this: 模拟海量用户、高并发、瞬间大数据量冲击系统，
包括撞库式回放风暴. The three invariants under fire are boring on purpose:

1. Every read route answers 200 with well-formed JSON — the surface never 500s
   on a load spike, and the shared read caches (LRU/Redis pools) hold.
2. Wire-frame garbage bodies answer 400, never 500 — the parser eats the storm
   and stays standing; no exception escapes to the wire.
3. A cross-site POST replay flood — the撞库-shaped rehearsal — answers 403 on
   every flight, before any business logic runs; nothing is created, nothing is
   accepted, nothing crashes.
"""

from __future__ import annotations

import concurrent.futures
import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from tests.test_http_surface import _LiveServer


@pytest.fixture(scope="module")
def storm_server(tmp_path_factory: pytest.TempPathFactory):
    server = _LiveServer(tmp_path_factory.mktemp("storm"))
    try:
        yield server
    finally:
        server.shutdown()


def _fire(url: str, *, method: str, body: bytes | None = None, headers: dict | None = None):
    request = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except urllib.error.URLError:
        # The surface must never refuse the connection outright under load.
        return 0, b""


def test_the_read_side_holds_under_a_thundering_herd(storm_server) -> None:
    reads = ["/api/health", "/api/digest", "/api/stats", "/api/worldpulse", "/api/admin/summary", "/api/metrics"]
    jobs = [reads[i % len(reads)] for i in range(120)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=24) as pool:
        results = list(pool.map(lambda p: _fire(storm_server.url + p, method="GET"), jobs))
    statuses = [status for status, _ in results]
    assert all(status == 200 for status in statuses), statuses
    for status, payload in results:
        assert isinstance(json.loads(payload), (dict, list)), payload[:200]


def test_a_storm_of_wire_frame_garbage_answers_400_never_500(storm_server) -> None:
    garbage = [
        b"{",
        b"}{ not json at all",
        b"\xff\xfe\x00 definitely not utf-8 \x80\x81",
        b"[1, 2, 3]",  # valid JSON but wrong shape for a chat-shaped target
        b"null",
        b'"just a string"',
        b"42",
        b"true",
    ]
    jobs = [garbage[i % len(garbage)] for i in range(64)]

    def one_body(body: bytes):
        return _fire(
            storm_server.url + "/api/chat",
            method="POST",
            body=body,
            headers={"Content-Type": "application/json"},
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=24) as pool:
        results = list(pool.map(one_body, jobs))
    statuses = [status for status, _ in results]
    assert all(status == 400 for status in statuses), statuses
    assert all(status < 500 for status in statuses), "the parser escaped to the wire"


def test_a_cross_site_replay_burst_answers_403_on_every_flight(storm_server) -> None:
    # 撞库-shaped replay: the same cross-site Origin that browsers send for a
    # forged fetch. Every flight must be denied before any business logic —
    # nothing created, nothing accepted, nothing logged into a queue.
    jobs = [{"task": "noop"}] * 48

    def one(payload):
        return _fire(
            storm_server.url + "/api/tasks",
            method="POST",
            body=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Origin": "https://credential-stuffing.example.invalid",
            },
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=24) as pool:
        results = list(pool.map(one, jobs))
    statuses = [status for status, _ in results]
    assert all(status == 403 for status in statuses), statuses
