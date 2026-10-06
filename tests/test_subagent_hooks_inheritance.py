"""M8-T147: T138 的行为见证必须真运行 subagent，而不是只查 specs.

T138 的修复给子代理的 ``run_agent`` 传了 ``hooks=HookRunner(self.workspace)``
（subagent.py）。原「行为」测试只构造了一个 HookRunner 并断言它的 spec 列表，
从未跑过子代理——把 ``hooks=`` 实参删掉、或让 run_agent 不再消费它，两个测试
都保持绿色。本文件驱动真实栈：假 provider → build_task_tool_spec →
spec.handler → 子代理自己的 run_agent。

三层判据：

- 挂钩运行：PreToolUse 拒绝钩子（exit 2，matcher=read_file）——子代理自己的
  对话里必须出现 ``[HOOK_DENIED]``，文件正文绝不进入；钩子进程本身在
  workspace（cwd）留下标记文件，证明它真跑过而非「没跑也算拒」；
- 对照运行（无 hooks.json）：同一个 provider 必须看到文件正文——没有这一半，
  「正文不出现」的断言可能只是在量一个从不成功的读取；
- 结构门：保留 AST 检查，run_agent(...) 调用带 hooks=HookRunner(...)。
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Any

from minicc.agent.subagent import build_task_tool_spec
from minicc.llm.base import LLMResponse
from minicc.tools import build_registry
from minicc.tools.editor import Editor

PY = sys.executable.replace("\\", "/")
BODY_MARKER = "READ-FILE-BODY-MARKER-4711"
FIRED_MARKER = "subagent_hook_fired"


def _cmd(code: str) -> str:
    return f'"{PY}" -c "{code}"'


# Deny (git-hook style exit 2) AND leave in-workspace evidence that the hook
# process itself executed: a deny verdict with no marker could otherwise be a
# timeout or spawn failure wearing the same word.
DENY_AND_MARK = _cmd(
    f"open('{FIRED_MARKER}','a').close();import sys;sys.exit(2)"
)


class _ReadOneFileProvider:
    """第 1 轮请求 read_file(README.md)，之后记录消息并给出最终答复."""

    def __init__(self) -> None:
        self.requests: list[Any] = []

    async def chat(self, messages, tools, on_delta=None):
        self.requests.append(json.loads(json.dumps(messages, ensure_ascii=False, default=str)))
        if len(self.requests) == 1:
            return LLMResponse(
                tool_calls=[{
                    "id": "call-1",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": json.dumps({"path": "README.md"}),
                    },
                }],
                finish_reason="tool_calls",
            )
        return LLMResponse(content="子代理结论：已完成。", finish_reason="stop")

    async def close(self) -> None:
        return None


def _workspace(tmp_path: Path) -> Path:
    (tmp_path / "README.md").write_text(f"# demo\n{BODY_MARKER}\n", encoding="utf-8")
    return tmp_path


def _run_subagent(workspace: Path) -> tuple[Any, _ReadOneFileProvider]:
    provider = _ReadOneFileProvider()
    spec = build_task_tool_spec(
        provider_factory=lambda: provider,
        workspace=workspace,
        system_prompt="你是 minicc 测试系统提示。",
        base_registry=build_registry(Editor(workspace)),
    )
    result = spec.handler({"description": "读取 README 并总结", "prompt": "读取 README.md 并总结项目用途。"})
    return result, provider


def test_deny_hook_really_blocks_a_subagent_tool_call(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.delenv("MINICC_HOOKS", raising=False)
    workspace = _workspace(tmp_path)
    cfg = workspace / ".minicc" / "hooks.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(
        json.dumps({
            "hooks": {
                "PreToolUse": [{
                    "command": DENY_AND_MARK,
                    "matcher": "^read_file$",
                    "on_failure": "deny",
                }]
            }
        }),
        encoding="utf-8",
    )

    result, provider = _run_subagent(workspace)

    # 前提：子代理确实走到「拿到工具结果、再问模型」这一步（否则下面的
    # 「正文没出现」只是在量一次从未发生的读取）。
    assert len(provider.requests) >= 2, (
        f"the child loop never asked the model again after the tool call; "
        f"only {len(provider.requests)} request(s) happened, so the denial "
        f"assertions below would measure nothing"
    )
    later_turns = json.dumps(provider.requests[1:], ensure_ascii=False)
    assert "[HOOK_DENIED]" in later_turns, (
        "the PreToolUse denial must reach the child's own conversation — the "
        "child's run_agent did not consume the inherited HookRunner"
    )
    assert BODY_MARKER not in later_turns, (
        "a denied read must not leak the file body into the child's conversation"
    )
    assert (workspace / FIRED_MARKER).is_file(), (
        "the hook process itself must have run (it leaves its marker in the "
        "workspace cwd) — a deny verdict without execution is a different failure"
    )
    log = result.data["tool_log"]
    assert any(
        entry["tool"] == "read_file" and "[HOOK_DENIED]" in entry["summary"]
        for entry in log
    ), f"the child's own tool log must record the denial; got {log!r}"


def test_without_the_hook_file_the_same_drive_reads_the_body(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """对照臂：没有 hooks.json 时同一个 provider 必须读到文件正文."""
    monkeypatch.delenv("MINICC_HOOKS", raising=False)
    workspace = _workspace(tmp_path)

    result, provider = _run_subagent(workspace)

    assert len(provider.requests) >= 2, (
        "the control drive must also reach the tool-result round; otherwise "
        "its absence of [HOOK_DENIED] means nothing"
    )
    later_turns = json.dumps(provider.requests[1:], ensure_ascii=False)
    assert BODY_MARKER in later_turns, (
        "without a hook the same subagent drive must surface the file body — "
        "if it does not, the denial test's 'body never appears' assertion is "
        "measuring a read that never succeeds anyway"
    )
    assert "[HOOK_DENIED]" not in later_turns
    assert not (workspace / FIRED_MARKER).exists(), (
        "no hook file means no hook process may have run"
    )


def test_run_agent_call_carries_hooks_parameter() -> None:
    """AST gate: the child's run_agent(...) call in subagent.py must carry hooks=HookRunner(...)."""
    src = Path(__file__).resolve().parent.parent / "minicc" / "agent" / "subagent.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))

    found_run_agent_with_hooks = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            # Could be Name(id='run_agent') or Attribute(attr='run_agent')
            is_run_agent = (
                isinstance(func, ast.Name) and func.id == "run_agent"
            ) or (
                isinstance(func, ast.Attribute) and func.attr == "run_agent"
            )
            if is_run_agent:
                # Check if any keyword arg is 'hooks'
                for kw in node.keywords:
                    if kw.arg == "hooks":
                        # Verify it's HookRunner(...)
                        value = kw.value
                        is_hook_runner = (
                            isinstance(value, ast.Call)
                            and isinstance(value.func, ast.Name)
                            and value.func.id == "HookRunner"
                        )
                        if is_hook_runner:
                            found_run_agent_with_hooks = True
                            break

    assert found_run_agent_with_hooks, (
        "run_agent(...) call in subagent.py must carry hooks=HookRunner(...) "
        "to ensure subagent inherits parent's deny/approve hooks"
    )
