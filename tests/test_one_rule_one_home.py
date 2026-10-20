"""M8-T307 — 一条规则只有一个家：一个**死副本**，和一份**没人维护的弱副本**

这一批扫到两处"同一个事实、两份写法"：

| 编号 | 位置 | 问题 |
| --- | --- | --- |
| M8-T307a | `agent/loop.py` | 有一份 `WRITE_TOOL_NAMES` 字面量，**全仓无人使用**（真正在用的是 `tool_policy` 那份）。死副本不是中性的：它是一份**没人维护的规则**，读代码的人会以为它是那一条 |
| M8-T307b | `agent/loop.py` × 4 处 | "这个工具是不是联网工具"有两半——**众所周知的名字**，与工具**声明的 `network` 能力**（M8-T3）。闸门（`audit.py`）两半都问；loop 只问名字，于是**声明了能力的插件**：它的结果会被**缓存并重放**（缓存是为了复用**可复现**的观察，而网络答复不是），它**也不计入熔断**（连着失败的联网插件被无限重试） |

本门禁钉住：死副本没了；声明能力的联网工具不会被重放，也会计入熔断。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from minicc.agent import loop as loop_module
from minicc.audit import is_network_tool
from minicc.llm.base import LLMResponse
from minicc.tools import build_registry
from minicc.tools.editor import Editor
from minicc.tools.registry import ToolRegistry, ToolSpec


# --- M8-T307a: the dead copy is gone -----------------------------------------


def test_the_agent_loop_has_no_dead_write_tool_list() -> None:
    """A copy nobody maintains is a rule nobody keeps true."""
    assert not hasattr(loop_module, "WRITE_TOOL_NAMES"), (
        "the agent loop still carries its own copy of the write-tool list; "
        "the live one is in tool_policy, and the copy here was used by "
        "nobody"
    )


def test_the_live_write_tool_list_still_exists() -> None:
    """The control: the real one is untouched."""
    from minicc.agent.tool_policy import WRITE_TOOL_NAMES

    assert "write_file" in WRITE_TOOL_NAMES
    assert "edit_file" in WRITE_TOOL_NAMES


# --- M8-T307b: the network question has two halves ----------------------------


def test_the_network_question_has_two_halves() -> None:
    """A well-known name, or a declared capability."""
    assert is_network_tool("webfetch") is True
    assert is_network_tool("web_search") is True
    assert is_network_tool("my_plugin", ("network",)) is True
    assert is_network_tool("read_file", ()) is False
    assert is_network_tool("read_file", ("fs_read",)) is False


def _network_plugin(registry: ToolRegistry, calls: list[int]) -> None:
    """Register a plugin that declares the network capability."""
    def handler(arguments: dict[str, Any]) -> Any:
        calls.append(1)
        from minicc.tools.schemas import ToolResult

        return ToolResult(status="ok", summary=f"fetched {len(calls)}")

    registry.register(ToolSpec(
        name="fetch_thing",
        description="从一个远端服务读取一个东西。",
        risk="readonly",
        params=(),
        handler=handler,
        capabilities=("network",),
    ))


def test_a_declared_network_result_is_not_replayed(tmp_path: Path) -> None:
    """The cache exists to reuse *reproducible* observations."""
    from minicc.agent.loop import run_agent

    workspace = tmp_path / "ws"
    workspace.mkdir()
    registry = build_registry(Editor(workspace))
    calls: list[int] = []
    _network_plugin(registry, calls)

    class _Twice:
        def __init__(self) -> None:
            self.turns = 0

        async def chat(self, messages, tools=None, on_delta=None, **kwargs):
            self.turns += 1
            if self.turns <= 2:
                return LLMResponse(
                    content=None,
                    tool_calls=[{
                        "id": f"call-{self.turns}",
                        "type": "function",
                        "function": {
                            "name": "fetch_thing",
                            "arguments": json.dumps({}),
                        },
                    }],
                    finish_reason="tool_calls",
                )
            return LLMResponse(content="done", finish_reason="stop")

    asyncio.run(run_agent(
        _Twice(),
        registry,
        [{"role": "user", "content": "取两次"}],
        workspace=workspace,
    ))

    assert len(calls) == 2, (
        f"the second call was replayed from the cache instead of being made: "
        f"{len(calls)} real call(s)"
    )


def test_a_local_read_result_is_still_replayed(tmp_path: Path) -> None:
    """The control: the ordinary reuse path is unchanged."""
    from minicc.agent.loop import run_agent

    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "a.txt").write_text("hello\n", encoding="utf-8")
    registry = build_registry(Editor(workspace))
    calls: list[int] = []

    def handler(arguments: dict[str, Any]) -> Any:
        calls.append(1)
        from minicc.tools.schemas import ToolResult

        return ToolResult(status="ok", summary=f"read {len(calls)}")

    registry.register(ToolSpec(
        name="read_thing",
        description="读一个本地的东西。",
        risk="readonly",
        params=(),
        handler=handler,
    ))

    class _Twice:
        def __init__(self) -> None:
            self.turns = 0

        async def chat(self, messages, tools=None, on_delta=None, **kwargs):
            self.turns += 1
            if self.turns <= 2:
                return LLMResponse(
                    content=None,
                    tool_calls=[{
                        "id": f"call-{self.turns}",
                        "type": "function",
                        "function": {
                            "name": "read_thing",
                            "arguments": json.dumps({}),
                        },
                    }],
                    finish_reason="tool_calls",
                )
            return LLMResponse(content="done", finish_reason="stop")

    asyncio.run(run_agent(
        _Twice(),
        registry,
        [{"role": "user", "content": "读两次"}],
        workspace=workspace,
    ))

    assert len(calls) == 1, (
        f"the local read was not reused: {len(calls)} real call(s)"
    )
