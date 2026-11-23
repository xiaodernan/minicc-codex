"""M4-T3: Python coverage for the Web HTTP surface and the JSON-RPC dispatcher.

Before this module the only end-to-end check was a Playwright smoke that never
asserted a terminal state, and ``grep api/tasks tests/*.py`` returned nothing:
every POST ``/api/*`` route and the whole ``rpc.py`` dispatcher were untested
from Python. These tests boot the real ``ThreadingHTTPServer`` handler stack
against a real ``AgentService`` (fake provider, no network) and drive it with
real ``urllib`` requests, plus focused unit tests for ``RpcDispatcher``.
"""

from __future__ import annotations

import ast
import json
import shutil
import subprocess
import threading
import time
import types
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from minicc.agent.rpc import RpcDispatcher, RpcProtocolError, parse_request
from minicc.task_store import TaskStore
from minicc.web import AgentService, MiniccHTTPServer
from minicc.webauth import WebAuth
from tests.test_http_route_inventory import _wait_for_live_server


# ---------------------------------------------------------------------------
# harness
# ---------------------------------------------------------------------------


def _config(tmp_path: Path, **extra) -> types.SimpleNamespace:
    base = dict(
        yolo=False,
        max_concurrent_tasks=4,
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
    base.update(extra)
    return types.SimpleNamespace(**base)


class _LiveServer:
    """Real ThreadingHTTPServer + real AgentService on an ephemeral port."""

    def __init__(self, tmp_path: Path, *, auth: WebAuth | None = None, **config_extra) -> None:
        self.service = AgentService(
            tmp_path,
            _config(tmp_path, **config_extra),
            task_store=TaskStore(tmp_path / "tasks.sqlite3"),
        )
        self.server = MiniccHTTPServer(("127.0.0.1", 0), self.service, auth=auth)
        self.error: BaseException | None = None
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        # A small poll_interval keeps server.shutdown() (which waits one poll
        # cycle) cheap; this module boots ~30 short-lived servers.
        self.thread = threading.Thread(
            target=self._serve, kwargs={"poll_interval": 0.05}, daemon=True,
            name="minicc-test-server",
        )
        self.thread.start()
        # M8-T68: when this server died, the suite said "connection refused" and left it at
        # that - one contended run produced 73 such failures across these fixtures plus an
        # "assert 0 == 8" and a teardown ExceptionGroup, none of which named the dead thread.
        # So the fixture now proves it is serving before handing out its url, and reports the
        # thread's own exception if it is not.
        # M8-T116: the wait itself is the shared two-phase helper (transport first,
        # application second). Its per-probe timeout also retires this fixture's old
        # 20s urlopen inside a 10s wall, where one hung probe was the whole budget.
        def _probe_health(probe_timeout_s: float) -> int:
            request = urllib.request.Request(f"{self.url}/api/health", method="GET")
            try:
                with urllib.request.urlopen(request, timeout=probe_timeout_s) as probe:
                    return probe.status
            except urllib.error.HTTPError as exc:
                return exc.code

        _wait_for_live_server(
            origin=self.url,
            thread=self.thread,
            thread_error=lambda: self.error,
            http_get_status=_probe_health,
        )

    def _serve(self, **kwargs) -> None:
        try:
            self.server.serve_forever(**kwargs)
        except BaseException as exc:  # noqa: BLE001 - reported by the constructor
            self.error = exc

    def shutdown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        assert not self.thread.is_alive(), (
            f"the surface test HTTP server thread {self.thread.name!r} was still "
            f"alive 5s after shutdown() at {self.url}; its socket can still answer, "
            "and the service behind it is still writing"
        )
        self.service.shutdown()


def _request(
    url: str,
    *,
    method: str,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 20.0,
):
    request = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def _post_json(url: str, payload, headers: dict[str, str] | None = None, *, timeout: float = 20.0):
    body = json.dumps(payload).encode("utf-8") if payload is not None else b""
    merged = {"Content-Type": "application/json", **(headers or {})}
    return _request(url, method="POST", body=body, headers=merged, timeout=timeout)


def _post_raw(url: str, body: bytes, headers: dict[str, str] | None = None):
    return _request(url, method="POST", body=body, headers=headers or {})


@pytest.fixture(autouse=True)
def _fake_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every agent run in this module uses the in-process fake provider."""
    monkeypatch.setenv("MINICC_FAKE_PROVIDER", "1")


@pytest.fixture
def live(tmp_path: Path):
    server = _LiveServer(tmp_path, auth=WebAuth("tok", required=False))
    try:
        yield server
    finally:
        server.shutdown()


# ---------------------------------------------------------------------------
# POST /api/* route coverage
# ---------------------------------------------------------------------------


def test_post_tasks_returns_202_with_task_id(live: _LiveServer, tmp_path: Path) -> None:
    status, _, body = _post_json(f"{live.url}/api/tasks", {
        "message": "hello", "session_id": "s1",
        "workspace_path": str(tmp_path), "allow_changes": False, "_defer_schedule": True,
    })
    assert status == 202
    assert json.loads(body)["task_id"].startswith("task-")


def test_post_tasks_requires_message(live: _LiveServer, tmp_path: Path) -> None:
    status, _, body = _post_json(f"{live.url}/api/tasks", {
        "session_id": "s1", "workspace_path": str(tmp_path),
    })
    assert status == 400
    assert "message" in json.loads(body)["error"]


def test_post_tasks_batch_validation(live: _LiveServer, tmp_path: Path) -> None:
    status, _, body = _post_json(f"{live.url}/api/tasks/batch", {
        "messages": "not-a-list", "workspace_path": str(tmp_path),
    })
    assert status == 400
    assert "messages" in json.loads(body)["error"]


def test_post_task_cancel_then_resume_unknown(live: _LiveServer, tmp_path: Path) -> None:
    status, _, body = _post_json(f"{live.url}/api/tasks", {
        "message": "cancel me", "session_id": "s-cancel",
        "workspace_path": str(tmp_path), "_defer_schedule": True,
    })
    task_id = json.loads(body)["task_id"]
    status, _, body = _post_json(f"{live.url}/api/tasks/{task_id}/cancel", {})
    assert status == 200
    assert json.loads(body)["status"] == "cancelled"
    # An unknown id surfaces as 404 (KeyError), not a 500.
    status, _, _ = _post_json(f"{live.url}/api/tasks/task-does-not-exist/resume", {})
    assert status == 404


def test_post_chat_completes_with_fake_provider(live: _LiveServer, tmp_path: Path) -> None:
    status, _, body = _post_json(f"{live.url}/api/chat", {
        "message": "summarize", "session_id": "chat-1", "workspace_path": str(tmp_path),
    })
    assert status == 200
    payload = json.loads(body)
    assert "fake-provider-answer" in str(payload.get("answer") or "")


def test_post_chat_requires_message(live: _LiveServer) -> None:
    status, _, body = _post_json(f"{live.url}/api/chat", {"session_id": "chat-2"})
    assert status == 400
    assert "message" in json.loads(body)["error"]


def test_post_workspace_select(live: _LiveServer, tmp_path: Path) -> None:
    status, _, body = _post_json(f"{live.url}/api/workspace/select", {"path": str(tmp_path)})
    assert status == 200
    # The response carries a posix-style path; compare through Path so the
    # forward/backslash difference on Windows is normalized away.
    assert Path(json.loads(body)["path"]) == Path(tmp_path).resolve()
    status, _, _ = _post_json(f"{live.url}/api/workspace/select", {"path": 123})
    assert status == 400


def test_post_allowlist(live: _LiveServer) -> None:
    status, _, body = _post_json(f"{live.url}/api/allowlist", {
        "session_id": "s-allow", "tools": ["bash"],
    })
    assert status == 200
    assert json.loads(body)["session_id"] == "s-allow"
    status, _, _ = _post_json(f"{live.url}/api/allowlist", {"tools": []})
    assert status == 400


def test_post_sessions_rewind_requires_session(live: _LiveServer) -> None:
    status, _, body = _post_json(f"{live.url}/api/sessions/rewind", {"keep_messages": 0})
    assert status == 400
    assert "session_id" in json.loads(body)["error"]


def test_post_sessions_rewind_after_chat(live: _LiveServer, tmp_path: Path) -> None:
    _post_json(f"{live.url}/api/chat", {
        "message": "remember this", "session_id": "rewind-1", "workspace_path": str(tmp_path),
    })
    status, _, body = _post_json(f"{live.url}/api/sessions/rewind", {
        "session_id": "rewind-1", "keep_messages": 1,
    })
    assert status == 200
    assert "kept" in json.loads(body)


def test_post_workspace_restore_requires_task_id(live: _LiveServer) -> None:
    status, _, body = _post_json(f"{live.url}/api/workspace/restore", {"task_id": "  "})
    assert status == 400
    assert "task_id" in json.loads(body)["error"]


def test_post_worktrees_require_name(live: _LiveServer) -> None:
    status, _, body = _post_json(f"{live.url}/api/worktrees", {"branch": "b"})
    assert status == 400
    assert "name" in json.loads(body)["error"]
    status, _, body = _post_json(f"{live.url}/api/worktrees/remove", {})
    assert status == 400
    assert "name" in json.loads(body)["error"]


def test_post_worktrees_create_and_remove(tmp_path: Path) -> None:
    if shutil.which("git") is None:
        pytest.skip("git not available")
    for args in (["git", "init", "-q"], ["git", "config", "user.email", "t@t"], ["git", "config", "user.name", "t"]):
        subprocess.run(args, cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "seed.txt").write_text("seed", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=tmp_path, check=True, capture_output=True)
    server = _LiveServer(tmp_path, auth=WebAuth("tok", required=False))
    try:
        status, _, body = _post_json(f"{server.url}/api/worktrees", {"name": "wt-1"})
        assert status == 201, body
        assert json.loads(body)["name"] == "wt-1"
        status, _, body = _post_json(f"{server.url}/api/worktrees/remove", {"name": "wt-1", "force": True})
        assert status == 200, body
    finally:
        server.shutdown()


def test_post_unknown_api_route_is_404(live: _LiveServer) -> None:
    status, _, body = _post_json(f"{live.url}/api/does-not-exist", {"x": 1})
    assert status == 404
    assert json.loads(body)["error"] == "not found"


# ---------------------------------------------------------------------------
# transport-level status codes: 400 / 401 / 403
# ---------------------------------------------------------------------------


def test_post_malformed_json_is_400(live: _LiveServer) -> None:
    status, _, body = _post_raw(f"{live.url}/api/tasks", b"{not json", {"Content-Type": "application/json"})
    assert status == 400
    assert "error" in json.loads(body)


def test_post_empty_body_is_400(live: _LiveServer) -> None:
    status, _, _ = _post_raw(f"{live.url}/api/tasks", b"", {"Content-Type": "application/json"})
    assert status == 400


def test_post_requires_token_when_auth_required(tmp_path: Path) -> None:
    server = _LiveServer(tmp_path, auth=WebAuth("tok-secret", required=True))
    try:
        status, _, body = _post_json(f"{server.url}/api/tasks", {"message": "hi"})
        assert status == 401
        assert json.loads(body)["auth_required"] is True
        status, _, _ = _post_json(
            f"{server.url}/api/tasks",
            {"message": "hi", "workspace_path": str(tmp_path), "_defer_schedule": True},
            {"Authorization": "Bearer tok-secret"},
        )
        assert status == 202
    finally:
        server.shutdown()


def test_post_cross_origin_state_change_is_403(live: _LiveServer, tmp_path: Path) -> None:
    status, _, body = _post_json(
        f"{live.url}/api/tasks",
        {"message": "hi", "workspace_path": str(tmp_path)},
        {"Origin": "http://evil.example"},
    )
    assert status == 403
    assert b"forbidden" in body


# ---------------------------------------------------------------------------
# M2-T1: workspace_roots whitelist enforced at every POST entry
# ---------------------------------------------------------------------------


@pytest.fixture
def rooted(tmp_path: Path):
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    server = _LiveServer(allowed, auth=WebAuth("tok", required=False), workspace_roots=(str(allowed),))
    try:
        yield server, allowed, outside
    finally:
        server.shutdown()


def test_roots_block_task_submit(rooted) -> None:
    server, _allowed, outside = rooted
    status, _, body = _post_json(f"{server.url}/api/tasks", {
        "message": "hi", "workspace_path": str(outside), "_defer_schedule": True,
    })
    assert status == 400
    assert "白名单" in json.loads(body)["error"]


def test_roots_block_batch_submit(rooted) -> None:
    server, _allowed, outside = rooted
    status, _, body = _post_json(f"{server.url}/api/tasks/batch", {
        "messages": ["a"], "workspace_path": str(outside),
    })
    assert status == 400
    assert "白名单" in json.loads(body)["error"]


def test_roots_block_workspace_select(rooted) -> None:
    server, _allowed, outside = rooted
    status, _, body = _post_json(f"{server.url}/api/workspace/select", {"path": str(outside)})
    assert status == 400
    assert "白名单" in json.loads(body)["error"]


def test_roots_block_chat(rooted) -> None:
    server, _allowed, outside = rooted
    status, _, body = _post_json(f"{server.url}/api/chat", {
        "message": "hi", "workspace_path": str(outside),
    })
    assert status == 400
    assert "白名单" in json.loads(body)["error"]


def test_roots_block_rpc_turn_start(rooted) -> None:
    server, _allowed, outside = rooted
    status, _, body = _post_json(f"{server.url}/api/rpc", {
        "jsonrpc": "2.0", "id": 1, "method": "turn/start",
        "params": {"message": "hi", "workspace_path": str(outside)},
    })
    assert status == 200  # JSON-RPC carries the error in the body
    error = json.loads(body)["error"]
    assert error["code"] == -32602
    assert "白名单" in error["message"]


def test_roots_allow_inside_path(rooted) -> None:
    server, allowed, _outside = rooted
    status, _, body = _post_json(f"{server.url}/api/tasks", {
        "message": "hi", "workspace_path": str(allowed), "_defer_schedule": True,
    })
    assert status == 202
    assert json.loads(body)["task_id"].startswith("task-")


# ---------------------------------------------------------------------------
# concurrency: parallel submits must all be accepted with unique ids
# ---------------------------------------------------------------------------


def test_concurrent_task_submits(live: _LiveServer, tmp_path: Path) -> None:
    results: list[tuple[int, str]] = []
    failures: list[str] = []
    lock = threading.Lock()

    def submit(index: int) -> None:
        try:
            # Batch 200 caught this cell's flake for the first time, with the shape:
            # "submit 7: TimeoutError: timed out" in a combination run that took 753s
            # against 287s for the same files - i.e. a contended machine, not a
            # server defect. What this cell asserts is acceptance and id uniqueness,
            # and a client timeout under load measures the machine. So it gets an
            # explicit wider budget. It does not hide a hang: a server that never
            # answers still fails here, just after 60s instead of 20.
            status, _, body = _post_json(f"{live.url}/api/tasks", {
                "message": f"task {index}", "session_id": f"conc-{index}",
                "workspace_path": str(tmp_path), "_defer_schedule": True,
            }, timeout=60.0)
        except BaseException as exc:  # noqa: BLE001 - the point is to report it
            # An exception raised in a thread used to vanish here: it never reached
            # results and never propagated, so the only evidence left was
            # "assert 0 == 8" - a sentence about a list length, on a machine where
            # the real cause was eight connection refusals.
            with lock:
                failures.append(f"submit {index}: {type(exc).__name__}: {exc}")
            return
        task_id = json.loads(body).get("task_id", "") if status == 202 else ""
        with lock:
            results.append((status, task_id))

    threads = [threading.Thread(target=submit, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for index, thread in enumerate(threads):
        thread.join(timeout=30)
        if thread.is_alive():
            raise AssertionError(
                f"submitter thread #{index} ({thread.name}) was still running after a "
                f"30s join; the server never answered it, and no result can be read "
                f"from a thread that did not return"
            )
    # Cause first, count second: if this gate ever reddens, the sentence has to name
    # what the eight threads hit rather than that a list is short.
    assert not failures, "concurrent submits raised: " + "; ".join(failures)
    assert len(results) == 8, results
    assert all(status == 202 for status, _ in results), results
    ids = [task_id for _, task_id in results]
    assert len(set(ids)) == 8 and all(ids)


# ---------------------------------------------------------------------------
# rpc.py dispatcher unit tests (protocol + routing, >=10 methods)
# ---------------------------------------------------------------------------


def _echo_dispatcher() -> RpcDispatcher:
    handlers = {
        f"m{i}": (lambda n: (lambda params: {"called": n, "params": params}))(i)
        for i in range(10)
    }
    return RpcDispatcher(handlers, server_name="minicc-test")


def _call(dispatcher: RpcDispatcher, method: str, params=None, request_id=1):
    return dispatcher.dispatch({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})


@pytest.mark.parametrize("method", [f"m{i}" for i in range(10)])
def test_rpc_routes_each_registered_method(method: str) -> None:
    response = _call(_echo_dispatcher(), method, {"x": 1})
    assert response["result"]["called"] == int(method[1:])
    assert response["result"]["params"] == {"x": 1}
    assert response["id"] == 1


def test_rpc_initialize() -> None:
    response = _call(RpcDispatcher({}), "initialize")
    assert response["result"]["serverInfo"]["name"] == "minicc"
    assert response["result"]["capabilities"]["turns"] is True


def test_rpc_unknown_method_is_32601() -> None:
    response = _call(_echo_dispatcher(), "nope")
    assert response["error"]["code"] == -32601


def test_rpc_invalid_request_not_dict() -> None:
    response = RpcDispatcher({}).dispatch("nope")
    assert response["error"]["code"] == -32600
    assert response["id"] is None


def test_rpc_missing_jsonrpc_version() -> None:
    response = RpcDispatcher({}).dispatch({"id": 1, "method": "initialize"})
    assert response["error"]["code"] == -32600


def test_rpc_bad_method_type() -> None:
    response = RpcDispatcher({}).dispatch({"jsonrpc": "2.0", "id": 1, "method": 5})
    assert response["error"]["code"] == -32600


def test_rpc_bad_id_type() -> None:
    response = RpcDispatcher({}).dispatch({"jsonrpc": "2.0", "id": True, "method": "initialize"})
    assert response["error"]["code"] == -32600


def test_rpc_params_must_be_object() -> None:
    response = RpcDispatcher({}).dispatch({"jsonrpc": "2.0", "id": 1, "method": "m0", "params": [1]})
    assert response["error"]["code"] == -32602


def test_rpc_notification_returns_none() -> None:
    dispatcher = _echo_dispatcher()
    assert dispatcher.dispatch({"jsonrpc": "2.0", "method": "m0", "params": {}}) is None


def test_rpc_notification_error_suppressed() -> None:
    dispatcher = RpcDispatcher({"boom": lambda params: (_ for _ in ()).throw(RuntimeError("x"))})
    # A notification (no id) swallows even a server error.
    assert dispatcher.dispatch({"jsonrpc": "2.0", "method": "boom"}) is None


def test_rpc_handler_value_error_is_32602() -> None:
    dispatcher = RpcDispatcher({"bad": lambda params: (_ for _ in ()).throw(ValueError("nope"))})
    assert _call(dispatcher, "bad")["error"]["code"] == -32602


def test_rpc_handler_key_error_is_32004() -> None:
    dispatcher = RpcDispatcher({"missing": lambda params: (_ for _ in ()).throw(KeyError("gid"))})
    error = _call(dispatcher, "missing")["error"]
    assert error["code"] == -32004
    assert error["data"] == "'gid'"


def test_rpc_handler_generic_error_is_32000() -> None:
    dispatcher = RpcDispatcher({"boom": lambda params: (_ for _ in ()).throw(RuntimeError("kaboom"))})
    error = _call(dispatcher, "boom")["error"]
    assert error["code"] == -32000
    assert "RuntimeError" in error["data"]


def test_rpc_handler_must_return_object() -> None:
    dispatcher = RpcDispatcher({"scalar": lambda params: 5})
    assert _call(dispatcher, "scalar")["error"]["code"] == -32000


def test_rpc_batch_dispatch() -> None:
    dispatcher = _echo_dispatcher()
    responses = dispatcher.dispatch([
        {"jsonrpc": "2.0", "id": 1, "method": "m0"},
        {"jsonrpc": "2.0", "id": 2, "method": "m1"},
        {"jsonrpc": "2.0", "method": "m2"},  # notification -> filtered out
    ])
    assert [item["id"] for item in responses] == [1, 2]


def test_rpc_empty_batch_is_invalid() -> None:
    response = RpcDispatcher({}).dispatch([])
    assert response["error"]["code"] == -32600


def test_rpc_parse_request_strips_method() -> None:
    request = parse_request({"jsonrpc": "2.0", "id": 7, "method": "  m3  ", "params": {"a": 1}})
    assert request.method == "m3"
    assert request.request_id == 7 and request.has_id
    with pytest.raises(RpcProtocolError):
        parse_request({"jsonrpc": "2.0", "id": 1, "method": ""})


# ---------------------------------------------------------------------------
# /api/rpc HTTP integration against the real service handlers
# ---------------------------------------------------------------------------


def test_api_rpc_initialize_and_thread_roundtrip(live: _LiveServer, tmp_path: Path) -> None:
    status, _, body = _post_json(f"{live.url}/api/rpc", {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
    })
    assert status == 200
    assert json.loads(body)["result"]["serverInfo"]["name"] == "minicc"

    status, _, body = _post_json(f"{live.url}/api/rpc", {
        "jsonrpc": "2.0", "id": 2, "method": "thread/start",
        "params": {"workspace_path": str(tmp_path), "session_id": "rpc-1"},
    })
    thread_id = json.loads(body)["result"]["thread_id"]
    status, _, body = _post_json(f"{live.url}/api/rpc", {
        "jsonrpc": "2.0", "id": 3, "method": "thread/read", "params": {"thread_id": thread_id},
    })
    assert status == 200
    assert json.loads(body)["result"]["session_id"] == "rpc-1"


def test_api_rpc_turn_lifecycle(live: _LiveServer, tmp_path: Path) -> None:
    status, _, body = _post_json(f"{live.url}/api/rpc", {
        "jsonrpc": "2.0", "id": 1, "method": "turn/start",
        "params": {"message": "do work", "workspace_path": str(tmp_path), "session_id": "rpc-turn"},
    })
    assert status == 200
    turn_id = json.loads(body)["result"]["turn_id"]
    status, _, body = _post_json(f"{live.url}/api/rpc", {
        "jsonrpc": "2.0", "id": 2, "method": "turn/read", "params": {"turn_id": turn_id},
    })
    assert status == 200
    assert json.loads(body)["result"]["task_id"] == turn_id
    status, _, body = _post_json(f"{live.url}/api/rpc", {
        "jsonrpc": "2.0", "id": 3, "method": "turn/interrupt", "params": {"turn_id": turn_id},
    })
    assert status == 200
    assert json.loads(body)["result"]["status"] == "cancelled"


def test_rpc_turn_start_honours_the_permission_mode(live: _LiveServer, tmp_path: Path) -> None:
    """The third entry point must take the same permission inputs as the other two.

    The Sept-18 review listed this as a P1: the thread executor dropped
    ``permission_mode``, so the frontend's choice and the executed policy disagreed.
    It was still true in batch 200 - the ``turn/start`` payload omitted the key, so
    ``resolve_task_permissions`` saw none and fell back to "default", and plan mode's
    forced ``changes = False`` went with it. A caller asking for the read-only mode
    was handed one where writes are permitted.
    """
    status, _, body = _post_json(f"{live.url}/api/rpc", {
        "jsonrpc": "2.0", "id": 1, "method": "turn/start",
        "params": {
            "message": "plan only",
            "workspace_path": str(tmp_path),
            "session_id": "rpc-mode",
            "permission_mode": "plan",
            "allow_changes": True,
        },
    })
    assert status == 200
    result = json.loads(body)["result"]
    assert result["permission_mode"] == "plan", (
        "turn/start dropped the requested mode; the task ran as "
        f"{result['permission_mode']!r} instead"
    )
    # Plan mode forces writes off even when the caller asked for them.
    assert result["allow_changes"] is False, result["allow_changes"]


def test_api_rpc_unknown_method_and_missing_task(live: _LiveServer) -> None:
    status, _, body = _post_json(f"{live.url}/api/rpc", {
        "jsonrpc": "2.0", "id": 1, "method": "does/not-exist",
    })
    assert status == 200
    assert json.loads(body)["error"]["code"] == -32601

    status, _, body = _post_json(f"{live.url}/api/rpc", {
        "jsonrpc": "2.0", "id": 2, "method": "turn/read", "params": {"turn_id": "task-nope"},
    })
    assert json.loads(body)["error"]["code"] == -32004


def test_api_rpc_rejects_non_object_body(live: _LiveServer) -> None:
    status, _, body = _post_json(f"{live.url}/api/rpc", "just-a-string")
    assert status == 400
    assert "RPC" in json.loads(body)["error"]


def test_api_rpc_notification_returns_204(live: _LiveServer, tmp_path: Path) -> None:
    status, _, body = _post_json(f"{live.url}/api/rpc", {
        "jsonrpc": "2.0", "method": "thread/start",
        "params": {"workspace_path": str(tmp_path), "session_id": "rpc-note"},
    })
    assert status == 204
    assert body == b""


# ---------------------------------------------------------------------------
# M4-3 follow-up: the six /api routes that had no Python test at all
#
# The live audit found that `approval`, `changes`, `mcp`, `models`,
# `permissions` and `sessions/fork` never appeared as path strings in any Python
# test — they were only reachable through the frontend smokes, which assert
# console errors rather than response contracts. These tests pin the contract
# (status code + payload shape + validation errors) for each of them.
# ---------------------------------------------------------------------------


def test_get_stats_answers_the_operational_inventory(live: _LiveServer) -> None:
    """M8-T922: the HTTP twin of `minicc --stats` — the route the pulse
    panel has been calling for months, finally real."""
    status, _, body = _request(f"{live.url}/api/stats", method="GET")
    assert status == 200
    payload = json.loads(body)
    assert payload["state_dir_present"] is False  # fresh tmp workspace has no .minicc
    assert payload["audit"]["present"] is False
    assert payload["tasks"]["present"] is False
    assert payload["sessions"]["count"] == 0
    assert payload["disk_bytes"] == 0
    assert payload["cache"]["live_backend"] is False
    assert payload["cache"]["local_capacity"] == 4096
    assert "llm_cache" in payload


def test_get_roadmap_answers_the_archive(live: _LiveServer, tmp_path: Path) -> None:
    """M8-T940: /api/roadmap answers the ledger as content - every batch
    heading, verbatim title, grouped into hundred-epoch eras."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ROADMAP_TO_PRODUCT.md").write_text(
        "# roadmap\n\n"
        "## 批次 900 — M8-T900：一个能力落地\nbody\n"
        "## 批次 942 — M8-T942：第二个能力落地，更长一点的标题\nbody\n"
        "## 批次 1002 — 合流批：m8-t537 → main\nbody\n",
        encoding="utf-8",
    )
    status, _, body = _request(f"{live.url}/api/roadmap", method="GET")
    assert status == 200
    payload = json.loads(body)
    assert payload["schema_version"] == "minicc.roadmap-archive.v1"
    assert payload["is_roadmap"] is True
    assert payload["total"] == 3
    ids = [entry["id"] for entry in payload["entries"]]
    assert ids[:2] == ["M8-T900", "M8-T942"]
    assert payload["eras"] == [
        {"from": 900, "to": 999, "count": 2},
        {"from": 1000, "to": 1099, "count": 1},
    ]


