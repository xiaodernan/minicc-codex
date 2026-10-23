"""The turn tools trace detail must have exactly one home."""

from __future__ import annotations

import ast
import pathlib

from minicc.agent.loop import _turn_tools_detail
from minicc.tools.schemas import ToolResult

REPO = pathlib.Path(__file__).resolve().parents[1]


class _Call:
    def __init__(self, tool: str):
        self.tool = tool
        self.arguments: dict = {}


def test_home_collects_qualifying_tool_names():
    results = {
        0: (_Call("read"), ToolResult(status="ok")),
        1: (_Call("bash"), ToolResult(status="error")),
    }
    detail = _turn_tools_detail(4, results, lambda call, result: result.status == "ok")
    assert detail == {"turn": 4, "tools": ["read"]}


def test_home_reports_empty_inventory():
    assert _turn_tools_detail(1, {}, lambda call, result: True) == {"turn": 1, "tools": []}


def test_census_exactly_one_literal_and_it_is_the_home():
    target = {"turn", "tools"}
    hits = []
    for path in sorted((REPO / "minicc").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                keys = {
                    key.value
                    for key in node.keys
                    if isinstance(key, ast.Constant) and isinstance(key.value, str)
                }
                if keys == target:
                    hits.append((path.relative_to(REPO).as_posix(), node.lineno))
    assert len(hits) == 1, hits
    path, lineno = hits[0]
    assert path == "minicc/agent/loop.py"
    source = (REPO / path).read_text(encoding="utf-8")
    lines = source.splitlines()
    window = "\n".join(lines[max(0, lineno - 22):lineno + 4])
    assert "def _turn_tools_detail" in window, window


def test_call_sites_use_the_home():
    source = (REPO / "minicc/agent/loop.py").read_text(encoding="utf-8")
    assert source.count("_turn_tools_detail(") == 3
