"""M8-T304 — 写到工作区之外的那次调用，得按它实际的样子判定

`memory_write` 登记为 **readonly**：它的 project 作用域写的是
`.minicc/MEMORY.md`——工作区**里面**的 agent 状态，与 `todo_write` 同类。

但它还有一个作用域：

| 作用域 | 目标 |
| --- | --- |
| `project` | `<工作区>/.minicc/MEMORY.md`（工作区内） |
| `user` | `~/.minicc/MEMORY.md`（**工作区之外**，且被所有项目共用） |

`readonly` 的工具**绕过写入闸门**——于是 agent 在**不询问**的情况下写了用户
home 里的文件，而 **plan 模式**（"只读规划"）也拦不住它：plan 只拒绝
`risk == "write"` 的工具。

本门禁钉住：user 作用域按**一次写操作**判定。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from minicc.audit import authorize_tool


def _decision(tool: str, arguments: dict[str, object], *, mode: str = "default", **extra: object):
    return authorize_tool(
        tool,
        "readonly",
        arguments,
        allow_changes=bool(extra.get("allow_changes", False)),
        allow_network=False,
        permission_mode=mode,
        workspace=extra.get("workspace"),  # type: ignore[arg-type]
    )


def test_the_user_scope_is_not_allowed_without_the_write_grant(tmp_path: Path) -> None:
    """It writes into the user's home - that is a write."""
    decision = _decision("memory_write", {"scope": "user"}, workspace=tmp_path)
    assert decision.allowed is False, (
        f"the write outside the workspace was allowed: {decision}"
    )
    assert decision.authorization == "missing_task_write", decision.authorization


def test_the_user_scope_is_refused_in_plan_mode(tmp_path: Path) -> None:
    """Plan mode's whole promise is "read only"."""
    decision = _decision("memory_write", {"scope": "user"}, mode="plan", workspace=tmp_path)
    assert decision.allowed is False, decision
    assert decision.authorization == "plan_mode_write", decision.authorization


def test_the_user_scope_is_allowed_once_writes_are_granted(tmp_path: Path) -> None:
    """The control: with the grant, it works."""
    decision = _decision(
        "memory_write", {"scope": "user"}, mode="acceptEdits", workspace=tmp_path
    )
    assert decision.allowed is True, decision


def test_the_project_scope_stays_readonly(tmp_path: Path) -> None:
    """The control: the in-workspace scope is unchanged."""
    decision = _decision("memory_write", {"scope": "project"}, workspace=tmp_path)
    assert decision.allowed is True, decision
    assert decision.authorization == "default_readonly", decision.authorization


def test_the_project_scope_is_still_allowed_in_plan_mode(tmp_path: Path) -> None:
    """The control: plan mode still allows the in-workspace memory."""
    decision = _decision("memory_write", {"scope": "project"}, mode="plan", workspace=tmp_path)
    assert decision.allowed is True, decision


def test_the_read_tools_are_unaffected(tmp_path: Path) -> None:
    """The control: nothing else moved."""
    for tool in ("memory_read", "memory_list", "todo_read", "read_file"):
        decision = _decision(tool, {}, workspace=tmp_path)
        assert decision.allowed is True, (tool, decision)
        assert decision.authorization == "default_readonly", (tool, decision)


def test_a_plan_mode_run_cannot_write_the_user_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The end-to-end shape: the loop has to ask, and the answer is no.

    The tool is registered ``readonly``, so the loop's own gate used to skip
    it entirely - the declared risk is all the loop had to go on.

    The user scope writes into ``~/.minicc/MEMORY.md``, so the home root is
    pointed at a temporary directory: this test must never write to the
    machine's real home (a mutation that lets the write through would
    otherwise leave a memory behind in it).
    """
    import asyncio
    import json

    from minicc.agent.loop import run_agent
    from minicc.llm.base import LLMResponse
    from minicc.tools import build_registry
    from minicc.tools.editor import Editor

    workspace = tmp_path / "ws"
    workspace.mkdir()
    monkeypatch.setenv("MINICC_HOME", str(tmp_path / "home"))

    class _WritesUserMemory:
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
                            "name": "memory_write",
                            "arguments": json.dumps({
                                "content": "记住这条",
                                "scope": "user",
                            }),
                        },
                    }],
                    finish_reason="tool_calls",
                )
            return LLMResponse(content="done", finish_reason="stop")

    def should_allow(name: str, call: Any) -> bool:
        # The gate the CLI and the Web face both use, in plan mode.
        return authorize_tool(
            name,
            "readonly",
            call.arguments,
            allow_changes=False,
            allow_network=False,
            permission_mode="plan",
            workspace=workspace,
        ).allowed

    result = asyncio.run(run_agent(
        _WritesUserMemory(),
        build_registry(Editor(workspace)),
        [{"role": "user", "content": "记一下"}],
        workspace=workspace,
        should_allow=should_allow,
    ))

    assert "memory_write" in result.denied_tools, (
        f"the plan-mode run wrote the user memory: {result.denied_tools}"
    )
    assert not (tmp_path / "home" / "MEMORY.md").exists(), (
        "the user memory was written even though the call was denied"
    )