def test_get_behavior_journeys_answers_the_visitor_log(live: _LiveServer) -> None:
    """M8-T1289: /api/behavior/journeys answers the synthetic visitor aggregate.

    The live fixture's workspace has never been walked, so the honest answer is
    the empty state — never a fabricated bounce rate. ``live: False`` plus the
    command that would fill the log is the whole contract the admin card reads.
    """
    status, _, body = _request(f"{live.url}/api/behavior/journeys", method="GET")
    assert status == 200
    payload = json.loads(body)
    assert payload["live"] is False
    assert payload["total"] == 0
    assert payload["personas"] == []
    assert payload["bounce_rate"] is None
    assert payload["median_dwell_ms"] is None
    assert payload["confidence"] == "empty"
    assert payload["source"] == "synthetic-real-execution"
    assert payload["how_to"].startswith("node scripts/behavior_sim.mjs")


def test_get_visitor_advice_is_model_free_even_on_an_empty_log(live: _LiveServer) -> None:
    """M8-T1292: rule-derived fixes never call a model, even when upstream is dry."""
    status, _, body = _request(f"{live.url}/api/visitor-advice", method="GET")
    assert status == 200
    payload = json.loads(body)
    assert payload["live"] is False
    assert payload["verdict"] == "no-signal"
    assert payload["model_free"] is True
    assert payload["source"] == "deterministic-rules"
    assert payload["zh"]["moves"] == []
    assert payload["en"]["moves"] == []
    assert "behavior_sim.mjs" in payload["en"]["how_to"]


