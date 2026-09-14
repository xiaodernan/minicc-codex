"""Session rewind tests: store semantics + HTTP route."""

from __future__ import annotations

import json
import threading
import types
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from minicc.session import SessionError, SessionStore
from minicc.web import AgentService, MiniccHTTPServer
from minicc.webauth import WebAuth


def _store(tmp_path: Path) -> SessionStore:
    store = SessionStore(tmp_path, "rewind-test")
    messages = [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "第一个问题"},
        {"role": "assistant", "content": "第一个回答"},
        {"role": "user", "content": "第二个问题"},
        {"role": "assistant", "content": "第二个回答"},
    ]
    store.save(messages)
    return store


def test_rewind_truncates_and_backs_up(tmp_path: Path) -> None:
    store = _store(tmp_path)
    result = store.rewind(3)
    assert result["kept"] == 3
    assert result["removed"] == 2
    assert result["backup"] == "rewind-test.pre-rewind.json"
    messages = store.load("system prompt")
    assert len(messages) == 3
    assert messages[-1]["content"] == "第一个回答"
    backup = tmp_path / ".minicc" / "sessions" / "rewind-test.pre-rewind.json"
    payload = json.loads(backup.read_text(encoding="utf-8"))
    assert len(payload["messages"]) == 5  # full pre-rewind snapshot


def test_rewind_noop_past_end_and_validation(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert store.rewind(99) == {"kept": 5, "removed": 0, "backup": ""}
    with pytest.raises(SessionError, match="至少为 1"):
        store.rewind(0)
    empty = SessionStore(tmp_path, "missing-session")
    with pytest.raises(SessionError, match="不存在"):
        empty.rewind(3)


def test_rewind_twice_replaces_backup(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.rewind(4)
    store.rewind(2)
    messages = store.load("system prompt")
    assert len(messages) == 2
    backup = json.loads(
        (tmp_path / ".minicc" / "sessions" / "rewind-test.pre-rewind.json").read_text(encoding="utf-8")
    )
    # Second rewind backs up the already-truncated 4-message state.
    assert len(backup["messages"]) == 4


def test_service_and_http_route(tmp_path: Path) -> None:
    _store(tmp_path)
    config = types.SimpleNamespace(
        yolo=False,
        max_concurrent_tasks=2,
        sandbox_mode="host",
        sandbox_image="python:3.11-slim",
        base_url="https://example.test/v1",
        api_key="test-key",
        model="test-model",
        timeout=10,
        tool_mode="auto",
        reasoning_effort="high",
        max_turns=4,
        compact_threshold=300_000,
        context_window_tokens=300_000,
    )
    service = AgentService(tmp_path, config)
    server = MiniccHTTPServer(("127.0.0.1", 0), service, auth=WebAuth("t", required=False))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        request = urllib.request.Request(
            f"{url}/api/sessions/rewind",
            data=json.dumps({"session_id": "rewind-test", "keep_messages": 3}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read())
        assert payload == {"kept": 3, "removed": 2, "backup": "rewind-test.pre-rewind.json"}

        # Invalid session id -> 400 via SessionError handling.
        bad = urllib.request.Request(
            f"{url}/api/sessions/rewind",
            data=json.dumps({"session_id": "bad id!", "keep_messages": 3}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(bad, timeout=5)
            raise AssertionError("expected 400")
        except urllib.error.HTTPError as exc:
            assert exc.code == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        service.shutdown()
