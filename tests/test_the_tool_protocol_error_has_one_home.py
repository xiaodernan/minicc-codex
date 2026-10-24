"""M8-T515 — 工具上下文协议判词六个家：一个前缀，六种违约

`validate_tool_protocol` 用六条判词拒绝畸形的原生工具轮次，六条都手拼
了同一个前缀 `工具上下文协议无效：`，其中两条还各自手拼了 `第 N 条` 的
位置约定。前缀是这一族拒绝的**契约标记**——loop 的预检、修复通道、测试
都按它匹配；哪天某一条改了措词，这条违约就对不上它的家族，而按前缀匹
配的读者只会看到半族红、半族静默。

家安在 `minicc/agent/context.py`，`validate_tool_protocol` 隔壁：前缀常
量 + 一个组装函数，0 基位置转 1 基句子的约定只存在一份。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from minicc.agent.context import (
    TOOL_PROTOCOL_ERROR_PREFIX,
    tool_protocol_error,
    validate_tool_protocol,
)

REPO = Path(__file__).resolve().parents[1]
HOME = "minicc/agent/context.py"


def test_the_home_pins_the_prefix_and_the_position_convention() -> None:
    assert TOOL_PROTOCOL_ERROR_PREFIX == "工具上下文协议无效："
    assert tool_protocol_error("消息不是对象", 0) == "工具上下文协议无效：第 1 条消息不是对象"
    assert tool_protocol_error("消息不是对象", 4) == "工具上下文协议无效：第 5 条消息不是对象"
    # No position: the sentence carries no 第 N 条 clause at all.
    assert tool_protocol_error("工具轮次缺少结果") == "工具上下文协议无效：工具轮次缺少结果"


def test_the_prefix_is_spelled_exactly_once() -> None:
    """Skeleton-and-prefix, the way T514-495 taught: a hand-spelled copy
    inside an f-string has no bare Constant to find, and its skeleton is
    never equal to the prefix - only ever prefixed by it."""
    hits: list[tuple[str, int]] = []
    for path in sorted((REPO / "minicc").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        inside_fstring: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                for child in ast.iter_child_nodes(node):
                    inside_fstring.add(id(child))
        for node in ast.walk(tree):
            if id(node) in inside_fstring:
                continue
            if isinstance(node, ast.JoinedStr):
                skeleton = "".join(
                    part.value
                    for part in node.values
                    if isinstance(part, ast.Constant) and isinstance(part.value, str)
                )
                if skeleton.startswith(TOOL_PROTOCOL_ERROR_PREFIX):
                    hits.append((path.relative_to(REPO).as_posix(), node.lineno))
            elif (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and node.value.startswith(TOOL_PROTOCOL_ERROR_PREFIX)):
                hits.append((path.relative_to(REPO).as_posix(), node.lineno))
    assert len(hits) == 1 and hits[0][0] == HOME, hits


def _assistant(*ids: str) -> dict:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": call_id, "type": "function",
             "function": {"name": "read_file", "arguments": "{}"}}
            for call_id in ids
        ],
    }


def _result(call_id: str) -> dict:
    return {"role": "tool", "tool_call_id": call_id, "content": "ok"}


def test_every_judgment_asks_the_home() -> None:
    cases: list[tuple[list, str]] = [
        (["not a message"], "工具上下文协议无效：第 1 条消息不是对象"),
        ([_assistant("c1"), _result("cX")], "工具上下文协议无效：第 2 条结果没有对应调用"),
        ([_assistant("c1"), {"role": "user", "content": "hi"}], "工具上下文协议无效：工具轮次缺少结果"),
        ([{"role": "user", "content": "hi", "tool_calls": [{"id": "c1"}]}],
         "工具上下文协议无效：调用必须属于 assistant 轮次"),
        ([_assistant("c1", "c1")], "工具上下文协议无效：调用 ID 为空或重复"),
        ([_assistant("c1")], "工具上下文协议无效：最后一个工具轮次缺少结果"),
    ]
    for messages, expected in cases:
        with pytest.raises(ValueError) as excinfo:
            validate_tool_protocol(messages)
        assert str(excinfo.value) == expected, (messages, str(excinfo.value))


def test_a_valid_history_is_still_accepted() -> None:
    """The control: the ordinary round passes untouched."""
    validate_tool_protocol([
        {"role": "user", "content": "hi"},
        _assistant("c1"),
        _result("c1"),
        {"role": "assistant", "content": "done"},
    ])