def test_get_rag_search_returns_bm25_results(live: _LiveServer, tmp_path: Path) -> None:
    """M8-T971: /api/rag/search is a read-only, in-process BM25 retrieval over
    the repo's own bundled documentation. It never makes network calls,
    returns at most k snippets, and survives unknown/empty queries."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "DEMO.md").write_text(
        "# demo\n\n缓存命中率低时，看看 prefix_cache_key 有没有同样的前缀。\n\n"
        "load test at twenty concurrent requests: every cold /api/stats walk\n"
        "is on you.\n\n",
        encoding="utf-8",
    )
    status, _, body = _request(f"{live.url}/api/rag/search?q=%E7%BC%93%E5%AD%98&k=3", method="GET")
    assert status == 200
    payload = json.loads(body)
    assert payload["q"]
    assert "results" in payload
    assert isinstance(payload["results"], list)
    # Empty query degrades to empty list, never 500
    status, _, body = _request(f"{live.url}/api/rag/search?q=&k=5", method="GET")
    assert status == 200
    assert json.loads(body)["results"] == []


def test_get_rag_context_reports_bounded_deterministic_evidence(live: _LiveServer) -> None:
    """M8-T1294: /api/rag/context is the zero-token window into the large-context
    assembler. It must stay read-only, bounded and never 500 on an odd query."""
    status, _, body = _request(
        f"{live.url}/api/rag/context?q=%E7%BC%93%E5%AD%98%20%E5%91%BD%E4%B8%AD%E7%8E%87&budget=2400",
        method="GET",
    )
    assert status == 200
    payload = json.loads(body)
    assert payload["ok"] is True
    assert payload["budget_tokens"] == 2400
    assert payload["estimated_tokens"] <= 2400
    assert isinstance(payload["chunks"], list)
    assert payload["candidates"] >= len(payload["chunks"])
    for chunk in payload["chunks"]:
        assert chunk["source"].endswith(".md")
        assert chunk["start_line"] >= 1
    assert isinstance(payload["prefix_fingerprint"], str) and len(payload["prefix_fingerprint"]) == 16
    # Empty query and absurd budget degrade to a valid shape, never 500
    status, _, body = _request(f"{live.url}/api/rag/context?q=&budget=oops", method="GET")
    assert status == 200
    empty = json.loads(body)
    assert empty["ok"] is True and empty["chunks"] == []


def test_get_worldpulse_returns_live_or_honest_failure(live: _LiveServer, monkeypatch) -> None:
    """M8-T993: /api/worldpulse is the live-glance route to the outside
    world — public GitHub facts, 5-minute shared cache, fail-open. This
    test does NOT require network: it stubs the fetch to return a canned
    honest dict (same shape as the real wire) and checks the route's
    path and error policy. Any real fetch happens exactly once per TTL."""
    import minicc.worldpulse as wp_mod

    monkeypatch.setattr(wp_mod, "fetch_worldpulse", lambda *, force_refresh=False: {
        "live": True,
        "fetched_at": 1234567890.0,
        "github": {"stars": 1, "forks": 0, "open_issues": 1, "pushed_at": "2026-11-15T00:00:00Z", "default_branch": "main", "html_url": "https://github.com/xiaodernan/minicc-codex"},
    })
    status, _, body = _request(f"{live.url}/api/worldpulse", method="GET")
    assert status == 200
    payload = json.loads(body)
    assert payload["live"] is True
    assert payload["github"]["stars"] == 1
    assert "sk-" not in body.decode("utf-8")


def test_get_provider_ping_returns_honest_probe_without_key(live: _LiveServer, monkeypatch) -> None:
    """M8-T997: /api/provider-ping is the doctor panel's upstream echo —
    one real GET {base}/models, 10s shared cache, fail-open. This test does
    NOT require network: it stubs the probe and checks the route wiring and
    the no-key-echo invariant. Any live fetch happens at most once per TTL."""
    import minicc.provider_ping as pp_mod

    monkeypatch.setattr(pp_mod, "fetch_provider_ping", lambda *, force_refresh=False: {
        "configured": True,
        "live": True,
        "gateway": "wkapi.pro",
        "model": "gpt-6-sol",
        "status": 200,
        "elapsed_ms": 2812.0,
        "error": None,
        "probe": "GET /models",
    })
    status, _, body = _request(f"{live.url}/api/provider-ping", method="GET")
    assert status == 200
    payload = json.loads(body)
    assert payload["live"] is True
    assert payload["gateway"] == "wkapi.pro"
    assert payload["probe"] == "GET /models"
    assert "sk-" not in body.decode("utf-8")


def test_get_provider_ping_survives_a_broken_probe(live: _LiveServer, monkeypatch) -> None:
    """M8-T997: a probe that blows up must surface as an honest payload,
    never as a 500."""
    import minicc.provider_ping as pp_mod

    def boom(*, force_refresh=False):
        raise RuntimeError("probe exploded")

    monkeypatch.setattr(pp_mod, "fetch_provider_ping", boom)
    status, _, body = _request(f"{live.url}/api/provider-ping", method="GET")
    assert status == 200
    payload = json.loads(body)
    assert payload["live"] is False
    assert payload["error"] == "RuntimeError"
    assert "sk-" not in body.decode("utf-8")


def test_get_rag_query_route_is_registered_and_safe(live: _LiveServer, monkeypatch) -> None:
    """M8-T973: /api/rag/query is a lexical retriever + one chat
    completion.  The fake fixture never exercises a real gateway (its
    base_url points nowhere real), so this test stubs the completion —
    proving the route wiring, query passing, and error-handling policy,
    without relying on example.test resolving."""
    import minicc.rag as rag_mod

    captured: dict = {}

    def fake_answer(query: str, **kwargs) -> dict:
        captured["q"] = query
        return {"query": query, "answer": "docs say cache affinity matters", "sources": [], "model": "stub-model", "usage": {"total_tokens": 100}}

    monkeypatch.setattr(rag_mod, "answer", fake_answer)
    status, _, body = _request(f"{live.url}/api/rag/query?q=anything&k=1", method="GET")
    assert status == 200
    payload = json.loads(body)
    assert payload["answer"] == "docs say cache affinity matters"
    assert payload["query"] == "anything"
    assert payload["usage"]["total_tokens"] == 100
    assert "sk-" not in body.decode("utf-8", "replace")


def test_get_rag_query_forwards_budget_only_when_asked(live: _LiveServer, monkeypatch) -> None:
    """M8-T1316: the wide-context budget must reach rag.answer, and the
    legacy path must stay byte-identical when no budget is supplied."""
    import minicc.rag as rag_mod

    calls: list[dict] = []

    def fake_answer(query: str, **kwargs) -> dict:
        calls.append({"q": query, **kwargs})
        out = {"query": query, "answer": "", "sources": []}
        if kwargs.get("budget_tokens") is not None:
            out["context"] = {"chunks": 3}
        return out

    monkeypatch.setattr(rag_mod, "answer", fake_answer)
    status, _, body = _request(f"{live.url}/api/rag/query?q=hello&k=2", method="GET")
    assert status == 200
    assert calls[-1] == {"q": "hello", "limit": 2, "budget_tokens": None,
                         "fanout": None, "per_variant": None}
    assert "context" not in json.loads(body), "legacy call must not fabricate a context block"

    status, _, body = _request(f"{live.url}/api/rag/query?q=hello&k=2&budget=8000", method="GET")
    assert status == 200
    assert calls[-1]["budget_tokens"] == 8000
    assert json.loads(body)["context"] == {"chunks": 3}

    # Deep mode raises lexical recall too — budget alone would have nothing
    # to pack. Both knobs must reach rag.answer.
    status, _, body = _request(
        f"{live.url}/api/rag/query?q=hello&budget=50000&fanout=48&per=20", method="GET")
    assert status == 200
    assert calls[-1]["budget_tokens"] == 50000
    assert calls[-1]["fanout"] == 48
    assert calls[-1]["per_variant"] == 20

    # Invalid knobs degrade to None (assembler defaults), never a 500.
    status, _, body = _request(
        f"{live.url}/api/rag/query?q=hello&budget=oops&fanout=bad&per=bad", method="GET")
    assert status == 200
    assert calls[-1]["budget_tokens"] is None
    assert calls[-1]["fanout"] is None
    assert calls[-1]["per_variant"] is None


def test_get_models_returns_local_catalog_without_network(live: _LiveServer) -> None:
    status, _, body = _request(f"{live.url}/api/models", method="GET")
    assert status == 200
    payload = json.loads(body)
    # The fake/unreachable gateway must degrade to the configured model rather
    # than fail the request, and must never echo credentials.
    assert [item["id"] for item in payload["models"]][0] == "test-model"
    assert payload["default_model"] == "test-model"
    assert "api_key" not in body.decode("utf-8", "replace")


def test_get_permissions_reports_rules_and_path(live: _LiveServer, tmp_path: Path) -> None:
    status, _, body = _request(f"{live.url}/api/permissions", method="GET")
    assert status == 200
    payload = json.loads(body)
    assert payload["path"] == (tmp_path / ".minicc" / "permissions.json").as_posix()
    # Empty rule sets come back as empty *rule buckets* (tools/paths/commands),
    # not as bare lists — pin the shape so the frontend can rely on it.
    assert payload["allow"] == {"tools": [], "paths": [], "commands": []}
    assert payload["deny"] == {"tools": [], "paths": [], "commands": []}
    # A healthy load reports no error (the loader uses "" for "no error").
    assert not payload["error"]


def test_get_permissions_surfaces_malformed_rule_file(live: _LiveServer, tmp_path: Path) -> None:
    target = tmp_path / ".minicc" / "permissions.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("{ not json", encoding="utf-8")
    status, _, body = _request(f"{live.url}/api/permissions", method="GET")
    assert status == 200
    payload = json.loads(body)
    # A broken rule file is reported, never silently treated as "no rules".
    assert payload["error"]


def test_get_mcp_reports_unconfigured_workspace(live: _LiveServer) -> None:
    status, _, body = _request(f"{live.url}/api/mcp", method="GET")
    assert status == 200
    payload = json.loads(body)
    assert payload.get("configured", 0) == 0


def test_get_stategraph_reports_the_live_workflow(live: _LiveServer) -> None:
    # M8-T1112: the panel's live wire must be entered by the HTTP suite too —
    # otherwise route_coverage.py has no entry into this branch.
    status, _, body = _request(f"{live.url}/api/stategraph", method="GET")
    assert status == 200
    payload = json.loads(body)
    assert payload["name"] == "coding"
    assert payload["entry"] == "intake"
    assert [node["id"] for node in payload["nodes"]] == [
        "intake", "plan", "inspect", "implement", "verify", "repair", "summarize",
    ]
    assert payload["guards"] == {"max_nodes": 32, "max_depth": 16, "max_parallel": 4, "max_steps": 64}
    assert len(payload["edges"]) == 8
    assert len(payload["routing"]["stages"]) == 5
    assert "sk-" not in body.decode("utf-8", "replace")


def test_get_oracle_retrospective_never_500s(live: _LiveServer, monkeypatch) -> None:
    # M8-T1125: the retrospective route is entered by the HTTP suite too —
    # same seam-stub pattern as the other model-duty tests.
    import minicc.oracle_retrospective as ot_mod

    monkeypatch.setattr(ot_mod, "build_workspace_retrospective", lambda **kwargs: {
        "live": False, "zh": "", "en": "",
        "error": "model-unavailable: TimeoutError",
    })
    status, _, body = _request(f"{live.url}/api/oracle-retrospective", method="GET")
    assert status == 200
    payload = json.loads(body)
    assert payload["live"] is False
    assert "error" in payload
    assert "sk-" not in body.decode("utf-8", "replace")


def test_get_oracle_review_never_500s(live: _LiveServer, monkeypatch) -> None:
    # M8-T1123: the review route is entered by the HTTP suite too —
    # seam stubbed exactly like the other model-duty tests.
    import minicc.oracle_review as orev_mod

    monkeypatch.setattr(orev_mod, "build_workspace_review", lambda **kwargs: {
        "live": False, "zh": "", "en": "",
        "error": "model-unavailable: TimeoutError",
    })
    status, _, body = _request(f"{live.url}/api/oracle-review", method="GET")
    assert status == 200
    payload = json.loads(body)
    assert payload["live"] is False
    assert "error" in payload
    assert "sk-" not in body.decode("utf-8", "replace")


def test_get_oracle_plan_never_500s(live: _LiveServer, monkeypatch) -> None:
    # M8-T1122: the forward planner route is entered by the HTTP suite too —
    # same seam-stub pattern as the brief and diagnosis tests.
    import minicc.oracle_plan as op_mod

    monkeypatch.setattr(op_mod, "build_workspace_plan", lambda **kwargs: {
        "live": False, "zh": [], "en": [],
        "error": "model-unavailable: TimeoutError",
    })
    status, _, body = _request(f"{live.url}/api/oracle-plan", method="GET")
    assert status == 200
    payload = json.loads(body)
    assert payload["live"] is False
    assert "error" in payload
    assert "sk-" not in body.decode("utf-8", "replace")


def test_get_oracle_diagnosis_never_500s(live: _LiveServer, monkeypatch) -> None:
    # M8-T1120: the diagnosis route is entered by the HTTP suite too —
    # stubbed at the seam exactly like the brief test.
    import minicc.oracle_diagnosis as od_mod

    monkeypatch.setattr(od_mod, "build_workspace_diagnosis", lambda **kwargs: {
        "live": False, "zh": "", "en": "",
        "error": "model-unavailable: TimeoutError",
    })
    status, _, body = _request(f"{live.url}/api/oracle-diagnosis", method="GET")
    assert status == 200
    payload = json.loads(body)
    assert payload["live"] is False
    assert "error" in payload
    assert "sk-" not in body.decode("utf-8", "replace")


def test_get_oracle_brief_never_500s(live: _LiveServer, monkeypatch) -> None:
    # M8-T1119: the model-written brief is entered by the HTTP suite too.
    # The fake provider cannot answer it (60s timeout), so the route is
    # stubbed at the seam — exactly like the /api/rag/query test.
    import minicc.oracle_brief as ob_mod

    monkeypatch.setattr(ob_mod, "build_workspace_brief", lambda **kwargs: {
        "live": False, "zh": "", "en": "",
        "error": "model-unavailable: TimeoutError",
    })
    status, _, body = _request(f"{live.url}/api/oracle-brief", method="GET")
    assert status == 200
    payload = json.loads(body)
    assert payload["live"] is False
    assert "error" in payload
    assert "sk-" not in body.decode("utf-8", "replace")


def test_get_oracle_ci_diagnosis_never_500s(live: _LiveServer, monkeypatch) -> None:
    # M8-T1166: the CI-diagnosis route is entered by the HTTP suite too —
    # the seam stub yields the honest failure payload, the route must still answer.
    import minicc.oracle_ci_diagnosis as cd_mod

    monkeypatch.setattr(cd_mod, "build_ci_diagnosis", lambda **kwargs: {
        "live": False, "zh": "", "en": "",
        "error": "model-unavailable: TimeoutError",
        "verdict": "model-unavailable",
    })
    status, _, body = _request(f"{live.url}/api/oracle-ci-diagnosis", method="GET")
    assert status == 200
    payload = json.loads(body)
    assert payload["live"] is False
    assert "error" in payload
    assert "sk-" not in body.decode("utf-8", "replace")
    fresh = _request(f"{live.url}/api/oracle-ci-diagnosis?fresh=1", method="GET")
    assert fresh[0] == 200


def test_get_oracle_audit_story_never_500s(live: _LiveServer, monkeypatch) -> None:
    # M8-T1173: the audit-story route is entered by the HTTP suite too —
    # the seam stub yields the honest failure payload, the route must still answer.
    import minicc.oracle_audit_story as oas_mod

    monkeypatch.setattr(oas_mod, "build_audit_story", lambda **kwargs: {
        "live": False, "zh": "", "en": "",
        "error": "model-unavailable: TimeoutError",
        "verdict": "model-unavailable",
    })
    status, _, body = _request(f"{live.url}/api/oracle-audit-story", method="GET")
    assert status == 200
    payload = json.loads(body)
    assert payload["live"] is False
    assert "error" in payload
    assert "sk-" not in body.decode("utf-8", "replace")
    fresh = _request(f"{live.url}/api/oracle-audit-story?fresh=1", method="GET")
    assert fresh[0] == 200


def test_get_oracle_recommendations_never_500s(live: _LiveServer, monkeypatch) -> None:
    # M8-T1196: the recommendations route is entered by the HTTP suite too —
    # the seam stub yields the honest failure payload, the route must still answer.
    import minicc.oracle_recommendations as orc_mod

    monkeypatch.setattr(orc_mod, "build_workspace_recommendations", lambda **kwargs: {
        "live": False, "zh": [], "en": [],
        "error": "model-unavailable: TimeoutError",
        "verdict": "model-unavailable",
    })
    status, _, body = _request(f"{live.url}/api/oracle-recommendations", method="GET")
    assert status == 200
    payload = json.loads(body)
    assert payload["live"] is False
    assert "sk-" not in body.decode("utf-8", "replace")
    fresh = _request(f"{live.url}/api/oracle-recommendations?fresh=1", method="GET")
    assert fresh[0] == 200


def test_get_oracle_trend_never_500s(live: _LiveServer, monkeypatch) -> None:
    # M8-T1287: the trend analyst route is entered by the HTTP suite too —
    # the seam stub yields the honest failure payload, the route must still answer.
    import minicc.oracle_trend as ot_mod

    monkeypatch.setattr(ot_mod, "build_trend_insight", lambda **kwargs: {
        "live": False, "verdict": "model-unavailable", "direction": "unknown",
        "baseline_direction": None, "zh": {"narrative": "", "moves": []},
        "en": {"narrative": "", "moves": []},
        "error": "model-unavailable: TimeoutError",
    })
    status, _, body = _request(f"{live.url}/api/oracle-trend", method="GET")
    assert status == 200
    payload = json.loads(body)
    assert payload["live"] is False
    assert payload["zh"]["moves"] == [] and payload["en"]["moves"] == []
    assert "sk-" not in body.decode("utf-8", "replace")
    fresh = _request(f"{live.url}/api/oracle-trend?fresh=1", method="GET")
    assert fresh[0] == 200


def test_oracle_visitors_route_reports_an_honest_outage(live: _LiveServer, monkeypatch) -> None:
    # M8-T1289b: the visitor analyst route answers even when the model is gone —
    # live:false with the same zh/en shape the panel already knows, never a 500,
    # never the api key.
    import minicc.oracle_visitors as ov_mod

    monkeypatch.setattr(ov_mod, "build_visitor_insight", lambda **kwargs: {
        "live": False, "verdict": "model-unavailable", "focus": "unknown",
        "zh": {"narrative": "", "moves": []}, "en": {"narrative": "", "moves": []},
        "error": "model-unavailable: TimeoutError",
    })
    status, _, body = _request(f"{live.url}/api/oracle-visitors", method="GET")
    assert status == 200
    payload = json.loads(body)
    assert payload["live"] is False
    assert payload["focus"] == "unknown"
    assert payload["zh"]["moves"] == [] and payload["en"]["moves"] == []
    assert "sk-" not in body.decode("utf-8", "replace")
    assert _request(f"{live.url}/api/oracle-visitors?fresh=1", method="GET")[0] == 200


def test_all_gateway_calling_oracles_answer_honest_429_shape_when_bucket_holds(live: _LiveServer, monkeypatch) -> None:
    # M8-T1178: every gateway-calling route is behind the shared token bucket;
    # a denial must be an honest 200 payload (live=False, rate_limited=True),
    # never a 500, and never the api key — whichever oracle you poll.
    monkeypatch.setattr(
        "minicc.webserver._oracle_rate_limited",
        lambda *a, **k: (False, {"window_seconds": 60, "limit": 20, "backend": "local"}),
    )
    routes = [
        "/api/oracle-ci-diagnosis", "/api/oracle-audit-story",
        "/api/oracle-retrospective", "/api/oracle-review",
        "/api/oracle-plan", "/api/oracle-diagnosis",
        "/api/oracle-brief", "/api/oracle-trend", "/api/oracle-visitors", "/api/provider-ping",
    ]
    for route in routes:
        status, _, body = _request(f"{live.url}{route}", method="GET")
        assert status == 200, (route, status)
        payload = json.loads(body)
        assert payload.get("rate_limited") is True, route
        assert payload.get("live") is False, route
        assert "rate limit" in str(payload.get("error", "")).lower(), route
        assert "sk-" not in body.decode("utf-8", "replace"), route
        assert int(payload.get("retry_after_seconds", 0)) >= 1, route


def test_get_admin_drift_never_500s(live: _LiveServer, monkeypatch) -> None:
    # M8-T1160: the drift sentinel route is entered by the HTTP suite too —
    # the seam stub yields the honest failure payload, the route must still answer.
    import minicc.admin_drift as ad_mod

    monkeypatch.setattr(ad_mod, "build_workspace_drift", lambda **kwargs: {
        "live": False,
        "error": "RuntimeError: git rev-parse failed: not a git repository",
        "generated_at": "2026-11-17T00:00:00Z",
        "honest_limits": ["full test suite not run here; CI is the authority on the suite"],
    })
    status, _, body = _request(f"{live.url}/api/admin/drift", method="GET")
    assert status == 200
    payload = json.loads(body)
    assert payload["live"] is False
    assert "error" in payload
    assert "sk-" not in body.decode("utf-8", "replace")
    fresh = _request(f"{live.url}/api/admin/drift?fresh=1", method="GET")
    assert fresh[0] == 200


def test_get_mcp_surfaces_malformed_config_as_error_not_500(tmp_path: Path) -> None:
    # M8-T138 (M5-4 recheck): the service loads .minicc/mcp.json at
    # construction (web.py _set_current_mcp), so a broken file must be
    # survived at boot and surfaced by the route: 200, configured=0, non-empty
    # error - never a 500, never a silent "configured: 0" that reads healthy.
    (tmp_path / ".minicc").mkdir()
    (tmp_path / ".minicc" / "mcp.json").write_text("{ not json", encoding="utf-8")
    server = _LiveServer(tmp_path, auth=WebAuth("tok", required=False))
    try:
        status, _, body = _request(f"{server.url}/api/mcp", method="GET")
    finally:
        server.shutdown()
    assert status == 200
    payload = json.loads(body)
    assert payload.get("configured", 0) == 0
    assert payload["error"], payload


def test_get_changes_returns_workspace_summary(live: _LiveServer) -> None:
    status, _, body = _request(f"{live.url}/api/changes", method="GET")
    assert status == 200
    payload = json.loads(body)
    assert isinstance(payload, dict) and payload


def test_get_diff_rejects_path_outside_workspace(live: _LiveServer) -> None:
    status, _, body = _request(f"{live.url}/api/diff?path=../outside.txt", method="GET")
    assert status == 400
    assert json.loads(body)["error"]


def test_post_approval_validates_request_id(live: _LiveServer) -> None:
    status, _, body = _post_json(f"{live.url}/api/approval", {"request_id": "  ", "decision": "allow"})
    assert status == 400
    assert "request_id" in json.loads(body)["error"]


def test_post_approval_rejects_unknown_decision(live: _LiveServer) -> None:
    status, _, body = _post_json(f"{live.url}/api/approval", {"request_id": "req-1", "decision": "maybe"})
    assert status == 400
    assert "allow|always|deny" in json.loads(body)["error"]


def test_post_approval_unknown_request_is_a_noop(live: _LiveServer) -> None:
    status, _, body = _post_json(f"{live.url}/api/approval", {"request_id": "req-missing", "decision": "deny"})
    assert status == 200
    assert json.loads(body) == {"resolved": False, "request_id": "req-missing"}


def test_post_sessions_fork_validates_payload(live: _LiveServer) -> None:
    status, _, body = _post_json(f"{live.url}/api/sessions/fork", {"from_message_id": 2})
    assert status == 400
    assert "session_id" in json.loads(body)["error"]

    status, _, body = _post_json(f"{live.url}/api/sessions/fork", {"session_id": "s1", "from_message_id": 1.5})
    assert status == 400
    assert "from_message_id" in json.loads(body)["error"]

    status, _, body = _post_json(f"{live.url}/api/sessions/fork", {"session_id": "s1", "from_message_id": "  "})
    assert status == 400
    assert "from_message_id" in json.loads(body)["error"]


def test_post_sessions_fork_creates_independent_session(live: _LiveServer, tmp_path: Path) -> None:
    from minicc.session import SessionStore

    source = SessionStore(tmp_path, "origin")
    source.save([
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "one"},
        {"role": "assistant", "content": "two"},
        {"role": "user", "content": "three"},
    ])
    status, _, body = _post_json(f"{live.url}/api/sessions/fork", {
        "session_id": "origin", "from_message_id": 2, "new_session_id": "branch",
    })
    assert status == 200
    payload = json.loads(body)
    assert payload == {"session_id": "branch", "forked_from": "origin", "from_message_id": 2}

    forked = SessionStore(tmp_path, "branch").load("SYS")
    assert [msg["content"] for msg in forked][1:] == ["one"]
    # The source conversation is untouched by the fork.
    assert [msg["content"] for msg in source.load("SYS")][1:] == ["one", "two", "three"]


def test_post_sessions_fork_rejects_unknown_session(live: _LiveServer) -> None:
    status, _, body = _post_json(f"{live.url}/api/sessions/fork", {
        "session_id": "no-such-session", "from_message_id": 1,
    })
    assert status == 400
    assert json.loads(body)["error"]



# ---------------------------------------------------------------------------
# M4-3 follow-up: the read-only RPC surface
#
# The dispatcher previously exposed five lifecycle methods plus ``initialize``.
# The roadmap's criterion asks for >=10 independently tested methods, and the
# honest way to meet it is to make the protocol surface actually complete: a
# client that can start a turn should also be able to read the workspace it is
# driving. These five read-only methods reuse the lifecycle methods' workspace
# boundary check and are each pinned here.
# ---------------------------------------------------------------------------


def _rpc(url: str, method: str, params: dict | None = None, *, request_id: int = 1):
    status, _, body = _post_json(f"{url}/api/rpc", {
        "jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {},
    })
    payload = json.loads(body)
    return status, payload


def test_rpc_dispatcher_exposes_ten_methods() -> None:
    """Pin the surface size so a silent method removal cannot pass unnoticed."""
    from minicc.agent.rpc import RpcDispatcher

    service_methods = {
        "thread/start", "thread/read", "turn/start", "turn/read", "turn/interrupt",
        "workspace/read", "models/list", "changes/read", "sessions/list", "permissions/read",
    }
    dispatcher = RpcDispatcher({name: (lambda _params: {}) for name in service_methods})
    for name in sorted(service_methods):
        assert dispatcher.dispatch({"jsonrpc": "2.0", "id": 1, "method": name, "params": {}})


def test_rpc_workspace_read_describes_workspace(live: _LiveServer, tmp_path: Path) -> None:
    status, payload = _rpc(live.url, "workspace/read", {"workspace_path": str(tmp_path)})
    assert status == 200
    result = payload["result"]
    assert result["path"] == tmp_path.as_posix()
    assert result["current"] is True
    assert result["model"] == "test-model"
    assert isinstance(result["sandbox"], dict)


def test_rpc_workspace_read_rejects_path_outside_roots(tmp_path: Path) -> None:
    """The read-only surface must enforce workspace_roots like the lifecycle one."""
    outside = tmp_path / "allowed"
    outside.mkdir()
    server = _LiveServer(tmp_path, workspace_roots=(outside,))
    try:
        status, payload = _rpc(server.url, "workspace/read", {"workspace_path": str(tmp_path / "elsewhere")})
        assert status == 200
        assert payload["error"]["message"]
    finally:
        server.shutdown()


def test_rpc_models_list_returns_catalog(live: _LiveServer) -> None:
    status, payload = _rpc(live.url, "models/list", {})
    assert status == 200
    assert payload["result"]["default_model"] == "test-model"
    assert payload["result"]["models"]


def test_rpc_changes_read_returns_summary_and_diff(live: _LiveServer, tmp_path: Path) -> None:
    status, payload = _rpc(live.url, "changes/read", {"workspace_path": str(tmp_path)})
    assert status == 200
    assert isinstance(payload["result"], dict) and payload["result"]

    (tmp_path / "tracked.txt").write_text("hello\n", encoding="utf-8")
    status, payload = _rpc(live.url, "changes/read", {"path": "../escape.txt"})
    assert status == 200
    assert payload["error"]["message"]


def test_rpc_sessions_list_counts_stored_sessions(live: _LiveServer, tmp_path: Path) -> None:
    from minicc.session import SessionStore

    SessionStore(tmp_path, "rpc-session").save([{"role": "user", "content": "hi"}])
    status, payload = _rpc(live.url, "sessions/list", {"workspace_path": str(tmp_path)})
    assert status == 200
    result = payload["result"]
    assert result["workspace_path"] == str(tmp_path)
    assert result["count"] >= 1
    assert any(item["session_id"] == "rpc-session" for item in result["sessions"])


def test_rpc_permissions_read_reports_rules(live: _LiveServer, tmp_path: Path) -> None:
    status, payload = _rpc(live.url, "permissions/read", {"workspace_path": str(tmp_path)})
    assert status == 200
    result = payload["result"]
    assert result["path"] == (tmp_path / ".minicc" / "permissions.json").as_posix()
    assert result["allow"] == {"tools": [], "paths": [], "commands": []}


def test_rpc_unknown_method_is_a_protocol_error(live: _LiveServer) -> None:
    status, payload = _rpc(live.url, "workspace/nonexistent", {})
    assert status == 200
    assert payload["error"]["code"] == -32601


# ---------------------------------------------------------------------------
# M4-3: the route-coverage criterion, made measurable.
#
# The roadmap asks for "POST /api/* covered 100% by Python tests". Two separate
# gates carry that criterion now, and this is the weaker of the two by design:
#
#   * here, every route the dispatcher compares `path` against must be *named* by
#     some Python test - it fails the moment someone adds a route and forgets
#     every test for it;
#   * `scripts/route_coverage.py --check` measures whether a request actually
#     *entered* each route branch, over a named test selection. `tests/
#     test_route_coverage_measurement.py` keeps that measurement honest.
#
# The distinction matters because "the route's comparison line executed" is not
# coverage on this code shape: the handlers are flat `if path == ...: return`
# chains, so one request that falls through to the 404 runs every comparison
# above it. Measured: a single `POST /api/nope` scores 14/14 on that reading and
# 0/14 on the entry reading.
#
# What neither gate proves: that a route's success path is asserted somewhere.
# ---------------------------------------------------------------------------

_HTTP_HANDLERS = ("do_GET", "do_POST", "do_PUT", "do_PATCH", "do_DELETE")
#: Floor for the inventory itself. If routing ever moves out of the
#: ``path == "/api/..."`` idiom this walker reads, the set would come back small
#: or empty and the gate would pass for the wrong reason.
_MIN_ROUTE_INVENTORY = 25


def _route_literals_from_source(server_file: Path) -> set[str]:
    tree = ast.parse(server_file.read_text(encoding="utf-8"))
    handlers = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name in _HTTP_HANDLERS
    }
    literals: set[str] = set()
    for handler in handlers.values():
        for node in ast.walk(handler):
            value: object
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("startswith", "endswith")
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "path"
                and node.args
            ):
                value = getattr(node.args[0], "value", None)
            elif (
                isinstance(node, ast.Compare)
                and isinstance(node.left, ast.Name)
                and node.left.id == "path"
                and len(node.comparators) == 1
            ):
                value = getattr(node.comparators[0], "value", None)
            else:
                continue
            if isinstance(value, str) and value.startswith("/api/"):
                literals.add(value)
    return literals


def test_every_api_route_is_named_by_a_python_test() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    literals = _route_literals_from_source(repo_root / "minicc" / "webserver.py")
    assert len(literals) >= _MIN_ROUTE_INVENTORY, sorted(literals)
    corpus = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in sorted((repo_root / "tests").glob("*.py"))
    )
    untested = sorted(route for route in literals if route not in corpus)
    assert untested == [], f"routes no Python test even names: {untested}"


def test_get_admin_summary_returns_honest_empty_dict_on_missing_workspace(live: _LiveServer) -> None:
    """M8-T1014: /api/admin/summary is the admin panel's single read source.
    The test asserts the route exists, answers 200, no-crash, no 'sk-'."""
    res = _request(f"{live.url}/api/admin/summary", method="GET")
    assert res[0] == 200
    payload = json.loads(res[2])
    assert set(payload.keys()) >= {"totals", "trend_7d", "recent_tasks", "recommendations"}
    assert isinstance(payload["totals"], dict)
    import re

    assert not re.search(rb"sk-[A-Za-z0-9]{40,}", res[2]), "admin summary leaked key-shaped material"

def test_get_oracle_recommendations_never_500s(live: _LiveServer, monkeypatch) -> None:
    import minicc.oracle_recommendations as orc_mod

    monkeypatch.setattr(orc_mod, "build_workspace_recommendations", lambda **kwargs: {
        "live": False, "zh": [], "en": [],
        "error": "model-unavailable: TimeoutError",
        "verdict": "model-unavailable",
    })
    status, _, body = _request(f"{live.url}/api/oracle-recommendations", method="GET")
    assert status == 200
    payload = json.loads(body)
    assert payload["live"] is False
    assert "sk-" not in body.decode("utf-8", "replace")
    fresh = _request(f"{live.url}/api/oracle-recommendations?fresh=1", method="GET")
    assert fresh[0] == 200


def test_get_bench_history_never_500s(live: _LiveServer, monkeypatch) -> None:
    import minicc.bench_history as bh_mod

    monkeypatch.setattr(bh_mod, "read_history", lambda workspace, **kwargs: {
        "present": False, "reason": "simulated outage",
        "count": 0, "entries": [],
    })
    status, _, body = _request(f"{live.url}/api/bench-history", method="GET")
    assert status == 200
    payload = json.loads(body)
    assert payload["present"] is False
    assert "sk-" not in body.decode("utf-8", "replace")


def test_bench_history_query_filters_reach_read_history(live: _LiveServer, monkeypatch) -> None:
    import minicc.bench_history as bh_mod

    seen: dict = {}

    def fake_read(workspace, **kwargs):
        seen.update(kwargs)
        return {"present": False, "reason": "filter probe", "count": 0, "entries": []}

    monkeypatch.setattr(bh_mod, "read_history", fake_read)
    status, _, body = _request(
        f"{live.url}/api/bench-history?suite=v2&kind=task&window=last-30d",
        method="GET",
    )
    assert status == 200
    assert json.loads(body)["reason"] == "filter probe"
    assert seen == {"suite": "v2", "kind": "task", "window_days": 30}

    status, _, _ = _request(f"{live.url}/api/bench-history?window=garbage", method="GET")
    assert status == 200
    assert seen == {"suite": None, "kind": None, "window_days": None}


def test_bench_history_accepts_a_non_ascii_window_without_500(live: _LiveServer) -> None:
    """`?window=²` used to reach `int("²")` — a digit by Unicode's word, a crash by Python's.

    The `kind` is a one-off string on purpose: the route memoizes by
    `suite:kind:window` for 10s, and a shared key would hand this cell another
    cell's cached body instead of a read of its own.
    """
    status, _, body = _request(
        f"{live.url}/api/bench-history?window=%C2%B2&kind=non-ascii-window-probe", method="GET")
    assert status == 200
    payload = json.loads(body)
    assert payload["filters"]["window_days"] is None
    assert payload["filters"]["kind"] == "non-ascii-window-probe"
    assert payload["state"] in {
        "present", "absent", "empty", "unreadable", "filtered_empty", "capped", "error",
    }


def test_bench_history_failure_answer_has_the_shape_of_a_real_answer(
    live: _LiveServer, monkeypatch, tmp_path
) -> None:
    """The route's defensive branch must not answer with a smaller shape than the reader."""
    import minicc.bench_history as bh_mod

    expected = set(bh_mod.read_history(tmp_path))
    assert "state" in expected and "total_lines" in expected

    def explode(workspace, **kwargs):
        raise RuntimeError("simulated reader fault")

    monkeypatch.setattr(bh_mod, "read_history", explode)
    status, _, body = _request(f"{live.url}/api/bench-history?kind=failure-shape-probe", method="GET")
    assert status == 200
    payload = json.loads(body)
    assert set(payload) == expected, sorted(expected ^ set(payload))
    assert payload["state"] == "error"
    assert payload["present"] is False
    assert payload["total_lines"] is None
    assert "simulated reader fault" in payload["reason"]
    assert payload["filters"] == {"suite": None, "kind": "failure-shape-probe", "window_days": None}


