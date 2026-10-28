"""M8-T530: an MCP answer the reader cannot read is not an answer of "no tools".

Both MCP transports ended every listing read the same way: a ``tools`` key that
was missing, ``null``, a dict instead of a list, or a list of strings came back
as ``[]`` — and the manager published that server as ``state: "ok"`` with an
empty ``skipped``.  A server that answered in a shape this client cannot read
was therefore indistinguishable from a server with no tools, and the roster the
model was handed read as if it were complete.  The item loop did not even
survive a non-object item: ``tool_specs()`` raised ``AttributeError`` and took
the *answering* server's tools down with it.

The resources/prompts half swallowed harder: both clients caught ``McpError``
and returned ``[]``, so a timeout, a dead child and a server that answered
"resources not supported" (with a code and a message) all became silence.

This door pins one home for reading a listing, and pins that a read which had
to leave things out says so:

* ``_read_listing`` returns the items it could read **and** a sentence per
  thing it had to leave out (missing key, ``null``, wrong type, N of M items
  that are not objects, N of M items without an identifier);
* the two transports' ``list_*()`` methods stay plain-list projections, because
  the registry bridge and four existing tests read that contract;
* a listing failure may not end as an empty list inside a client — the reason
  travels with the items to the manager;
* the disclosure has a home that already ships: ``status()["unreadable"]``,
  which ``/api/mcp`` and ``workspace_info()["mcp"]`` forward verbatim, beside
  the ``skipped`` half M8-T264 already settled;
* both halves of the read also say it in the log — measured before the fix, the
  tools side warned and the resources side stayed silent, which is the same
  asymmetry one level down;
* a server whose *answer* was unreadable is still alive: shape is not death.

Real stdio children (the venv interpreter), no mocking of ``subprocess``.
"""

from __future__ import annotations

import ast
import json
import logging
import sys
from pathlib import Path

from minicc import mcp as mcp_mod
from minicc.mcp import McpManager

#: One spec-driven server stands in for every shape: ``answers`` overrides the
#: result for one method verbatim, or sends a JSON-RPC error with ``__error__``.
SERVER_SRC = r'''
import json, sys

spec = json.load(open(sys.argv[1], encoding="utf-8"))
answers = spec.get("answers", {})
sequence = spec.get("sequence", {})
seen = {}

DEFAULTS = {
    "initialize": {"protocolVersion": "2024-11-05", "capabilities": {},
                   "serverInfo": {"name": "shape", "version": "0"}},
    "tools/list": {"tools": spec.get("tools", [])},
    "resources/list": {"resources": spec.get("resources", [])},
    "prompts/list": {"prompts": spec.get("prompts", [])},
}

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        continue
    method = msg.get("method")
    mid = msg.get("id")
    if method == "notifications/initialized" or mid is None:
        continue
    steps = sequence.get(method)
    if steps:
        index = seen.get(method, 0)
        reply = steps[min(index, len(steps) - 1)]
        seen[method] = index + 1
    else:
        reply = answers.get(method, DEFAULTS.get(method, {}))
    if isinstance(reply, dict) and reply.get("__error__"):
        out = {"jsonrpc": "2.0", "id": mid,
               "error": {"code": -32601, "message": reply["__error__"]}}
    else:
        out = {"jsonrpc": "2.0", "id": mid, "result": reply}
    sys.stdout.write(json.dumps(out) + "\n")
    sys.stdout.flush()
'''

HEALTHY_TOOL = "mcp__healthy__healthy_tool"


def _workspace(tmp_path: Path, tag: str, specs: dict[str, dict]) -> Path:
    ws = tmp_path / f"ws_{tag}"
    (ws / ".minicc").mkdir(parents=True, exist_ok=True)
    (ws / "shape_server.py").write_text(SERVER_SRC, encoding="utf-8")
    servers: dict[str, dict] = {}
    for name, spec in specs.items():
        spec_path = ws / f"spec_{name}.json"
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        servers[name] = {
            "command": sys.executable,
            "args": [str(ws / "shape_server.py"), str(spec_path)],
        }
    (ws / ".minicc" / "mcp.json").write_text(
        json.dumps({"servers": servers}), encoding="utf-8")
    return ws


def _unreadable(manager: McpManager) -> dict[str, list[str]]:
    """The shipped disclosure channel for an answer that could not be read."""
    return manager.status().get("unreadable") or {}


# --- the home ----------------------------------------------------------------


