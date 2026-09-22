"""M4-T3's criterion asks for a number; this measures it by driving every route.

Two earlier attempts at this criterion failed in opposite directions:

* the first matched route strings against test sources, and reported 100 % —
  because `route in literal or literal in route` is satisfied by any pair
  sharing a prefix, and would even be satisfied by the empty string;
* tightening that to "a literal request call naming the route" reported 17 %,
  because six test modules build their paths with f-strings, which static
  matching cannot resolve.

Neither is coverage. So this module enumerates the route table from the
dispatcher itself (AST over ``webserver.py``, with floors so an empty
inventory can never pass) and then **issues one real request per route**
against a live server, asserting the universal response contract: an endpoint
either answers, or refuses with a structured body — never an unhandled 500.
"""

from __future__ import annotations

import ast
import json
import re
import threading
import types
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from minicc.task_store import TaskStore
from minicc.web import AgentService, MiniccHTTPServer
from minicc.webauth import WebAuth

REPO_ROOT = Path(__file__).resolve().parent.parent
WEBSERVER = REPO_ROOT / "minicc" / "webserver.py"

#: Anti-vacuity floors: the scanner must find a route table of real size.
_MIN_GET_ROUTES = 15
_MIN_POST_ROUTES = 10

#: A failure code is a stable identifier, not prose: lowercase snake_case, or a
#: JSON-RPC numeric code. This deliberately does *not* check membership in a
#: harvested vocabulary — the first attempt scanned the product for
#: ``"code": "..."`` literals and collected *event* codes instead of HTTP
#: response codes, which sent 11 healthy routes to the wall. A vocabulary read
#: from the wrong syntactic pattern is exactly as misleading as a hand-copied
#: one, so the rule here is only the shape a code must have.
_CODE_SHAPE = re.compile(r"^[a-z][a-z0-9_]{2,40}$")


def _route_table() -> dict[str, list[str]]:
    """Every exact ``/api/...`` path compared against ``path`` in each handler."""
    tree = ast.parse(WEBSERVER.read_text(encoding="utf-8"))
    verbs = {"do_GET": "GET", "do_POST": "POST"}
    routes: dict[str, set[str]] = {"GET": set(), "POST": set()}
    for fn in (node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)):
        verb = verbs.get(fn.name)
        if verb is None:
            continue
        for node in ast.walk(fn):
            if not (isinstance(node, ast.Compare) and isinstance(node.left, ast.Name) and node.left.id == "path"):
                continue
            for comparator in node.comparators:
                if (
                    isinstance(comparator, ast.Constant)
                    and isinstance(comparator.value, str)
                    and comparator.value.startswith("/api/")
                ):
                    routes[verb].add(comparator.value)
    return {verb: sorted(paths) for verb, paths in routes.items()}


def _config(workspace: Path) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        yolo=False,
        max_concurrent_tasks=2,
        sandbox_mode="host",
        sandbox_image="python:3.11-slim",
        base_url="https://example.test/v1",
        api_key="Zx9q-not-a-real-key",
        model="test-model",
        timeout=10,
        tool_mode="auto",
        reasoning_effort="high",
        max_turns=4,
        compact_threshold=300_000,
        context_window_tokens=300_000,
    )


