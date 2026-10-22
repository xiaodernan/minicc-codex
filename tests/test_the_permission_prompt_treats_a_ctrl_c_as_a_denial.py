"""M8-T362 — 权限询问处的 Ctrl-C 是"这一次不行"，不是"整轮作废"

CLI 的权限询问问的是**这一次操作**（"允许此次操作？" ✓）。于是"没人回答"只有一
种结局：**拒绝这一次 ✓，这一轮继续** ✓——EOF（管道里没人应答 ✓）就是这么处理的
✓。

而 Ctrl-C 从 gate 里**冲了出去** ✗：它不是"拒绝这一次" ✗，而是把**整轮**掀了 ✓
（实测：`ESCAPED: KeyboardInterrupt` ✓）——agent 前面已经做的那一轮（读了文件 ✓、
跑了测试 ✓）全白费 ✓。

同一个 gate、同一种"没有肯定回答" ✓，两种结局 ✗。

本门钉住：Ctrl-C = **拒绝这一次** ✓（gate 返回 False ✓）；控制组——EOF 的处理
不变 ✓；端到端——一次写着文件的请求被 Ctrl-C 拒掉之后，**这一轮照样走完** ✓
（模型拿到拒绝理由 ✓，任务正常结束 ✓）。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from minicc.config import Config
from minicc.llm.base import LLMResponse
from minicc.main import _permission_gate
from minicc.tools import ToolCall, build_registry
from minicc.tools.editor import Editor


def _config() -> Config:
    return Config(base_url="http://localhost:1/v1", api_key="k", model="m")


def _write_call() -> ToolCall:
    return ToolCall(
        tool="write_file",
        arguments={"path": "a.py", "content": "x=1"},
        call_id="c1",
    )


def test_ctrl_c_at_the_permission_prompt_denies_that_one_call(
    tmp_path: Path, monkeypatch
) -> None:
    def _boom(*_args, **_kwargs):
        raise KeyboardInterrupt()

    monkeypatch.setattr("builtins.input", _boom)
    gate = _permission_gate(
        _config(),
        build_registry(Editor(tmp_path)),
        "default",
        session_id="s1",
        workspace=tmp_path,
    )
    try:
        allowed = gate("write_file", _write_call())
    except KeyboardInterrupt:
        pytest.fail("the interrupt escaped the gate: it ended the whole turn")
    assert allowed is False


def test_the_end_of_input_still_denies_that_one_call(
    tmp_path: Path, monkeypatch
) -> None:
    """The control: the EOF answer is unchanged."""

    def _eof(*_args, **_kwargs):
        raise EOFError()

    monkeypatch.setattr("builtins.input", _eof)
    gate = _permission_gate(
        _config(),
        build_registry(Editor(tmp_path)),
        "default",
        session_id="s1",
        workspace=tmp_path,
    )
    assert gate("write_file", _write_call()) is False


def test_the_turn_keeps_going_after_a_ctrl_c_denial(tmp_path: Path, monkeypatch) -> None:
    """The observable: the denial is one tool result, not the end of the turn."""
    from minicc.agent.loop import run_agent

    def _boom(*_args, **_kwargs):
        raise KeyboardInterrupt()

    monkeypatch.setattr("builtins.input", _boom)

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
                        "function": {
                            "name": "write_file",
                            "arguments": json.dumps({"path": "a.py", "content": "x=1"}),
                        },
                    }],
                    finish_reason="tool_calls",
                )
            return LLMResponse(content="好的，没有写。", finish_reason="stop")

    seen: list[Any] = []

    def on_tool(call: Any, result: Any) -> None:
        seen.append(result)

    gate = _permission_gate(
        _config(),
        build_registry(Editor(tmp_path)),
        "default",
        session_id="s1",
        workspace=tmp_path,
    )
    result = None
    try:
        result = asyncio.run(run_agent(
            _Provider(),
            build_registry(Editor(tmp_path)),
            [{"role": "user", "content": "写个文件"}],
            max_turns=4,
            on_tool=on_tool,
            should_allow=gate,
            workspace=tmp_path,
        ))
    except KeyboardInterrupt:
        pytest.fail("the interrupt escaped the gate: the whole turn was lost")

    assert result is not None

    assert result.error is None, result.error
    assert seen, "the write was never attempted"
    assert seen[0].status == "denied", seen[0].status
    assert not (tmp_path / "a.py").exists()
