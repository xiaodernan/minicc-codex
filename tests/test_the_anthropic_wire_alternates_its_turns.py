"""M8-T360 — Anthropic 这条线的回合必须交替：转换器是这条格式规则唯一的家

Anthropic 的 Messages 格式是**严格交替**的 user/assistant 序列——两条连续的
user 回合在这条线上没有表示。而产品**确实**会造出连续的回合：

* 循环在每轮开头注入视觉上下文 ✓ → 用户消息后面又来一条 user 消息 ✓
  （**带图片的任务必中** ✓）；
* 软预算收束时模型连着回了两段 ✓ → 两条 assistant 回合 ✓；
* 一轮被中断 ✓ → 用户消息留在历史里没人回答 ✓。

而转换器**已经**为"多个 tool_result 合成一个 user 回合"实现了同一条规则 ✓
（`flush_results` ✓）——只是没对文本/图片回合用 ✗。

本门钉住：转出来的回合**严格交替** ✓；合并**不丢内容** ✓（图片、tool_result ✓
都还在 ✓）；控制组——本来就交替的对话**原样不动** ✓（tool_result 回合仍然
独立 ✓）。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from minicc.agent.loop import run_agent
from minicc.llm.anthropic_provider import messages_to_anthropic
from minicc.llm.base import LLMResponse
from minicc.tools import build_registry
from minicc.tools.editor import Editor

IMAGE_URL = "data:image/png;base64,iVBORw0KGgo="
IMAGE_PART = {"type": "image_url", "image_url": {"url": IMAGE_URL}}


def _same_role_pairs(converted: list[dict[str, Any]]) -> list[tuple[str, str]]:
    return [
        (str(converted[i].get("role")), str(converted[i + 1].get("role")))
        for i in range(len(converted) - 1)
        if converted[i].get("role") == converted[i + 1].get("role")
    ]


def _blocks(converted: list[dict[str, Any]]) -> list[Any]:
    out: list[Any] = []
    for entry in converted:
        content = entry.get("content")
        if isinstance(content, list):
            out.extend(content)
        elif isinstance(content, str):
            out.append({"type": "text", "text": content})
    return out


def test_the_vision_context_keeps_the_wire_alternating(tmp_path: Path) -> None:
    """The product path: the loop appends the vision context, the wire must alternate."""
    class _Provider:
        def __init__(self) -> None:
            self.calls = 0

        async def chat(self, messages, tools=None, on_delta=None, **kwargs):
            self.calls += 1
            return LLMResponse(content="done", finish_reason="stop")

    messages: list[dict[str, Any]] = [{"role": "user", "content": "看这张图，改成图里的布局"}]
    asyncio.run(run_agent(
        _Provider(),
        build_registry(Editor(tmp_path)),
        messages,
        max_turns=3,
        vision_context=[IMAGE_PART],
        should_allow=lambda _name, _call: True,
        workspace=tmp_path,
    ))

    # The product really did produce two user turns in a row.
    assert sum(1 for message in messages if message.get("role") == "user") >= 2, messages

    _system, converted = messages_to_anthropic(messages)
    assert not _same_role_pairs(converted), converted
    # The merge must not cost us the image.
    assert any(
        isinstance(block, dict) and block.get("type") == "image"
        for block in _blocks(converted)
    ), converted


def test_two_assistant_turns_become_one() -> None:
    """The soft-budget wrap produces two assistant turns."""
    _system, converted = messages_to_anthropic([
        {"role": "system", "content": "s"},
        {"role": "user", "content": "干活"},
        {"role": "assistant", "content": "第一段"},
        {"role": "assistant", "content": "收束段"},
    ])
    assert not _same_role_pairs(converted), converted
    texts = [
        block.get("text")
        for block in _blocks(converted)
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    assert "第一段" in texts and "收束段" in texts, texts


def test_an_alternating_conversation_is_untouched() -> None:
    """The control: a normal conversation (with a tool result turn) stays as it was."""
    history = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "读一下"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": "t1",
                "type": "function",
                "function": {"name": "read_file", "arguments": json.dumps({"path": "a.py"})},
            }],
        },
        {"role": "tool", "tool_call_id": "t1", "content": "文件内容"},
        {"role": "assistant", "content": "读完了"},
    ]
    _system, converted = messages_to_anthropic(history)
    assert [entry["role"] for entry in converted] == ["user", "assistant", "user", "assistant"], converted
    # The tool result is still its own turn, and its payload survived.
    tool_turn = converted[2]
    assert isinstance(tool_turn.get("content"), list), tool_turn
    assert tool_turn["content"][0].get("type") == "tool_result", tool_turn
