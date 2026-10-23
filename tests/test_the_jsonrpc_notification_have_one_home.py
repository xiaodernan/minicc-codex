"""The JSON-RPC notification envelope must have exactly one home."""

from __future__ import annotations

import ast
import pathlib

from minicc.mcp import _jsonrpc_notification

REPO = pathlib.Path(__file__).resolve().parents[1]


def test_home_carries_three_keys_and_no_id():
    envelope = _jsonrpc_notification("notifications/initialized", {})
    assert envelope == {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
    assert "id" not in envelope


def test_home_pins_the_version():
    assert _jsonrpc_notification("m", {})["jsonrpc"] == "2.0"


def test_census_exactly_one_literal_and_it_is_the_home():
    target = {"jsonrpc", "method", "params"}
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
    window = "\n".join(lines[max(0, lineno - 14):lineno + 3])
    assert "def _jsonrpc_notification" in window, window


def test_call_sites_use_the_home():
    source = (REPO / "minicc/mcp.py").read_text(encoding="utf-8")
    assert source.count("_jsonrpc_notification(") == 3
    assert source.count('_JSONRPC_VERSION') == 4
    assert '"jsonrpc": "2.0"' not in source
