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
import time
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

#: Routes dispatched by prefix/``endswith`` and carrying a task id. The AST scan
#: for ``path == "..."`` cannot see them, so they are declared here: the
#: inventory keeps them (floors + named-route assertions still bite) and
#: :func:`_probe_dynamic_routes` drives each one with a real id.
_DYNAMIC_ROUTES: dict[str, list[str]] = {
    "GET": ["/api/tasks/{task_id}", "/api/tasks/{task_id}/events"],
    "POST": ["/api/tasks/{task_id}/resume", "/api/tasks/{task_id}/cancel"],
}

#: A template placeholder the generic per-route loops must not send literally.
_TEMPLATE = "{task_id}"


def _route_table() -> dict[str, list[str]]:
    """Every exact ``/api/...`` path compared against ``path`` in each handler.

    Exact paths are enumerated from the dispatcher's own AST. Dynamic routes
    (dispatched by ``path.startswith``/``path.endswith`` and carrying a task id)
    are merged in from :data:`_DYNAMIC_ROUTES`, because no scan of ``path ==
    "..."`` can ever see them — M8-T32's 100 % measured exactly that set and
    nothing more.
    """
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
    for verb, paths in _DYNAMIC_ROUTES.items():
        routes[verb].update(paths)
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

    def _target(self, path: str) -> str:
        """Quote the path but keep a query string intact.

        ``quote(path)`` would percent-encode the ``?`` of ``.../events?after=0``,
        which the server then reads as part of the task id — the probe has to
        build the URL from its parts, not quote the whole string.
        """
        parsed = urllib.parse.urlsplit(path)
        target = self.origin + urllib.parse.quote(parsed.path)
        return f"{target}?{parsed.query}" if parsed.query else target

    def call(self, method: str, path: str, body: Any = None) -> tuple[int, Any]:
        if body is None:
            data = b"{}" if method == "POST" else None
        else:
            data = json.dumps(body).encode("utf-8")
        headers = {"Content-Type": "application/json"} if method == "POST" else {}
        request = urllib.request.Request(
            self._target(path), data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, _decode(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, _decode(exc.read())
        except OSError as exc:  # a route that kills the connection is a defect too
            pytest.fail(f"{method} {path} never answered: {exc}")

    def submit(self, workspace: Path, *, session_id: str = "route-probe") -> str:
        """Create a real, *unscheduled* task so the dynamic routes have an id.

        ``_defer_schedule`` is what the rest of the suite uses for this: the
        record exists (so the routes have something to address) but no worker
        starts, so the probe never races a real agent run.
        """
        status, payload = self.call(
            "POST",
            "/api/tasks",
            {
                "message": "route inventory probe",
                "session_id": session_id,
                "workspace_path": str(workspace),
                "allow_changes": False,
                "_defer_schedule": True,
            },
        )
        assert status == 202, payload
        task_id = str(payload.get("task_id") or "")
        assert task_id, payload
        return task_id

    def read_sse_prefix(self, path: str, *, limit: int = 4096, timeout: float = 10.0) -> tuple[int, str]:
        """Read a bounded prefix of a streaming response, then hang up.

        A streaming route cannot be driven by :meth:`call`: ``read()`` would sit
        on the socket until the stream's own timeout (``TASK_STREAM_TIMEOUT``),
        which is how a healthy route becomes a hung test. This stops as soon as
        one frame is complete (or the byte budget / deadline is spent) and
        always closes the connection.
        """
        request = urllib.request.Request(self._target(path), method="GET")
        try:
            response = urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", "replace")
        except OSError as exc:
            pytest.fail(f"GET {path} never answered: {exc}")
        try:
            status = int(response.status)
            buffer = b""
            deadline = time.monotonic() + timeout
            # ``read(256)`` on an ``HTTPResponse`` waits for the full 256 bytes,
            # so a short first frame would block until the socket timeout.
            # ``read1`` returns whatever has arrived, which is what "read one
            # frame and hang up" needs.
            reader = getattr(response, "read1", None)
            while b"\n\n" not in buffer and len(buffer) < limit and time.monotonic() < deadline:
                chunk = reader(256) if callable(reader) else response.read(256)
                if not chunk:
                    break
                buffer += chunk
            return status, buffer.decode("utf-8", "replace")
        finally:
            response.close()

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


#: Prefix-dispatched route families (``path.startswith("/api/tasks/")``). They
#: cannot be enumerated as a finite list, so the exact-path inventory above
#: cannot cover them — and M8-T33's whole point is that this hole is *data*
#: rather than a sentence in a boundary note.
#:
#: M8-T34 closed the hole instead of parking it: ``/api/tasks/`` now has a
#: streaming-aware probe (:func:`_probe_dynamic_routes` plus the two
#: ``test_dynamic_*`` gates), so it moved from "unprobed" to "probed". A family
#: that genuinely cannot be probed safely belongs in :data:`_PARKED_FAMILIES`
#: **with its reason**, never silently dropped.
_PROBED_FAMILIES = {"/api/tasks/"}

#: family -> why it cannot be probed. Empty on purpose: nothing is parked today,
#: and the gate below fails if a new family arrives without a decision.
_PARKED_FAMILIES: dict[str, str] = {}

#: The catch-all guard that answers 404 for anything under /api/ that matched no
#: route. Not a family with endpoints of its own.
_CATCH_ALL = "/api/"


def _prefix_families() -> set[str]:
    """Every ``path.startswith("/api/...")`` family inside the verb handlers."""
    tree = ast.parse(WEBSERVER.read_text(encoding="utf-8"))
    verbs = {"do_GET", "do_POST"}
    found: set[str] = set()
    for fn in (node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name in verbs):
        for node in ast.walk(fn):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "startswith"):
                continue
            receiver = node.func.value
            if not (isinstance(receiver, ast.Name) and receiver.id == "path"):
                continue
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                value = node.args[0].value
                if value.startswith("/api/") and value != _CATCH_ALL:
                    found.add(value)
    return found


def test_prefix_dispatched_families_are_probed_or_parked_with_a_reason() -> None:
    """The hole outside the 100 % is recorded, and cannot grow quietly."""
    families = _prefix_families()
    assert "/api/tasks/" in families, families
    declared = _PROBED_FAMILIES | set(_PARKED_FAMILIES)
    assert families == declared, (
        "a prefix-dispatched route family appeared that this gate does not probe; "
        "either probe it or record why not: " + json.dumps(sorted(families ^ declared))
    )
    # A family may only be parked with a reason; an empty-string reason is how a
    # silent drop would look once it has been written into the dict.
    assert all(reason.strip() for reason in _PARKED_FAMILIES.values()), _PARKED_FAMILIES


def test_the_route_inventory_is_actually_a_route_inventory() -> None:
    routes = _route_table()
    assert len(routes["GET"]) >= _MIN_GET_ROUTES, routes
    assert len(routes["POST"]) >= _MIN_POST_ROUTES, routes
    # An inventory that silently lost the chat/task routes would make every
    # later per-route assertion pass by covering nothing.
    assert {"/api/chat", "/api/tasks", "/api/tasks/batch"} <= set(routes["POST"]), routes["POST"]
    assert "/api/metrics" in routes["GET"], routes["GET"]
    # The dynamic family is part of the inventory, not a footnote beside it.
    for verb, templates in _DYNAMIC_ROUTES.items():
        assert set(templates) <= set(routes[verb]), (verb, templates, routes[verb])


def test_every_get_route_answers_or_refuses_with_a_code(tmp_path: Path) -> None:
    live = _Live(tmp_path)
    try:
        routes = [path for path in _route_table()["GET"] if _TEMPLATE not in path]
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
        routes = [path for path in _route_table()["POST"] if _TEMPLATE not in path]
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


# ---------------------------------------------------------------------------
# M8-T34: the streaming-aware probe for the prefix-dispatched family
#
# M8-T33 turned "the 100 % has a hole" into data. This closes the hole: each
# route under ``/api/tasks/`` is driven with a real task id, including the SSE
# endpoint, which is read as a stream and hung up on as soon as one frame is
# complete. Nothing here may block on a socket until a timeout.
# ---------------------------------------------------------------------------


def test_dynamic_task_routes_answer_or_refuse_with_a_code(tmp_path: Path) -> None:
    """GET detail, POST resume and POST cancel, all addressed to a real id."""
    live = _Live(tmp_path)
    try:
        task_id = live.submit(tmp_path)
        for method, path in (
            ("GET", f"/api/tasks/{task_id}"),
            ("POST", f"/api/tasks/{task_id}/resume"),
            ("POST", f"/api/tasks/{task_id}/cancel"),
        ):
            status, payload = live.call(method, path)
            assert_answered(f"{method} {path}", status, payload)
    finally:
        live.shutdown()


def test_dynamic_task_routes_refuse_an_unknown_id_with_a_stable_code(tmp_path: Path) -> None:
    """An unknown id is refused *by code*, not by a 500 or a hang.

    ``task_not_found`` is the documented shape for this family; pinning the
    exact code is what makes the assertion more than "something happened".
    """
    live = _Live(tmp_path)
    try:
        status, payload = live.call("GET", "/api/tasks/task-does-not-exist")
        assert status == 404, payload
        assert payload.get("code") == "task_not_found", payload

        status, payload = live.call("GET", "/api/tasks/task-does-not-exist/events")
        assert status == 404, payload
        assert payload.get("code") == "task_not_found", payload
    finally:
        live.shutdown()


def test_event_stream_yields_a_frame_without_hanging(tmp_path: Path) -> None:
    """The SSE route is read as a stream: one frame, then hang up.

    This is the route M8-T33 named as the reason the family could not be probed
    by the generic driver. The bound below is a multiple of the probe's own
    deadline, so it moves with the implementation rather than becoming a load
    function; a socket that hangs forever is NOT caught here - that is M8-T50.
    """
    live = _Live(tmp_path)
    try:
        task_id = live.submit(tmp_path)
        deadline, started = live.read_sse_prefix.__kwdefaults__["timeout"], time.monotonic()
        status, text = live.read_sse_prefix(f"/api/tasks/{task_id}/events", timeout=deadline)
        elapsed = time.monotonic() - started
        assert status == 200, (status, text[:400])
        assert "data:" in text, f"stream produced no frame: {text[:400]!r}"
        assert elapsed < 3 * deadline, f"stream probe took {elapsed:.1f}s against a {deadline}s probe deadline"
        source = Path(__file__).read_text(encoding="utf-8")
        marker = "elapsed < 3" + " * deadline"  # 拆开写：见证不许自己拼出要找的东西
        assert marker in source, "the bound drifted back to an absolute literal"
    finally:
        live.shutdown()


def test_event_stream_replay_from_a_cursor_also_answers(tmp_path: Path) -> None:
    """Reconnecting with ``?after=`` is the documented replay path; probe it too."""
    live = _Live(tmp_path)
    try:
        task_id = live.submit(tmp_path)
        status, text = live.read_sse_prefix(f"/api/tasks/{task_id}/events?after=0")
        assert status == 200, (status, text[:400])
        assert "data:" in text, f"replay produced no frame: {text[:400]!r}"
    finally:
        live.shutdown()


