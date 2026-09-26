"""Session allowlist tests: matching, plan-mode lock, HTTP routes."""

from __future__ import annotations

import json
import threading
import time
import types
import urllib.request
from pathlib import Path

from minicc.allowlist import add_session_rule, match_session_allowlist, session_rules
from minicc.audit import authorize_tool
from minicc.web import AgentService, MiniccHTTPServer
from minicc.webauth import WebAuth


def _config() -> types.SimpleNamespace:
    return types.SimpleNamespace(
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


def test_path_and_command_globs_match(tmp_path: Path) -> None:
    add_session_rule(tmp_path, "s1", path="src/*.py", command="pytest *", tool="webfetch")
    assert match_session_allowlist(tmp_path, "s1", "write_file", {"path": "src/main.py"})
    assert not match_session_allowlist(tmp_path, "s1", "write_file", {"path": "README.md"})
    assert match_session_allowlist(tmp_path, "s1", "bash", {"command": "pytest -q tests"})
    assert not match_session_allowlist(tmp_path, "s1", "bash", {"command": "rm -rf /"})
    assert match_session_allowlist(tmp_path, "s1", "webfetch", {"url": "https://example.com"})


def test_allowlist_overrides_missing_task_write_but_not_plan_mode(tmp_path: Path) -> None:
    add_session_rule(tmp_path, "s1", path="notes.txt", tool="write_file")
    allowed = authorize_tool(
        "write_file",
        "write",
        {"path": "notes.txt"},
        allow_changes=False,
        allow_network=False,
        permission_mode="default",
        session_id="s1",
        workspace=tmp_path,
    )
    assert allowed.allowed is True
    assert allowed.authorization == "session_allowlist"
    planned = authorize_tool(
        "write_file",
        "write",
        {"path": "notes.txt"},
        allow_changes=True,
        allow_network=True,
        permission_mode="plan",
        session_id="s1",
        workspace=tmp_path,
    )
    assert planned.allowed is False
    assert planned.authorization == "plan_mode_write"


def test_allowlist_can_unlock_network_tools(tmp_path: Path) -> None:
    add_session_rule(tmp_path, "s1", tool="webfetch")
    decision = authorize_tool(
        "webfetch",
        "readonly",
        {"url": "https://example.com"},
        allow_changes=False,
        allow_network=False,
        session_id="s1",
        workspace=tmp_path,
    )
    assert decision.allowed is True
    assert decision.authorization == "session_allowlist"


def test_allowlist_http_roundtrip(tmp_path: Path) -> None:
    service = AgentService(tmp_path, _config())
    server = MiniccHTTPServer(("127.0.0.1", 0), service, auth=WebAuth("t", required=False))
    served: list[BaseException] = []

    def _serve() -> None:
        try:
            server.serve_forever(poll_interval=0.05)
        except BaseException as exc:
            served.append(exc)

    thread = threading.Thread(target=_serve, daemon=True, name="minicc-test-server")
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    # M8-T68: the url is published only once the thread has actually served, so a
    # dead server names itself instead of showing up as a later connection refusal.
    deadline = time.monotonic() + 10.0
    while True:
        if served or not thread.is_alive():
            raise AssertionError(
                f"the test HTTP server thread {thread.name!r} died before serving {url}: {served!r}"
            )
        try:
            with urllib.request.urlopen(f"{url}/api/health", timeout=5) as probe:
                if probe.status == 200:
                    break
        except OSError:
            pass
        if time.monotonic() >= deadline:
            raise AssertionError(
                f"the test HTTP server thread {thread.name!r} never answered GET /api/health "
                f"within 10s at {url}"
            )
        time.sleep(0.02)
    try:
        with urllib.request.urlopen(f"{url}/api/allowlist?session_id=web-1", timeout=5) as response:
            empty = json.loads(response.read())
        assert empty["session_id"] == "web-1"
        assert empty["commands"] == []
        request = urllib.request.Request(
            f"{url}/api/allowlist",
            data=json.dumps({
                "session_id": "web-1",
                "commands": ["pytest *"],
                "paths": ["src/**"],
                "tools": ["webfetch"],
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            saved = json.loads(response.read())
        assert saved["tools"] == ["webfetch"]
        assert session_rules(tmp_path, "web-1")["paths"] == ["src/**"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        service.shutdown()
        assert not thread.is_alive(), (
            f"the allowlist test server thread {thread.name!r} was still alive 5s "
            f"after shutdown() at {url}; its socket can still answer and the "
            "service behind it is still writing the allowlist store"
        )