def test_the_home_returns_items_and_a_sentence_for_everything_it_left_out() -> None:
    home = getattr(mcp_mod, "_read_listing", None)
    assert home is not None, (
        "the listing read has no home yet: a missing key, a null, a dict and a "
        "list of strings all end as [] with nothing said about which it was"
    )

    ok = [{"name": "a"}, {"name": "b"}]
    assert home({"tools": ok}, "tools") == (ok, [])

    missing_items, missing_reasons = home({}, "tools")
    assert missing_items == []
    assert missing_reasons and "'tools'" in missing_reasons[0], missing_reasons

    _, null_reasons = home({"tools": None}, "tools")
    assert null_reasons and "null" in null_reasons[0], null_reasons

    _, dict_reasons = home({"tools": {"a": 1}}, "tools")
    assert dict_reasons and "dict" in dict_reasons[0], dict_reasons

    kept, item_reasons = home({"tools": [{"name": "a"}, "just a string"]}, "tools")
    assert kept == [{"name": "a"}]
    assert item_reasons and "1 of 2" in item_reasons[0], item_reasons

    _, ident_reasons = home({"tools": [{"description": "no name"}]}, "tools")
    assert ident_reasons and "1 of 1" in ident_reasons[0], ident_reasons

    resources, _ = home({"resources": [{"uri": "file:///a"}]}, "resources",
                        id_keys=("uri", "name"))
    assert resources == [{"uri": "file:///a"}]


def test_a_listing_failure_may_not_end_as_an_empty_list_inside_a_client() -> None:
    """The swallow has to move: a client that answers [] owns the last word."""
    tree = ast.parse(Path(mcp_mod.__file__).read_text(encoding="utf-8"))
    offenders: list[str] = []
    for klass in [n for n in tree.body if isinstance(n, ast.ClassDef)]:
        if klass.name not in ("McpStdioClient", "McpHttpClient"):
            continue
        for func in [
            n for n in klass.body
            if isinstance(n, ast.FunctionDef) and "list" in n.name
        ]:
            for node in ast.walk(func):
                if not isinstance(node, ast.ExceptHandler) or node.type is None:
                    continue
                if ast.unparse(node.type) != "McpError":
                    continue
                for ret in [n for n in node.body if isinstance(n, ast.Return)]:
                    if _discloses_failure(ret.value):
                        continue
                    offenders.append(f"{klass.name}.{func.name}:{node.lineno}")
    assert not offenders, (
        "a listing read that failed is answered with silence inside the client, "
        "where nothing downstream can tell it from an empty server: "
        + ", ".join(offenders)
    )


def _discloses_failure(value: ast.expr | None) -> bool:
    """True when a return hands back a reason beside the (possibly empty) items."""
    return (
        isinstance(value, ast.Tuple)
        and len(value.elts) == 2
        and isinstance(value.elts[1], ast.List)
        and bool(value.elts[1].elts)
    )


# --- end to end: the tool half -----------------------------------------------


def test_a_server_that_answered_with_no_shape_is_not_a_server_with_no_tools(
    tmp_path: Path,
) -> None:
    ws = _workspace(tmp_path, "shape", {
        "broken": {"answers": {"tools/list": {}}},
    })
    manager = McpManager(ws)
    try:
        assert manager.tool_specs() == []
        reasons = _unreadable(manager)
        assert "broken" in reasons, (
            "the server answered something unreadable and status() called it "
            f"nothing: {json.dumps(manager.status(), ensure_ascii=False)}"
        )
        assert any("tools" in text for text in reasons["broken"]), reasons
    finally:
        manager.close()


def test_one_unreadable_item_does_not_take_the_answering_server_down(
    tmp_path: Path,
) -> None:
    ws = _workspace(tmp_path, "pair", {
        "healthy": {"tools": [{"name": "healthy_tool", "description": "ok"}]},
        "ragged": {"answers": {"tools/list": {"tools": ["just", "strings"]}}},
    })
    manager = McpManager(ws)
    try:
        try:
            names = sorted(spec.name for spec in manager.tool_specs())
        except AttributeError as exc:
            names = f"RAISED {type(exc).__name__}: {exc}"
        assert names == [HEALTHY_TOOL], (
            f"one ragged server cost the answering server its tool: {names}"
        )
        assert "ragged" in _unreadable(manager), sorted(_unreadable(manager))
    finally:
        manager.close()


# --- end to end: the resources/prompts half ----------------------------------


def test_a_resources_error_is_not_the_clients_to_swallow(tmp_path: Path) -> None:
    ws = _workspace(tmp_path, "ctx", {
        "srv": {
            "tools": [{"name": "healthy_tool"}],
            "answers": {
                "resources/list": {"__error__": "resources not supported"},
                "prompts/list": {"no_prompts_key": True},
            },
        },
    })
    manager = McpManager(ws)
    try:
        assert manager.resources_context() == ""
        reasons = _unreadable(manager)
        assert "srv" in reasons, (
            "the server said 'resources not supported' with a code and a message "
            f"and nothing downstream kept it: {json.dumps(reasons, ensure_ascii=False)}"
        )
        text = " ".join(reasons["srv"]).lower()
        assert "resource" in text, reasons
        assert "prompt" in text, reasons
    finally:
        manager.close()


# --- over-correction guards ---------------------------------------------------


def test_the_list_projections_still_ship_plain_lists(tmp_path: Path) -> None:
    ws = _workspace(tmp_path, "proj", {"srv": {"tools": [{"name": "healthy_tool"}]}})
    manager = McpManager(ws)
    try:
        manager.tool_specs()
        client = manager.clients["srv"]
        assert client.list_tools() == [{"name": "healthy_tool"}]
        assert client.list_resources() == []
        assert client.list_prompts() == []
    finally:
        manager.close()


