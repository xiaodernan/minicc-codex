"""M8-T595 — the http tools' declared parameters match their handlers.

Four hand-spelled declaration-vs-handler pairs were kept in step by memory:

* the ``webfetch`` tool's timeout Param (1..600 — the schema for ``bash``'s
  sibling) vs ``webfetch``'s clamp (``max(1.0, min(60.0, timeout))``);
* the ``web_search`` result-count Param (1..8) vs the handler's
  ``min(MAX_RESULTS=8, ...)``;
* ``web_search``'s query Param (max_len=500) vs ``MAX_QUERY_CHARS`` (the
  handler raises past it);
* ``web_search``'s Param description claims "max 20" for the timeout —
  ``DEFAULT_TIMEOUT = 20.0``.

After this batch both sides ask the same constants: ``webfetch.MIN_TIMEOUT``
/ ``MAX_TIMEOUT`` for the clamp and the Param's int caps; ``web.MAX_RESULTS``
/ ``MAX_QUERY_CHARS`` for the search caps. This gate pins:

* the four home constants (1.0 / 60.0 / 20.0 / 8 / 500);
* the Param declarations reference the homes by name (AST);
* the clamp expression references the homes by name (source scan).
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOLS_INIT = REPO / "minicc" / "tools" / "__init__.py"
WEBFETCH = REPO / "minicc" / "tools" / "webfetch.py"
WEB = REPO / "minicc" / "tools" / "web.py"


def _param_nodes(tree: ast.Module):
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)):
            continue
        target = node.targets[0].id
        value = node.value
        if not (isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == "Param"):
            continue
        yield target, {kw.arg: kw.value for kw in value.keywords}


def _int_name_call(node) -> str | None:
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "int":
        if len(node.args) == 1 and isinstance(node.args[0], ast.Name):
            return node.args[0].id
    return None


def test_the_http_tool_declarations_match_their_handlers() -> None:
    import importlib

    import minicc.tools.web as web_mod

    # tools/__init__.py does `from .webfetch import webfetch`, shadowing the
    # module attribute on the package with the handler function - importlib
    # asks sys.modules instead of getattr.
    webfetch_mod = importlib.import_module("minicc.tools.webfetch")

    assert webfetch_mod.MIN_TIMEOUT == 1.0
    assert webfetch_mod.MAX_TIMEOUT == 60.0
    assert webfetch_mod.DEFAULT_TIMEOUT == 20.0
    assert web_mod.MAX_RESULTS == 8
    assert web_mod.MAX_QUERY_CHARS == 500
    assert web_mod.MAX_RESULTS_PARAM == "max_results"

    tree = ast.parse(TOOLS_INIT.read_text(encoding="utf-8"), filename=str(TOOLS_INIT))
    params = dict(_param_nodes(tree))

    fetch_timeout = params["fetch_timeout_p"]
    assert _int_name_call(fetch_timeout["min_value"]) == "MIN_TIMEOUT"
    assert _int_name_call(fetch_timeout["max_value"]) == "MAX_TIMEOUT"

    search_limit = params["search_limit_p"]
    assert isinstance(search_limit["min_value"], ast.Constant) and search_limit["min_value"].value == 1
    assert isinstance(search_limit["max_value"], ast.Name) and search_limit["max_value"].id == "MAX_RESULTS"

    search_query = params["search_query_p"]
    assert isinstance(search_query["max_len"], ast.Name) and search_query["max_len"].id == "MAX_QUERY_CHARS"


def test_the_clamps_ask_the_homes_not_raw_literals() -> None:
    fetch_src = WEBFETCH.read_text(encoding="utf-8")
    assert "min(MAX_TIMEOUT" in fetch_src
    assert "max(MIN_TIMEOUT" in fetch_src
    assert "min(60.0" not in fetch_src
    assert "max(1.0" not in fetch_src

    web_src = WEB.read_text(encoding="utf-8")
    assert "min(MAX_RESULTS" in web_src
    assert "if len(raw_query) > MAX_QUERY_CHARS" in web_src
