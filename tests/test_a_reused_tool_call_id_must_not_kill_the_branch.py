"""M8-T295 — 工具调用 id 被复用时，回退/分叉不能切出非法历史

原生工具协议是**按轮次**结算的：一条 `tool` 结果回答的是它**前面那一轮**
assistant 的调用，而兼容网关**可以在后面的轮次里复用同一个 id**。

会话的切口逻辑原来把**整段**历史里的 assistant 调用 id 收成一个集合，再用
**任意一条**同 id 的结果去抵消它。于是：

* 第一轮的结果把**第二轮**那个还没应答的调用抵消掉了；
* 切口因此没有被延长；
* 分叉/回退出来的历史**以一个没有结果的 assistant 工具轮次结尾**——而
  模型 API 对这种历史**第一轮就拒绝**。

也就是说：分支是"一出生就死的"。而 `agent/context.validate_tool_protocol`
（协议的权威实现）一直是**按轮次**判的——同一件事实，两处读法。

本门禁钉住：切口按**轮次**延长；产出的历史能通过协议校验。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from minicc.agent.context import validate_tool_protocol
from minicc.session import SessionStore


def _reused_id_history() -> list[dict[str, object]]:
    """Two rounds that use the **same** tool-call id."""
    return [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "第一件事"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "call_1", "type": "function",
                           "function": {"name": "read_file", "arguments": "{}"}}],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "第一次的结果"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "call_1", "type": "function",
                           "function": {"name": "read_file", "arguments": "{}"}}],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "第二次的结果"},
        {"role": "assistant", "content": "好了"},
    ]


def test_rewinding_into_a_reused_id_round_carries_its_result(tmp_path: Path) -> None:
    """The cut has to be extended past the second round's unanswered call."""
    store = SessionStore(tmp_path, "reuse-rewind")
    store.save(_reused_id_history())

    result = store.rewind(5)
    assert result["kept"] == 6, (
        "the cut stopped on an assistant turn whose tool result was left behind"
    )


def test_the_rewound_history_passes_the_protocol_check(tmp_path: Path) -> None:
    """The branch must be one the model API accepts."""
    store = SessionStore(tmp_path, "reuse-valid")
    store.save(_reused_id_history())

    store.rewind(5)
    messages = store.load("第一件事")
    validate_tool_protocol([item for item in messages if isinstance(item, dict)])


def test_forking_into_a_reused_id_round_carries_its_result(tmp_path: Path) -> None:
    """The same rule on the fork path."""
    store = SessionStore(tmp_path, "reuse-fork")
    store.save(_reused_id_history())

    forked = store.fork(5)
    messages = forked.load("第一件事")
    validate_tool_protocol([item for item in messages if isinstance(item, dict)])
    assert messages, "the fork produced an empty history"


def test_an_ordinary_round_is_unaffected(tmp_path: Path) -> None:
    """The control: a history without id reuse behaves as before."""
    store = SessionStore(tmp_path, "reuse-control")
    store.save([
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "问"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "call_a", "type": "function",
                           "function": {"name": "read_file", "arguments": "{}"}}],
        },
        {"role": "tool", "tool_call_id": "call_a", "content": "结果"},
        {"role": "assistant", "content": "好了"},
    ])
    result = store.rewind(3)
    assert result["kept"] == 4