class _Live:
    def __init__(self, workspace: Path) -> None:
        self.service = AgentService(
            workspace, _config(workspace), task_store=TaskStore(workspace / "tasks.sqlite3")
        )
        self.server = MiniccHTTPServer(("127.0.0.1", 0), self.service, auth=WebAuth("tok", required=False))
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
        )
        self.thread.start()
        self.origin = f"http://127.0.0.1:{self.server.server_address[1]}"

    def call(self, method: str, path: str) -> tuple[int, Any]:
        body = b"{}" if method == "POST" else None
        headers = {"Content-Type": "application/json"} if method == "POST" else {}
        request = urllib.request.Request(
            self.origin + urllib.parse.quote(path), data=body, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, _decode(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, _decode(exc.read())
        except OSError as exc:  # a route that kills the connection is a defect too
            pytest.fail(f"{method} {path} never answered: {exc}")

    def shutdown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.service.shutdown()


def _decode(raw: bytes) -> Any:
    text = raw.decode("utf-8", "replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def assert_answered(label: str, status: int, payload: Any) -> None:
    """The universal response contract: no unhandled server error, and refusals
    carry a stable ``code`` so clients never have to parse Chinese prose."""
    assert status < 500, f"{label} -> {status}: {payload!r}"
    if status < 400:
        return
    assert isinstance(payload, dict), f"{label} -> {status} answered without a JSON body: {payload!r}"
    # JSON-RPC routes report ``error.code``; HTTP routes report ``code``.
    error = payload.get("error")
    code = str(payload.get("code") or (error.get("code", "") if isinstance(error, dict) else ""))
    if not code and isinstance(error, dict):
        # JSON-RPC answers with a numeric error.code, which is stable by spec.
        code = str(error.get("code", ""))
    assert code, f"{label} -> {status} carried no failure code: {payload!r}"
    assert _CODE_SHAPE.match(code) or code.lstrip("-").isdigit(), (
        f"{label} -> {status} reported {code!r}, which is not a stable code: {payload!r}"
    )


def test_the_route_inventory_is_actually_a_route_inventory() -> None:
    routes = _route_table()
    assert len(routes["GET"]) >= _MIN_GET_ROUTES, routes
    assert len(routes["POST"]) >= _MIN_POST_ROUTES, routes
    # An inventory that silently lost the chat/task routes would make every
    # later per-route assertion pass by covering nothing.
    assert {"/api/chat", "/api/tasks", "/api/tasks/batch"} <= set(routes["POST"]), routes["POST"]
    assert "/api/metrics" in routes["GET"], routes["GET"]


def test_every_get_route_answers_or_refuses_with_a_code(tmp_path: Path) -> None:
    live = _Live(tmp_path)
    try:
        routes = _route_table()["GET"]
        probed = 0
        for path in routes:
            status, payload = live.call("GET", path)
            assert_answered(f"GET {path}", status, payload)
            probed += 1
        assert probed == len(routes)
    finally:
        live.shutdown()


def test_every_post_route_answers_or_refuses_with_a_code(tmp_path: Path) -> None:
    """Each POST route is driven with an empty JSON object on purpose.

    `{}` is the minimal body that must never crash a handler: routes that need
    a message, a task id or a session id have to *reject* it, not raise.
    """
    live = _Live(tmp_path)
    try:
        routes = _route_table()["POST"]
        probed = 0
        for path in routes:
            status, payload = live.call("POST", path)
            assert_answered(f"POST {path}", status, payload)
            probed += 1
        assert probed == len(routes)
    finally:
        live.shutdown()


def test_the_inventory_reports_the_criterion_s_number(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """M4-T3 asks "how much of the surface is covered"; print the honest ratio.

    The number is reported by driving every enumerated route once, so it is
    "routes that answer to a well-formed request", not a substring guess.
    """
    live = _Live(tmp_path)
    try:
        routes = _route_table()
        tally = {"GET": [0, 0], "POST": [0, 0]}
        for verb, paths in routes.items():
            for path in paths:
                status, payload = live.call(verb, path)
                tally[verb][1] += 1
                try:
                    assert_answered(f"{verb} {path}", status, payload)
                    tally[verb][0] += 1
                except AssertionError:
                    pass
        result = {
            verb: {"answered": ok, "total": total, "percent": round(100.0 * ok / total, 1)}
            for verb, (ok, total) in tally.items()
            if total
        }
        print("MINICC_ROUTE_COVERAGE " + json.dumps(result, ensure_ascii=False))
        # Every route must at least be reachable; a lower number here means the
        # two per-verb gates above are red for a reason.
        assert all(item["percent"] == 100.0 for item in result.values()), result
    finally:
        live.shutdown()
