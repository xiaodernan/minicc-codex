"""M8-T354 — 备忘只配回答它取自的那个文件

agent 重复调用同一个只读工具时，循环会**重放**上一次的结果（省 token，也让模型
知道"这个证据你已经有了"）。但那份备忘**不认文件**：

1. agent 读了 `notes.md`（内容 ORIGINAL）；
2. 用户（或别的进程）把 `notes.md` 改成了 CHANGED；
3. agent 再读一次 → 备忘把**旧内容**交回去（实测："ORIGINAL"）；
4. 而且备忘只会重放——**新的内容再也读不到**（直到 agent 自己写一次，缓存才被
   清空）。

检索索引的同一类"备忘"是认文件身份的（`ino, mtime_ns, ctime_ns, size`，
M8-T292）——**同一条规则只在一处落地**。

本门钉住：文件在外部被改过之后，agent 读到的是**新内容**；控制组——文件没变
时，重放照旧（省 token 这件事没有丢）。
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


class _ReadsTwice:
    """The model reads the same file twice, in one run."""

    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, messages, tools=None, on_delta=None, **kwargs):
        self.calls += 1
        if self.calls <= 2:
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


def _run(
    tmp_path: Path,
    *,
    change_after_first_read: bool,
) -> list[tuple[str, str]]:
    workspace = tmp_path / "ws"
    workspace.mkdir(parents=True, exist_ok=True)
    target = workspace / "notes.md"
    target.write_text("ORIGINAL\n", encoding="utf-8")
    seen: list[tuple[str, str]] = []

    def on_tool(call: Any, result: Any) -> None:
        seen.append((result.summary or "", ((result.head or "") + (result.output or ""))))
        if change_after_first_read and len(seen) == 1:
            # Somebody else edits the file underneath the agent.
            target.write_text("CHANGED\n", encoding="utf-8")

    asyncio.run(run_agent(
        _ReadsTwice(),
        build_registry(Editor(workspace)),
        [{"role": "user", "content": "读一下笔记"}],
        max_turns=6,
        on_tool=on_tool,
        should_allow=lambda _name, _call: True,
        workspace=workspace,
    ))
    return seen


def test_a_changed_file_is_not_served_from_the_memo(tmp_path: Path) -> None:
    """The observable: the agent sees the file's current content."""
    seen = _run(tmp_path, change_after_first_read=True)
    assert len(seen) == 2, seen
    _summary, second = seen[1]
    assert "CHANGED" in second, (
        "the memo served the old content of a file that changed underneath the agent"
    )
    assert "ORIGINAL" not in second, second


def test_an_unchanged_file_is_still_served_from_the_memo(tmp_path: Path) -> None:
    """The control: the reuse still saves the work."""
    seen = _run(tmp_path, change_after_first_read=False)
    assert len(seen) == 2, seen
    summary, second = seen[1]
    assert "[DUPLICATE_TOOL_CALL]" in summary, summary
    assert "ORIGINAL" in second, second
