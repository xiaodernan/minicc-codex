"""M8-T289 — hook 执行不该占住事件循环

hook 以前是在 `run_agent` 的协程里**同步**跑的。于是：

* 一次工具调用要等一组 hook 全部返回，而这段时间里事件循环是停的；
* 运行中请求的**取消**要等 hook 全部返回才会被看到——一个本来能被取消的
  运行，卡在 hook 上时取消不了。

现在 hook 在**线程**里跑，事件循环继续转。

This door pins:

* the hook runs off the event loop, so the loop keeps turning;
* the control: the hook still fires and still decides.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import pytest

from minicc.agent.loop import run_agent
from minicc.hooks import HookRunner
from minicc.llm.base import LLMResponse
from minicc.tools import build_registry
from minicc.tools.editor import Editor


class _OneToolThenStop:
    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, messages, tools=None, on_delta=None, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                content=None,
                tool_calls=[{
                    "id": "call-0",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": json.dumps({"path": "README.md"}),
                    },
                }],
                finish_reason="tool_calls",
            )
        return LLMResponse(content="done", finish_reason="stop")


def _hooks(workspace: Path, command: str) -> None:
    path = workspace / ".minicc" / "hooks.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"hooks": {"PreToolUse": [{"command": command, "timeout": 10}]}}),
        encoding="utf-8",
    )


def test_the_loop_keeps_turning_while_a_hook_runs(tmp_path: Path) -> None:
    """A hook that sleeps must not stop the event loop.

    The sampler lives **inside** the event loop (an ``asyncio`` task), not
    in a thread: a thread is unaffected by the loop being blocked, so it
    could not tell the two implementations apart.
    """
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "README.md").write_text("# demo\n", encoding="utf-8")
    _hooks(workspace, "python -c \"import time; time.sleep(1.5)\"")

    async def scenario() -> int:
        ticks = 0

        async def sampler() -> None:
            nonlocal ticks
            while True:
                ticks += 1
                await asyncio.sleep(0.02)

        task = asyncio.create_task(sampler())
        try:
            await run_agent(
                _OneToolThenStop(),
                build_registry(Editor(workspace)),
                [{"role": "user", "content": "read README.md"}],
                workspace=workspace,
                hooks=HookRunner(workspace),
            )
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        return ticks

    ticks = asyncio.run(scenario())
    assert ticks > 20, (
        f"the event loop only turned {ticks} times while a 1.5s hook was "
        "running - it was blocked"
    )


def test_the_hook_still_fires_and_still_decides(tmp_path: Path) -> None:
    """The control: the hook is not skipped by the move to a thread."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "README.md").write_text("# demo\n", encoding="utf-8")
    marker = workspace / "hook-ran.txt"
    _hooks(workspace, f"python -c \"open(r'{marker}', 'w').close()\"")

    asyncio.run(run_agent(
        _OneToolThenStop(),
        build_registry(Editor(workspace)),
        [{"role": "user", "content": "read README.md"}],
        workspace=workspace,
        hooks=HookRunner(workspace),
    ))

    assert marker.is_file(), "the hook did not run"


def test_a_denying_hook_still_denies(tmp_path: Path) -> None:
    """The control: the decision still reaches the loop."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "README.md").write_text("# demo\n", encoding="utf-8")
    path = workspace / ".minicc" / "hooks.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({
            "hooks": {
                "PreToolUse": [{
                    "command": "python -c \"import sys; sys.exit(2)\"",
                    "timeout": 10,
                    "on_failure": "deny",
                }]
            }
        }),
        encoding="utf-8",
    )

    result = asyncio.run(run_agent(
        _OneToolThenStop(),
        build_registry(Editor(workspace)),
        [{"role": "user", "content": "read README.md"}],
        workspace=workspace,
        hooks=HookRunner(workspace),
    ))

    assert result.denied_tools, "the denying hook did not deny"
