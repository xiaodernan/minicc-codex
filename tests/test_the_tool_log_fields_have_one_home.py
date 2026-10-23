"""M8-T415 — 工具日志条目词表两个家：CLI 生产者与会话库落盘白名单各写一份"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/session.py"
PRODUCER = "minicc/main.py"

FIELDS = ("index", "tool", "summary", "command", "output")


def test_the_vocabulary_has_a_name() -> None:
    """The home exists, and it holds the five fields in their written order."""
    from minicc.session import TOOL_LOG_FIELDS

    assert TOOL_LOG_FIELDS == FIELDS


def test_the_producer_spells_the_same_five_fields() -> None:
    """The CLI view recorder's entry literal is the vocabulary, no more.

    A sixth field the CLI starts writing is invisible on disk until the
    whitelist names it - the drift is silent in exactly the direction that
    loses data: the run shows it, every reconnect does not.
    """
    tree = ast.parse((PACKAGE / "main.py").read_text(encoding="utf-8"))
    producer = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "record_tool"
    )
    literals = [
        node for node in ast.walk(producer)
        if isinstance(node, ast.Dict)
        and {
            key.value for key in node.keys
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        } == set(FIELDS)
    ]
    assert len(literals) == 1, (
        "the CLI view recorder must spell the tool-log entry exactly once, "
        f"found {len(literals)}"
    )


def test_the_whitelist_keeps_every_field_and_nothing_else() -> None:
    """The persisted copy carries the five fields - and drops the rest."""
    from minicc.session import SessionStore

    item = {
        "index": 3, "tool": "bash", "summary": "ran",
        "command": "echo hi", "output": "hi",
        "secret": "sk-live-123", "empty": "",
    }
    persisted = SessionStore._redacted_view_item(item)
    assert list(persisted) == list(FIELDS), persisted
    assert "secret" not in persisted and "empty" not in persisted, persisted


def test_a_field_the_whitelist_forgets_is_absent_from_every_reconnect() -> None:
    """The behavioral half: drop one field from the vocabulary and it vanishes."""
    from minicc.session import SessionStore

    persisted = SessionStore._redacted_view_item(
        {"index": 1, "tool": "read", "summary": "s", "command": "c", "output": "o"}
    )
    for field in FIELDS:
        assert field in persisted, (
            f"{field} fell off the persisted tool-log entry: {persisted}"
        )
