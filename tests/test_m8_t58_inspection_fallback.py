"""M8-T58: 循环层验证守卫的检视回退——「无可运行检查」的工作区不可满足尾部。

M6-4 全量 + A/B 复测各抓到一次：version-exact（version.txt）与
package-manifest 的产物正确（oracle 通过），但循环守卫要求白名单检查器
成功运行——对纯文本/JSON 改动，白名单里没有任何命令适用，
VERIFICATION_RETRY_LIMIT=1 一次烧完即死。修复与 M8-T54 同判据：
verification plan 对改动路径没有产出任何命令（客观工作区事实）时，
写入后的 read_file/git_diff 检视视为完成验证。有检查可跑的工作区行为不变。
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from minicc.agent.loop import run_agent
from minicc.llm.base import LLMResponse
from minicc.tools import build_registry
from minicc.tools.editor import Editor


class _TextWriteThenReadProvider:
    """写一个 .txt、读回一次，然后试图用纯文本结束——从不跑任何检查器。"""

    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, messages, tools, on_delta=None):
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(tool_calls=[{
                "id": "write-1",
                "type": "function",
                "function": {
                    "name": "write_file",
                    "arguments": json.dumps({"path": "notes.txt", "content": "v2\n"}),
                },
            }])
        if self.calls == 2:
            return LLMResponse(tool_calls=[{
                "id": "read-1",
                "type": "function",
                "function": {
                    "name": "read_file",
                    "arguments": json.dumps({"path": "notes.txt"}),
                },
            }])
        return LLMResponse(content="已写入并读回确认。")

    async def close(self) -> None:
        return None


class _TextWriteAndFinishProvider:
    """写一个 .txt 后直接试图结束，从不检视——检视回退不得豁免「未检视」。"""

    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, messages, tools, on_delta=None):
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(tool_calls=[{
                "id": "write-1",
                "type": "function",
                "function": {
                    "name": "write_file",
                    "arguments": json.dumps({"path": "notes.txt", "content": "v2\n"}),
                },
            }])
        return LLMResponse(content="写好了，任务完成。")

    async def close(self) -> None:
        return None


def _run(provider, tmp_path: Path, yolo: bool = True):
    registry = build_registry(Editor(tmp_path))
    registry.declare_builtin()

    # should_allow is a synchronous bool contract (loop.py:431, consumed at
    # loop.py:1042 as `not allow(...)`); an async gate here would be treated as
    # a truthy coroutine and leak unawaited, failing the suite under -W error.
    def gate(name, call):
        return True

    import asyncio
    return asyncio.run(run_agent(
        provider,
        registry,
        [{"role": "user", "content": "把 notes.txt 写成 v2"}],
        budget=None,
        should_allow=gate,
        workspace=str(tmp_path),
    ))


def test_inspection_satisfies_verification_in_a_checkless_workspace(tmp_path: Path) -> None:
    provider = _TextWriteThenReadProvider()
    result = _run(provider, tmp_path)
    assert result.error is None, result.error
    assert result.answer == "已写入并读回确认。"
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "v2\n"


def test_no_inspection_still_fails_the_guard(tmp_path: Path) -> None:
    provider = _TextWriteAndFinishProvider()
    result = _run(provider, tmp_path)
    # 检视回退的前提是确实检视过：没有 read_file/git_diff 时守卫照旧拒绝。
    assert result.error == "Agent 在修改工作区后没有完成验证"


def test_second_nudge_converts_a_late_inspection(tmp_path: Path) -> None:
    """M8-T59: 两次 nudge 的第二次才补上检视——不再一次烧完即死。

    未修复（RETRY_LIMIT=1）代码上这里红：第二次尝试结束时守卫直接判死，
    读回根本没机会发生。
    """

    class LateInspector:
        def __init__(self) -> None:
            self.calls = 0

        async def chat(self, messages, tools, on_delta=None):
            self.calls += 1
            if self.calls == 1:
                return LLMResponse(tool_calls=[{
                    "id": "write-1",
                    "type": "function",
                    "function": {
                        "name": "write_file",
                        "arguments": json.dumps({"path": "notes.txt", "content": "v2\n"}),
                    },
                }])
            if self.calls in (2, 3):
                # 第一次 nudge 后仍未行动，再次试图纯文本结束——LIMIT=1 在这里
                # 就判死，读回永远轮不到（这就是本测试的判红点）。
                return LLMResponse(content="写好了，任务完成。")
            if self.calls == 4:
                # 第二次 nudge 后才读回。
                return LLMResponse(tool_calls=[{
                    "id": "read-1",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": json.dumps({"path": "notes.txt"}),
                    },
                }])
            return LLMResponse(content="已写入并读回确认。")

        async def close(self) -> None:
            return None

    provider = LateInspector()
    result = _run(provider, tmp_path)
    assert result.error is None, result.error
    assert result.answer == "已写入并读回确认。"


def test_workspace_with_runnable_check_keeps_demanding_it(tmp_path: Path, monkeypatch) -> None:
    """有检查可跑的工作区：检视不能替代检查器（回退只在无检查时生效）。"""
    # 注入一个「有命令」的 plan，模拟存在可运行检查的工作区。
    import minicc.agent.loop as loop_mod
    from minicc.agent.verification_plan import VerificationCommand, VerificationPlan

    def fake_plan(workspace, changed_paths):
        return VerificationPlan(
            [VerificationCommand("python -m pytest -q", label="project")],
            list(changed_paths),
            "fp",
            "changed files",
        )

    monkeypatch.setattr(loop_mod, "build_verification_plan", fake_plan)
    provider = _TextWriteThenReadProvider()
    result = _run(provider, tmp_path)
    assert result.error == "Agent 在修改工作区后没有完成验证"
