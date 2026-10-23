"""The empty-field guard must have exactly one home."""

from __future__ import annotations

import ast
import pathlib

import pytest

from minicc.web import _require_text

REPO = pathlib.Path(__file__).resolve().parents[1]


def test_home_strips_and_returns():
    assert _require_text("  abc  ", "session_id") == "abc"


@pytest.mark.parametrize("bad", [None, "", "   ", 123, []])
def test_home_rejects_every_empty_spelling(bad):
    with pytest.raises(ValueError, match="session_id 不能为空"):
        _require_text(bad, "session_id")


def _strict_guard_sites(path: pathlib.Path) -> list[tuple[str, int]]:
    """AST sites of the hand-written isinstance/strip/raise idiom."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not isinstance(test, ast.BoolOp) or not isinstance(test.op, ast.Or):
            continue
        if len(test.values) != 2:
            continue
        first, second = test.values
        if not (isinstance(first, ast.UnaryOp) and isinstance(first.op, ast.Not)):
            continue
        if not (isinstance(first.operand, ast.Call) and getattr(first.operand.func, "id", "") == "isinstance"):
            continue
        if not (isinstance(second, ast.UnaryOp) and isinstance(second.op, ast.Not)):
            continue
        if not (isinstance(second.operand, ast.Call) and getattr(second.operand.func, "attr", "") == "strip"):
            continue
        hits.append((path.name, node.lineno))
    return hits


def test_census_exactly_one_guard_idiom_and_it_is_the_home():
    hits = _strict_guard_sites(REPO / "minicc" / "web.py")
    assert len(hits) == 1, hits
    _, lineno = hits[0]
    source = (REPO / "minicc" / "web.py").read_text(encoding="utf-8")
    lines = source.splitlines()
    window = "\n".join(lines[max(0, lineno - 12):lineno + 3])
    assert "def _require_text" in window, window


def test_call_sites_use_the_home():
    source = (REPO / "minicc" / "web.py").read_text(encoding="utf-8")
    assert source.count("_require_text(") == 8
    assert source.count('"session_id 不能为空"') == 2
    assert source.count('"thread_id 不能为空"') == 0
    assert source.count('"message 不能为空"') == 0
    assert source.count('"工作区路径不能为空"') == 0
