"""M8-T347 — 名字要在**源头**收拾干净，而不是让每个读者各自擦屁股

M8-T341 给"名字只有一种合法形态"立了家（`tool_call_name`），并让五个读者改问它。
但还有两条路没被覆盖：

* **chat-completions 路径把历史原样发出去**——历史里存的是 provider 给的原始
  字典，名字带空格就带到了线上；
* 两条**另建的报文**（信封 wire、Responses wire）各自渲染历史里的调用，名字
  也是原始的。

于是同一个调用，模型看到的历史、发给 API 的报文、落盘的会话日志，可能是三种
拼写。

正确的做法不是"再多擦两个地方"，而是**在源头收拾**：assistant 轮次进历史时，
名字就已经是干净的那种（与派发器用的那个一致）。于是历史、日志、chat 报文、
信封报文、Responses 报文、Anthropic 报文——**全都**是同一个拼写。

本门钉住：四种线上形态都带着同一个干净的名字。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from minicc.agent.loop import run_agent
from minicc.llm.base import LLMResponse
from minicc.llm.openai_provider import OpenAICompatibleProvider
from minicc.tools import build_registry
from minicc.tools.editor import Editor


def _call(name: str, call_id: str = "c1") -> dict[str, Any]:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": "{}"},
    }


def _assistant_message() -> dict[str, Any]:
    return {"role": "assistant", "content": "", "tool_calls": [_call(" read_file ")]}


def test_the_chat_wire_carries_the_clean_name(tmp_path: Path) -> None:
    """The observable site: what the provider is asked to send."""
    (tmp_path / "note.txt").write_text("hi\n", encoding="utf-8")
    seen: list[list[dict[str, Any]]] = []

    class _Provider:
        def __init__(self) -> None:
            self.calls = 0

        async def chat(self, messages, tools=None, on_delta=None, **kwargs):
            self.calls += 1
            seen.append([dict(message) for message in messages])
            if self.calls == 1:
                return LLMResponse(
                    tool_calls=[{
                        "id": "c1",
                        "type": "function",
                        "function": {"name": " read_file ", "arguments": json.dumps({"path": "note.txt"})},
                    }],
                    finish_reason="tool_calls",
                )
            return LLMResponse(content="done", finish_reason="stop")

    provider = _Provider()
    asyncio.run(run_agent(
        provider,
        build_registry(Editor(tmp_path)),
        [{"role": "user", "content": "读一下"}],
        should_allow=lambda _name, _call: True,
        workspace=tmp_path,
    ))
    assistant = [
        message
        for round_messages in seen
        for message in round_messages
        if message.get("role") == "assistant" and message.get("tool_calls")
    ]
    assert assistant, "the assistant round never reached the wire"
    names = [
        str((call.get("function") or {}).get("name"))
        for message in assistant
        for call in message["tool_calls"]
    ]
    assert names == ["read_file"], names


def test_the_envelope_wire_carries_the_clean_name() -> None:
    wire = OpenAICompatibleProvider._to_envelope_wire(
        None,
        [_assistant_message()],
        [{"type": "function", "function": {"name": "read_file", "description": "", "parameters": {}}}],
    )
    rendered = "\n".join(str(part) for part in wire)
    assert "read_file" in rendered, rendered
    assert " read_file " not in rendered, rendered


def test_the_responses_wire_carries_the_clean_name() -> None:
    items = OpenAICompatibleProvider._to_responses_input(None, [_assistant_message()], None)
    calls = [item for item in items if item.get("type") == "function_call"]
    assert calls, items
    assert [str(item.get("name")) for item in calls] == ["read_file"], calls
