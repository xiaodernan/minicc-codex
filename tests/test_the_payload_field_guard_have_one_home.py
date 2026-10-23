"""The JSON payload field guard must have exactly one home."""

from __future__ import annotations

import ast
import pathlib

import pytest

from minicc.input_guard import require_text
from minicc.webserver import MiniccHTTPServer  # noqa: F401 - import proves reachability

REPO = pathlib.Path(__file__).resolve().parents[1]
PAYLOAD_READERS = (
    "minicc/web.py",
    "minicc/webserver.py",
    "minicc/task_manager.py",
)
HOME = "minicc/input_guard.py"


def test_home_strips_and_returns():
    assert require_text("  abc  ", "session_id") == "abc"


@pytest.mark.parametrize("bad", [None, "", "   ", 123, [], {}])
def test_home_rejects_every_empty_spelling(bad):
    with pytest.raises(ValueError, match="session_id 不能为空"):
        require_text(bad, "session_id")


def test_home_names_the_field_it_rejected():
    with pytest.raises(ValueError, match="^decision 不能为空$"):
        require_text("  ", "decision")


def test_home_is_a_leaf_module():
    """The transport that needs it most sits below ``web``.

    ``web`` re-exports the HTTP server, so ``webserver`` cannot import
    from ``web``; a home anywhere above it is unreachable from the file
    that hand-rolled the guard ten times.
    """
    tree = ast.parse((REPO / HOME).read_text(encoding="utf-8"))
    intra = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.level > 0 or (node.module or "").startswith("minicc")):
            intra.append(node.lineno)
        elif isinstance(node, ast.Import):
            intra.extend(node.lineno for a in node.names if a.name.startswith("minicc"))
    assert intra == [], intra


def _field_messages(path: pathlib.Path) -> list[tuple[str, int]]:
    """AST sites that spell a whole ``<field> 不能为空`` message."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value.endswith("不能为空") and len(node.value) > 5:
                hits.append((node.value, node.lineno))
    return hits


def test_no_payload_reader_spells_the_message_by_hand():
    """A hand-spelled message is a guard that lost one of its two halves."""
    for rel in PAYLOAD_READERS:
        hits = _field_messages(REPO / rel)
        assert hits == [], (rel, hits)


def _guard_idioms(path: pathlib.Path) -> list[int]:
    """AST sites of the hand-written isinstance/strip pair."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue

        def neg_isinstance(sub):
            return (
                isinstance(sub, ast.UnaryOp)
                and isinstance(sub.op, ast.Not)
                and isinstance(sub.operand, ast.Call)
                and getattr(sub.operand.func, "id", "") == "isinstance"
            )

        def neg_strip(sub):
            return (
                isinstance(sub, ast.UnaryOp)
                and isinstance(sub.op, ast.Not)
                and isinstance(sub.operand, ast.Call)
                and getattr(sub.operand.func, "attr", "") == "strip"
            )

        walker = list(ast.walk(node.test))
        if any(neg_isinstance(s) for s in walker) and any(neg_strip(s) for s in walker):
            hits.append(node.lineno)
    return hits


def test_no_payload_reader_writes_the_guard_idiom():
    for rel in PAYLOAD_READERS:
        assert _guard_idioms(REPO / rel) == [], (rel, _guard_idioms(REPO / rel))


def test_the_transport_calls_the_home():
    """The route table must read its fields through the one guard."""
    source = (REPO / "minicc" / "webserver.py").read_text(encoding="utf-8")
    assert source.count("require_text(") >= 10, source.count("require_text(")
    task_source = (REPO / "minicc" / "task_manager.py").read_text(encoding="utf-8")
    assert task_source.count("require_text(") >= 1


def test_the_home_owns_the_message_shape():
    home = (REPO / HOME).read_text(encoding="utf-8")
    assert home.count("f\"{field} 不能为空\"") == 1
