"""The MCP initialize params must have exactly one home."""

from __future__ import annotations

import ast
import pathlib

from minicc.mcp import _client_info, _initialize_params

REPO = pathlib.Path(__file__).resolve().parents[1]


def test_home_carries_three_keys_with_the_given_version():
    params = _initialize_params("2024-11-05")
    assert params == {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": _client_info(),
    }


def test_home_lets_each_transport_pick_its_revision():
    assert _initialize_params("2025-03-26")["protocolVersion"] == "2025-03-26"


def test_census_exactly_one_literal_and_it_is_the_home():
    target = {"capabilities", "clientInfo", "protocolVersion"}
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
    assert path == "minicc/mcp.py"
    source = (REPO / path).read_text(encoding="utf-8")
    lines = source.splitlines()
    window = "\n".join(lines[max(0, lineno - 16):lineno + 4])
    assert "def _initialize_params" in window, window


def test_call_sites_use_the_home():
    source = (REPO / "minicc/mcp.py").read_text(encoding="utf-8")
    assert source.count("_initialize_params(") == 3
