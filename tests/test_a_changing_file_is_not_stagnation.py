"""M8-T355 — 停滞判据也要认文件身份：世界在变，就不是原地打转

停滞守卫判"这一轮是不是又来了一遍"，靠的是**调用的形状**（工具 + 参数）——
这本身是对的：**输出**变了不算数（一个会变的输出不该把没变的路径伪装成进展 ✓）。

但**目标文件变了**是另一回事：agent 反复读一个**正在被改**的文件，每读一次都
拿到新内容（实测三次读三个不同 digest ✓），那不是"原地打转"，而是"在跟进"。

而旧判据只认形状，于是：

* 守卫开火（`stagnation_replan` ✓）；
* agent 被推进恢复探针 ✓（`recovery_probe_finished` ✓）；
* 然后**出不来**（`recovery_required_before_finish` 连续三次 ✓）——明明在干活的
  任务被卡在恢复循环里，直到轮次耗尽。

本门钉住：目标在变时，**不算**停滞（守卫不开火、任务能交付）；控制组——目标
不变时，同样的重复**仍然**算停滞（守卫照旧开火）。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from minicc.agent.loop import run_agent
from minicc.llm.base import LLMResponse
from minicc.tools import build_registry
from minicc.tools.editor import Editor


class _ReadsThreeTimes:
    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, messages, tools=None, on_delta=None, **kwargs):
        self.calls += 1
        if self.calls <= 3:
            return LLMResponse(
                tool_calls=[{
                    "id": f"r-{self.calls}",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": json.dumps({"path": "notes.md"}),
                    },
                }],
                finish_reason="tool_calls",
            )
        return LLMResponse(content="done", finish_reason="stop")


def _run(tmp_path: Path, *, keep_changing: bool) -> tuple[list[str], list[dict[str, Any]]]:
    workspace = tmp_path / "ws"
    workspace.mkdir(parents=True, exist_ok=True)
    target = workspace / "notes.md"
    target.write_text("v0\n", encoding="utf-8")
    traces: list[dict[str, Any]] = []

    def on_tool(call: Any, result: Any) -> None:
        if keep_changing:
            # Somebody keeps editing the file the agent is reading.
            target.write_text(f"v{len(result.summary or '')}\n", encoding="utf-8")

    asyncio.run(run_agent(
        _ReadsThreeTimes(),
        build_registry(Editor(workspace)),
        [{"role": "user", "content": "读一下笔记"}],
        max_turns=8,
        on_tool=on_tool,
        on_trace=traces.append,
        should_allow=lambda _name, _call: True,
        workspace=workspace,
    ))
    return [str(event.get("code") or "") for event in traces], traces


def test_a_changing_file_is_not_stagnation(tmp_path: Path) -> None:
    """The observable: the guard stays closed and the task can finish."""
    codes, _traces = _run(tmp_path, keep_changing=True)
    assert "stagnation_replan" not in codes, codes
    assert "recovery_required_before_finish" not in codes, codes


def test_an_unchanged_file_still_counts_as_a_repetition(tmp_path: Path) -> None:
    """The control: the guard still opens for a genuinely repeated round."""
    codes, _traces = _run(tmp_path, keep_changing=False)
    assert "stagnation_replan" in codes, codes
