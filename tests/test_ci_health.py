"""M8-T1062: /api/ci_status — the admin tile's single read: live mainline health
for THIS repository, from the real GitHub REST API.

Two honesty rules are pinned here:

1. the route NEVER answers 500 and never raises — network death, rate limits and
   repository moves are reported as ``live=False`` with an ``errors`` list, not
   a traceback
2. cache mechanics stay out of the answer: every test installs a fresh, empty
   cache stub, so what the test asserts is the parse logic — never a value
   a previous test happened to store (and the order of tests can never leak state).
"""

from __future__ import annotations

import json
import urllib.error

import pytest
from tests.test_http_surface import _LiveServer, _request

from minicc import ci_health


class _FreshCache:
    def __init__(self) -> None:
        self._store: dict[str, object] = {}

    def get(self, key: str):
        return self._store.get(key)

    def set(self, key: str, value, ttl: float | None = None) -> None:  # noqa: ARG002 - mirrors the real cache contract
        self._store[key] = value


@pytest.fixture(autouse=True)
def fresh_cache(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(ci_health, "default_cache", _FreshCache())

def _fake_get_json_ok(url: str):
    if "actions/runs" in url:
        return {
            "workflow_runs": [
                {
                    "conclusion": "success",
                    "status": "completed",
                    "name": "CI",
                    "created_at": "2026-11-16T01:00:00Z",
                    "head_sha": "abc123deadbeef456",
                    "html_url": "https://github.com/xiaodernan/minicc-codex/actions/runs/1",
                }
            ]
        }
    if "pulls" in url:
        return [{"number": 17}]
    if "issues" in url:
        # pull_request entries must be filtered out — GitHub's issues endpoint returns both
        return [{"number": 1, "pull_request": {"url": "x"}}, {"number": 2}, {"number": 3, "pull_request": {"url": "y"}}, {"number": 4}]
    raise AssertionError("unexpected url " + url)


def test_a_network_death_yields_live_false_not_a_traceback(monkeypatch: pytest.MonkeyPatch) -> None:
    def dead(url: str):  # noqa: ARG001
        raise urllib.error.URLError("boom")

    monkeypatch.setattr(ci_health, "_get_json", dead)
    payload = ci_health.fetch_ci_health()
    assert payload["live"] is False
    assert payload["latest_run"] is None
    assert payload["recent"] == []
    assert payload["errors"] is not None and len(payload["errors"]) == 3


def test_real_wire_shape_parses_and_filters_prs_from_issues(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ci_health, "_get_json", _fake_get_json_ok)
    payload = ci_health.fetch_ci_health()
    assert payload["live"] is True
    latest = payload["latest_run"]
    assert latest["conclusion"] == "success"
    assert latest["head_sha"] == "abc123d"
    assert latest["workflow"] == "CI"
    assert len(payload["recent"]) == 1
    assert payload["open_prs"] == 1
    # 4 entries minus 2 pull_request entries = 2 honest issues
    assert payload["open_issues"] == 2
    assert payload["errors"] is None


def test_ci_status_route_answers_200_json_over_a_live_server(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    def dead(url: str):  # noqa: ARG001
        raise urllib.error.URLError("no wire in this test")

    monkeypatch.setattr(ci_health, "_get_json", dead)
    live = _LiveServer(tmp_path)
    try:
        status, _, body = _request(f"{live.url}/api/ci_status", method="GET")
    finally:
        live.shutdown()
    assert status == 200
    payload = json.loads(body)
    assert payload["live"] is False
    assert "errors" in payload


def test_ci_status_route_compare_line_executes(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ci_health, "_get_json", _fake_get_json_ok)
    live = _LiveServer(tmp_path)
    try:
        status, _, body = _request(f"{live.url}/api/ci_status", method="GET")
    finally:
        live.shutdown()
    assert status == 200
    payload = json.loads(body)
    assert payload["live"] is True
    assert payload["latest_run"]["conclusion"] == "success"
