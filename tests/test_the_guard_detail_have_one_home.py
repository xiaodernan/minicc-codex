"""The guard trace detail must have exactly one home."""

from __future__ import annotations

import ast
import pathlib

from minicc.agent.loop import _guard_detail

REPO = pathlib.Path(__file__).resolve().parents[1]


def test_home_carries_both_numbers():
    assert _guard_detail(7, 3) == {"turn": 7, "retry_limit": 3}


def test_census_exactly_one_literal_and_it_is_the_home():
    target = {"turn", "retry_limit"}
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
    window = "\n".join(lines[max(0, lineno - 14):lineno + 3])
    assert "def _guard_detail" in window, window


def test_call_sites_use_the_home():
    source = (REPO / "minicc/agent/loop.py").read_text(encoding="utf-8")
    assert source.count("_guard_detail(") == 3
