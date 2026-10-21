"""M8-T357 — 同一份坏参数，两条线要给出同一个诊断

网关偶尔吐出**不是 JSON 的参数**（流式增量拼坏了 ✓）。两条线对它的处理原本
不同：

* OpenAI 兼容那条线把**原始串**交给 agent 循环 ✓ → 循环的统一修复
  （`ToolCall.from_openai`）把它读成"参数不是合法 JSON 对象" ✓ →
  `[INVALID_TOOL_ARGUMENTS] …` ✓；
* Anthropic 的**流式**路径把它包成 `{"_raw": "…"}` ✓ → 循环看到的是**合法
  JSON** ✓ → 于是注册表报的是"缺少必填参数 'path'" ✓。

第二条是**误导性的诊断**：参数根本没缺，是坏 JSON ✗。模型收到的是"你少给了
参数"，于是照着这个错诊断重发同一个坏调用 ✗（白费一轮 ✓）。

本门钉住：同一份坏参数，两条线给出**同一个**诊断（都是"参数不是合法 JSON" ✓）。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from minicc.agent.loop import run_agent
from minicc.llm.anthropic_provider import _sse_to_llm
from minicc.llm.base import LLMResponse
from minicc.tools import build_registry
from minicc.tools.editor import Editor


def _openai_style_call(arguments: str) -> dict[str, Any]:
    """The OpenAI-compatible wire: the raw text travels as it is."""
    return {
        "id": "c1",
        "type": "function",
        "function": {"name": "read_file", "arguments": arguments},
    }


def _anthropic_style_call() -> dict[str, Any]:
    """The Anthropic stream wire: the provider parses the broken arguments."""
    parsed = _sse_to_llm(
        {
            "text": "",
            "tools": {1: {"id": "c1", "name": "read_file", "json": "{not json"}},
            "usage": {},
            "stop_reason": "tool_use",
            "model": "claude-x",
        },
        "claude-x",
    )
    return parsed.tool_calls[0]


def _run(tmp_path: Path, call: dict[str, Any]) -> str:
    class _Gateway:
        def __init__(self) -> None:
            self.calls = 0

        async def chat(self, messages, tools=None, on_delta=None, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return LLMResponse(tool_calls=[call], finish_reason="tool_calls")
            return LLMResponse(content="done", finish_reason="stop")

    seen: list[str] = []

    def on_tool(tool_call: Any, result: Any) -> None:
        seen.append(result.summary or "")

    asyncio.run(run_agent(
        _Gateway(),
        build_registry(Editor(tmp_path)),
        [{"role": "user", "content": "读一下"}],
        max_turns=3,
        on_tool=on_tool,
        should_allow=lambda _name, _call: True,
        workspace=tmp_path,
    ))
    return seen[0] if seen else ""


def test_both_wires_report_a_malformed_argument_the_same_way(tmp_path: Path) -> None:
    raw = _run(tmp_path, _openai_style_call('{"path": "a.py"'))
    assert "INVALID_TOOL_ARGUMENTS" in raw, raw

    streamed = _run(tmp_path, _anthropic_style_call())
    assert "INVALID_TOOL_ARGUMENTS" in streamed, streamed
    assert "缺少必填参数" not in streamed, streamed
