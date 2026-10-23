"""M8-T417 — tool 消息形状有家而邻居手抄：interrupted 修复各写一份三键 dict"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/llm/base.py"
READER = "minicc/agent/context.py"

FIELDS = {"role", "tool_call_id", "content"}


def test_the_home_builds_the_message() -> None:
    """The constructor owns the three keys of a tool result message."""
    from minicc.llm.base import tool_result_msg

    assert tool_result_msg("call-1", "ok") == {
        "role": "tool", "tool_call_id": "call-1", "content": "ok",
    }


def test_the_interrupted_repair_asks_the_home() -> None:
    """The one hand-written copy now goes through the constructor."""
    source = (PACKAGE / READER.removeprefix("minicc/")).read_text(encoding="utf-8")
    assert "tool_result_msg" in source, (
        "the interrupted-round repair must ask the one home for the tool message"
    )


def test_the_repair_still_writes_the_unknown_result() -> None:
    """Behavior unchanged: the repaired round carries role, id and content."""
    from minicc.agent.context import repair_interrupted_tool_rounds

    messages: list[dict[str, Any]] = [{
        "role": "assistant", "content": "",
        "tool_calls": [{"id": "c1", "type": "function",
                        "function": {"name": "tree", "arguments": "{}"}}],
    }]
    assert repair_interrupted_tool_rounds(messages) == 1
    repaired = messages[-1]
    assert repaired["role"] == "tool"
    assert repaired["tool_call_id"] == "c1"
    assert "INTERRUPTED_TOOL_RESULT" in repaired["content"]


def test_the_message_is_spelled_exactly_once_in_the_package() -> None:
    """One literal, in the home - the copy beside it was the T407 lesson again.

    ``tool_result_msg`` had existed for years; the repair path still spelled
    the three keys by hand, because the helper's name says what it is *for*
    (a tool result message) and the repair's author did not read that as
    "my case too".  A shape named for its *shape* is what makes the second
    writer see the home.
    """
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        relative = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            keys = {
                key.value
                for key in node.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
            if keys == FIELDS:
                offenders.append(f"{relative}:{node.lineno}")
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the tool message shape is spelled by hand outside its one home: "
        + ", ".join(offenders)
    )
