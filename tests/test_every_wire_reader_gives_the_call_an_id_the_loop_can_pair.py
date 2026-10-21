"""M8-T356 — 工具调用的 id 也要修：两条线不许对同一次回答给出两种行为

网关偶尔**复用同一个 id**（或者干脆不给 id）。工具结果按 id 配对
（`tool_result_msg` / `repair_interrupted_tool_rounds`），所以重复的 id 会
**丢结果或把结果送错地方**；而空 id 会让协议校验器直接拒收这段历史
（"调用 ID 为空或重复"）——**整轮崩掉**。

OpenAI 兼容的那条线一直有修复（`_unique_tool_call_id`：空 id 给一个兜底名、
重复 id 给 `<base>-dup<N>`）。**原生 Anthropic 那条线没有**：

| 线 | 两个相同 id 的块 | 没有 id 的块 |
| --- | --- | --- |
| OpenAI 兼容 | `same` / `same-dup2` ✓ | `call-0` ✓ |
| Anthropic | `same` / `same` ✗ | `""` ✗ |

同一个畸形网关回答，两条线两种行为——M8-T334 那一族的**又一次**。

本门钉住：两条线都给出**非空且互不相同**的 id；端到端——一份 id 重复的畸形
回答不能让整轮崩掉（协议校验器不再拒收历史）。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from minicc.agent.loop import run_agent
from minicc.llm.anthropic_provider import _sse_to_llm, response_to_llm
from minicc.llm.base import LLMResponse
from minicc.tools import build_registry
from minicc.tools.editor import Editor


def _payload(*blocks: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": "claude-x",
        "stop_reason": "tool_use",
        "content": list(blocks),
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }


def _tool_block(call_id: str, name: str = "read_file") -> dict[str, Any]:
    return {"type": "tool_use", "id": call_id, "name": name, "input": {"path": "a.py"}}


def _sse_parsed(*ids: str) -> dict[str, Any]:
    tools: dict[int, dict[str, str]] = {}
    for index, call_id in enumerate(ids, start=1):
        tools[index] = {"id": call_id, "name": "read_file", "json": '{"path": "a.py"}'}
    return {
        "text": "",
        "tools": tools,
        "usage": {},
        "stop_reason": "tool_use",
        "model": "claude-x",
    }


def test_the_anthropic_json_path_gives_unique_non_empty_ids() -> None:
    response = response_to_llm(
        _payload(_tool_block("same"), _tool_block("same"), _tool_block("")),
        "claude-x",
    )
    ids = [str(call["id"]) for call in response.tool_calls]
    assert len(ids) == 3, ids
    assert all(ids), ids
    assert len(set(ids)) == len(ids), ids


def test_the_anthropic_stream_path_gives_unique_non_empty_ids() -> None:
    response = _sse_to_llm(_sse_parsed("same", "same", ""), "claude-x")
    ids = [str(call["id"]) for call in response.tool_calls]
    assert len(ids) == 3, ids
    assert all(ids), ids
    assert len(set(ids)) == len(ids), ids


def test_a_malformed_answer_does_not_kill_the_turn(tmp_path: Path) -> None:
    """The observable: the protocol validator never sees a broken history."""
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    malformed = _payload(_tool_block("same"), _tool_block("same"))

    class _Gateway:
        """A gateway that reuses one id, read through the Anthropic wire."""

        def __init__(self) -> None:
            self.calls = 0

        async def chat(self, messages, tools=None, on_delta=None, **kwargs):
            self.calls += 1
            if self.calls == 1:
                parsed = response_to_llm(malformed, "claude-x")
                return LLMResponse(
                    content=parsed.content,
                    tool_calls=parsed.tool_calls,
                    finish_reason="tool_calls",
                )
            return LLMResponse(content="done", finish_reason="stop")

    provider = _Gateway()
    result = asyncio.run(run_agent(
        provider,
        build_registry(Editor(tmp_path)),
        [{"role": "user", "content": "读一下"}],
        max_turns=4,
        should_allow=lambda _name, _call: True,
        workspace=tmp_path,
    ))
    assert result.error is None, result.error
    assert provider.calls == 2, provider.calls
