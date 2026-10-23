"""The OpenAI tool wire shape must have exactly one home."""

from __future__ import annotations

import ast
import pathlib

from minicc.tools.registry import ToolSpec, _openai_tool_wire

REPO = pathlib.Path(__file__).resolve().parents[1]


def test_home_carries_the_three_function_keys():
    wire = _openai_tool_wire("bash", "run a command", {"type": "object"})
    assert wire == {
        "type": "function",
        "function": {"name": "bash", "description": "run a command", "parameters": {"type": "object"}},
    }


def test_openai_schema_uses_the_home_on_both_paths():
    given = ToolSpec(
        name="todo_write",
        description="write todos",
        risk="readonly",
        params=(),
        handler=lambda: None,
        input_schema={"type": "object", "properties": {}, "required": []},
    ).openai_schema()
    assert given["type"] == "function"
    assert given["function"]["parameters"] == {"type": "object", "properties": {}, "required": []}
    assert given["function"]["name"] == "todo_write"


def test_census_exactly_one_literal_and_it_is_the_home():
    target = {"name", "description", "parameters"}
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
    assert path == "minicc/tools/registry.py"
    source = (REPO / path).read_text(encoding="utf-8")
    lines = source.splitlines()
    window = "\n".join(lines[max(0, lineno - 16):lineno + 4])
    assert "def _openai_tool_wire" in window, window


def test_call_sites_use_the_home():
    source = (REPO / "minicc/tools/registry.py").read_text(encoding="utf-8")
    assert source.count("_openai_tool_wire(") == 3
