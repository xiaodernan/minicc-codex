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
        deadline = time.monotonic() + 10.0
        while True:
            if self.error is not None or not self.thread.is_alive():
                raise AssertionError(
                    f"the test HTTP server thread {self.thread.name!r} died before serving "
                    f"{self.url}; it raised: {self.error!r}"
                )
            try:
                status, _, _ = _request(f"{self.url}/api/health", method="GET")
            except OSError:
                status = -1
            if status == 200:
                return
            if time.monotonic() >= deadline:
                raise AssertionError(
                    f"the test HTTP server at {self.url} never answered /api/health within "
                    f"10s; thread alive={self.thread.is_alive()}, its exception={self.error!r}"
                )
            time.sleep(0.02)

    def _serve(self, **kwargs) -> None:
        try:
            self.server.serve_forever(**kwargs)
        except BaseException as exc:  # noqa: BLE001 - reported by the constructor
            self.error = exc

    def shutdown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.service.shutdown()


def _request(url: str, *, method: str, body: bytes | None = None, headers: dict[str, str] | None = None):
    request = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def _post_json(url: str, payload, headers: dict[str, str] | None = None):
    body = json.dumps(payload).encode("utf-8") if payload is not None else b""
    merged = {"Content-Type": "application/json", **(headers or {})}
    return _request(url, method="POST", body=body, headers=merged)


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
            status, _, body = _post_json(f"{live.url}/api/tasks", {
                "message": f"task {index}", "session_id": f"conc-{index}",
                "workspace_path": str(tmp_path), "_defer_schedule": True,
            })
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