def test_an_unreadable_answer_leaves_the_server_alive(tmp_path: Path) -> None:
    """Shape is not death: health() must still say ok and skipped stays empty."""
    ws = _workspace(tmp_path, "alive", {
        "broken": {"answers": {"tools/list": {"tools": None}}},
    })
    manager = McpManager(ws)
    try:
        manager.tool_specs()
        assert [row["state"] for row in manager.health()] == ["ok"], manager.health()
        assert not (manager.status().get("skipped") or {}), manager.status()["skipped"]
    finally:
        manager.close()


def test_a_server_that_finally_answers_stops_being_named(tmp_path: Path) -> None:
    """A note that never clears is the same lie as a roster that never shrinks."""
    ws = _workspace(tmp_path, "clears", {
        "srv": {"sequence": {"tools/list": [{"tools": None},
                                            {"tools": [{"name": "healthy_tool"}]}]}},
    })
    manager = McpManager(ws)
    try:
        assert manager.tool_specs() == []
        assert "srv" in _unreadable(manager), manager.status()
        names = [spec.name for spec in manager.tool_specs()]
        assert names == ["mcp__srv__healthy_tool"], names
        assert "srv" not in _unreadable(manager), (
            f"the server answered cleanly and is still reported unreadable: "
            f"{_unreadable(manager)}"
        )
    finally:
        manager.close()


def test_one_kind_cannot_erase_what_another_kind_had_to_say(tmp_path: Path) -> None:
    """The disclosure is per answer: tools being fine must mute resources nothing."""
    ws = _workspace(tmp_path, "both", {
        "srv": {
            "answers": {
                "tools/list": {"tools": None},
                "resources/list": {"__error__": "resources not supported"},
            },
        },
    })
    manager = McpManager(ws)
    try:
        manager.tool_specs()
        manager.resources_context()
        reasons = _unreadable(manager).get("srv") or []
        text = " | ".join(reasons)
        assert "tools:" in text, reasons
        assert "resources:" in text, reasons
    finally:
        manager.close()


# --- the operator side --------------------------------------------------------


def test_both_halves_of_the_read_also_tell_the_operator(tmp_path: Path) -> None:
    """``status()`` is what a caller reads; the WARNING is what a watching human gets.

    Measured while writing this door: the tools half already warned and the
    resources half recorded its reason and said nothing out loud, so a session
    that kept showing no resources had no log line about why.
    """
    captured: list[str] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            if record.name == "minicc.mcp" and record.levelno >= logging.WARNING:
                captured.append(record.getMessage())

    ws = _workspace(tmp_path, "warn", {
        "srv": {
            "answers": {
                "tools/list": {"tools": None},
                "resources/list": {"__error__": "resources not supported"},
            },
        },
    })
    log = logging.getLogger("minicc.mcp")
    handler = Capture()
    log.addHandler(handler)
    manager = McpManager(ws)
    try:
        manager.tool_specs()
        manager.resources_context()
    finally:
        log.removeHandler(handler)
        manager.close()

    text = " || ".join(captured)
    assert "tools/list 有读不出来的部分" in text, captured
    assert "resources/list 有读不出来的部分" in text, captured


def test_stdio_manager_discovers_all_three_listings_after_an_empty_page(tmp_path: Path) -> None:
    ws = _workspace(tmp_path, "paged", {
        "srv": {"sequence": {
            "tools/list": [
                {"tools": [], "nextCursor": "tools-page-two"},
                {"tools": [{"name": "later_tool"}]},
            ],
            "resources/list": [
                {"resources": [], "nextCursor": "resources-page-two"},
                {"resources": [{"uri": "file:///later-resource"}]},
            ],
            "prompts/list": [
                {"prompts": [], "nextCursor": "prompts-page-two"},
                {"prompts": [{"name": "later_prompt"}]},
            ],
        }},
    })
    manager = McpManager(ws)
    try:
        assert [spec.name for spec in manager.tool_specs()] == ["mcp__srv__later_tool"]
        context = manager.resources_context()
        assert "resource file:///later-resource" in context
        assert "prompt later_prompt" in context
        assert not _unreadable(manager)
    finally:
        manager.close()


def test_stdio_manager_discloses_an_incomplete_paginated_listing(tmp_path: Path) -> None:
    ws = _workspace(tmp_path, "page_failure", {
        "srv": {"sequence": {"tools/list": [
            {"tools": [{"name": "kept"}], "nextCursor": "next"},
            {"__error__": "page unavailable"},
        ]}},
    })
    manager = McpManager(ws)
    try:
        assert [spec.name for spec in manager.tool_specs()] == ["mcp__srv__kept"]
        reasons = _unreadable(manager)["srv"]
        assert any("tools:" in reason and "page 2" in reason and "page unavailable" in reason for reason in reasons)
    finally:
        manager.close()
