"""M8-T341 — 工具名字有五个读者，只有一个问了家

M8-T336 定下"一个名字只有一种合法形态：干净的那种"，并在**派发**那一个地方
实现了它（`ToolCall.from_openai`）。但线上短语里的名字有**五个**读者：

| 读者 | 读到的是什么 |
| --- | --- |
| 派发（`ToolCall.from_openai`） | 干净的名字 ✓ |
| 本轮 trace（"本轮准备调用 N 个工具：…"） | **原始**名字 ✗ |
| 会话普查/检查点（`context._message_facts`） | **原始**名字 ✗ |
| 复核证据包（`completion._transcript_items`） | **原始**名字 ✗ |
| Anthropic 出站转译（`messages_to_anthropic`） | **原始**名字 ✗ |

于是同一个调用，在派发处叫 `read_file`，在 trace、普查、复核证据与发给
Anthropic 的报文里叫 `" read_file "`——最后那一处尤其糟：Anthropic 只认自己
声明过的工具名，带空格的名字会让整轮请求被 API 拒掉。

本门钉住：五个读者读到的都是同一个干净的名字；派发与那个"家"给出同一个
答案；控制组——干净的名字原样不动，名字写在顶层（没有 `function`）时也照样
解析得出来。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from minicc.agent.context import _message_facts
from minicc.agent.loop import run_agent
from minicc.agent.completion import _transcript_items
from minicc.llm.anthropic_provider import messages_to_anthropic
from minicc.llm.base import LLMResponse
from minicc.tools import build_registry
from minicc.tools.editor import Editor
from minicc.tools.schemas import ToolCall, tool_call_name


def _call(name: str, call_id: str = "c1") -> dict[str, Any]:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": "{}"},
    }


def test_the_home_and_the_dispatcher_agree() -> None:
    """The one home answers the same way the dispatcher does."""
    for name in ("read_file", " read_file ", "  ", ""):
        call = _call(name)
        assert tool_call_name(call) == ToolCall.from_openai(call).tool, name
    top_level = {"id": "c2", "name": " read_file "}
    assert tool_call_name(top_level) == "read_file", top_level


def test_the_round_trace_names_the_tool_the_way_the_dispatcher_does(
    tmp_path: Path,
) -> None:
    (tmp_path / "note.txt").write_text("hello\n", encoding="utf-8")

    class _Provider:
        def __init__(self) -> None:
            self.calls = 0

        async def chat(self, messages, tools=None, on_delta=None, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return LLMResponse(
                    tool_calls=[{
                        "id": "c1",
                        "type": "function",
                        "function": {"name": " read_file ", "arguments": '{"path": "note.txt"}'},
                    }],
                    finish_reason="tool_calls",
                )
            return LLMResponse(content="done", finish_reason="stop")

    traces: list[dict[str, Any]] = []
    asyncio.run(run_agent(
        _Provider(),
        build_registry(Editor(tmp_path)),
        [{"role": "user", "content": "读一下"}],
        on_trace=traces.append,
        should_allow=lambda _name, _call: True,
        workspace=tmp_path,
    ))
    started = next(
        (event for event in traces if event.get("code") == "tool_round_started"),
        None,
    )
    assert started is not None, [event.get("code") for event in traces]
    summary = str(started.get("summary") or "")
    assert "read_file" in summary, summary
    assert " read_file " not in summary, summary


def test_the_conversation_census_counts_the_clean_name() -> None:
    facts = _message_facts([{
        "role": "assistant",
        "content": "",
        "tool_calls": [_call(" read_file ")],
    }])
    names = {entry["name"] for entry in facts["tools"]}
    assert names == {"read_file"}, facts["tools"]


def test_the_review_transcript_names_the_tool_the_same_way() -> None:
    items = _transcript_items([{
        "role": "assistant",
        "content": "先读一下文件",
        "tool_calls": [_call(" read_file ")],
    }])
    assert items, "the transcript dropped the assistant round"
    assert items[0]["tool_calls"] == ["read_file"], items[0]


def test_the_anthropic_wire_carries_the_clean_name() -> None:
    """The name Anthropic sees has to be a name it knows."""
    _system, converted = messages_to_anthropic([{
        "role": "assistant",
        "content": "",
        "tool_calls": [_call(" read_file ")],
    }])
    block = converted[0]["content"][0]
    assert block["type"] == "tool_use", block
    assert block["name"] == "read_file", block


def test_a_clean_name_is_left_alone() -> None:
    """The control: the rule changes nothing for a well-formed call."""
    facts = _message_facts([{
        "role": "assistant",
        "content": "",
        "tool_calls": [_call("read_file")],
    }])
    assert {entry["name"] for entry in facts["tools"]} == {"read_file"}
    items = _transcript_items([{
        "role": "assistant",
        "content": "先读一下文件",
        "tool_calls": [_call("read_file")],
    }])
    assert items[0]["tool_calls"] == ["read_file"], items[0]
