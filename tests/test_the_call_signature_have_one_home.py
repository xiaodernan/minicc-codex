"""The tool-call identity must have exactly one home."""

from __future__ import annotations

import ast
import pathlib

from minicc.agent.loop import _call_signature, _signature

REPO = pathlib.Path(__file__).resolve().parents[1]


def test_home_is_the_signature_of_the_two_key_call():
    assert _call_signature("bash", {"command": "pytest"}) == _signature(
        {"tool": "bash", "arguments": {"command": "pytest"}}
    )


def test_home_separates_different_arguments():
    assert _call_signature("bash", {"command": "a"}) != _call_signature("bash", {"command": "b"})
    assert _call_signature("read", {"path": "a"}) != _call_signature("write", {"path": "a"})


def test_census_exactly_one_literal_and_it_is_the_home():
    target = {"tool", "arguments"}
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
    window = "\n".join(lines[max(0, lineno - 12):lineno + 4])
    assert "def _call_signature" in window, window


def test_call_sites_use_the_home():
    source = (REPO / "minicc/agent/loop.py").read_text(encoding="utf-8")
    assert source.count("_call_signature(") == 3