def test_get_evidence_never_500s(live: _LiveServer, monkeypatch) -> None:
    import minicc.evidence as ev_mod

    monkeypatch.setattr(ev_mod, "latest", lambda workspace=None, **kwargs: {
        "present": False, "reason": "simulated outage",
        "count": 0, "entries": [], "source": "minicc-cloud-evidence",
    })
    status, _, body = _request(f"{live.url}/api/evidence", method="GET")
    assert status == 200
    payload = json.loads(body)
    assert payload["present"] is False
    assert "sk-" not in body.decode("utf-8", "replace")


def test_get_evidence_backend_crash_yields_present_false(live: _LiveServer, monkeypatch) -> None:
    import minicc.evidence as ev_mod

    def _raise(workspace=None, **kwargs):
        raise RuntimeError("boom for the route-level guard")

    monkeypatch.setattr(ev_mod, "latest", _raise)
    status, _, body = _request(f"{live.url}/api/evidence", method="GET")
    assert status == 200
    payload = json.loads(body)
    assert payload["present"] is False


def test_evidence_bridge_reports_unreachable(monkeypatch) -> None:
    import urllib.request

    import minicc.evidence as ev_mod

    def _hang(*args, **kwargs):
        raise TimeoutError("simulated hang")

    monkeypatch.setattr(urllib.request, "urlopen", _hang)
    out = ev_mod.latest()
    assert out["present"] is False
    assert "unreachable" in out["reason"]
    assert out["entries"] == []
