"""M7-T1: workspace hooks contract.

Four events (UserPromptSubmit / PreToolUse / PostToolUse / Stop), and the
invariants the roadmap pins down:

- a hook may only *deny* — it can never widen what the permission model
  already refused (the PreToolUse hook is not even consulted after a gate
  denial);
- UserPromptSubmit denial stops the run before the provider is called;
- timeouts terminate the hook instead of hanging the loop;
- hook output is redacted before it reaches traces;
- a configured hook set leaves the workspace byte-identical otherwise.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

from minicc.agent.loop import run_agent
from minicc.hooks import HookRunner
from minicc.llm.base import LLMResponse
from minicc.tools import build_registry
from minicc.tools.editor import Editor

PY = sys.executable.replace("\\", "/")
SECRET = "sk-abcdefgh12345678"


def _cmd(code: str) -> str:
    return f'"{PY}" -c "{code}"'


EXIT_ALLOW = _cmd("import sys;sys.exit(0)")
EXIT_DENY = _cmd("import sys;sys.exit(2)")
SLEEP_10 = _cmd("import time;time.sleep(10)")
MARKER = _cmd("open('hook_ran','a').close()")
# The secret must never appear in the command itself: hook commands are
# echoed verbatim into traces, which would make the redaction assertion
# unfalsifiable. The hook prints it from a file instead.
ECHO_SECRET = _cmd("print(open('secret.txt').read())")


def _install_hooks(workspace: Path, hooks: dict[str, list[dict[str, Any]]]) -> HookRunner:
    cfg_dir = workspace / ".minicc"
    cfg_dir.mkdir(exist_ok=True)
    (cfg_dir / "hooks.json").write_text(json.dumps({"hooks": hooks}), encoding="utf-8")
    return HookRunner(workspace)


class ToolThenAnswerProvider:
    """One read_file call, then a plain answer."""

    def __init__(self, tool: str = "read_file", arguments: dict[str, Any] | None = None) -> None:
        self.calls = 0
        self.tool = tool
        self.arguments = arguments if arguments is not None else {"path": "a.txt"}

    async def chat(self, messages, tools, on_delta=None):
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                content="",
                tool_calls=[{
                    "id": "call-1",
                    "type": "function",
                    "function": {
                        "name": self.tool,
                        "arguments": json.dumps(self.arguments),
                    },
                }],
                finish_reason="tool_calls",
            )
        return LLMResponse(content="完成。", finish_reason="stop")


class NeverCalledProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, messages, tools, on_delta=None):
        self.calls += 1
        raise AssertionError("provider must not be called after UserPromptSubmit deny")


class AnswerOnlyProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, messages, tools, on_delta=None):
        self.calls += 1
        return LLMResponse(content="完成。", finish_reason="stop")


def _run(tmp_path: Path, provider, hooks, **kwargs):
    workspace_file = tmp_path / "a.txt"
    if not workspace_file.exists():
        workspace_file.write_text("hello\n", encoding="utf-8")

    async def _go():
        return await run_agent(
            provider,
            build_registry(Editor(tmp_path)),
            [{"role": "user", "content": "读一下 a.txt"}],
            should_allow=kwargs.pop("should_allow", lambda _n, _c: True),
            hooks=hooks,
            **kwargs,
        )

    before = {p.as_posix(): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    result = asyncio.run(_go())
    after = {p.as_posix(): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    return result, before, after


def test_user_prompt_submit_deny_stops_before_provider(tmp_path: Path) -> None:
    hooks = _install_hooks(tmp_path, {
        "UserPromptSubmit": [{"command": EXIT_DENY, "timeout": 5}],
    })
    provider = NeverCalledProvider()
    result, before, after = _run(tmp_path, provider, hooks)
    assert provider.calls == 0
    assert result.error and "UserPromptSubmit" in result.error
    assert "hook" in result.answer
    assert before == after, "denied prompt must leave the workspace untouched"


def test_pre_tool_use_deny_blocks_tool_and_keeps_loop_running(tmp_path: Path) -> None:
    hooks = _install_hooks(tmp_path, {
        "PreToolUse": [{"command": EXIT_DENY, "matcher": "^read_file$", "timeout": 5}],
    })
    result, _before, _after = _run(tmp_path, ToolThenAnswerProvider(), hooks)
    assert "read_file" in result.denied_tools
    assert result.error is None
    assert result.answer == "完成。", "a denied tool must not abort the run"


def test_pre_tool_use_can_never_escalate_past_the_gate(tmp_path: Path) -> None:
    # An allow-exiting hook is installed; the permission gate still denies the
    # write, and the hook must not even be consulted for a gate-denied call.
    # (read-only tools never reach the gate — pick an authorization-required
    # tool so the deny path is the permission model, not the hook.)
    hooks = _install_hooks(tmp_path, {
        "PreToolUse": [{"command": MARKER, "timeout": 5}],
    })
    result, _before, _after = _run(
        tmp_path,
        ToolThenAnswerProvider(tool="write_file", arguments={"path": "b.txt", "content": "x\n"}),
        hooks,
        should_allow=lambda _n, _c: False,
    )
    assert not (tmp_path / "hook_ran").exists(), "hook ran for a gate-denied tool"
    assert not (tmp_path / "b.txt").exists(), "gate-denied write must not be performed"
    assert result.error is None


def test_pre_tool_use_timeout_denies_and_does_not_hang(tmp_path: Path) -> None:
    hooks = _install_hooks(tmp_path, {
        "PreToolUse": [
            {"command": SLEEP_10, "matcher": "^read_file$", "timeout": 1, "on_failure": "deny"},
        ],
    })
    started = time.monotonic()
    result, _before, _after = _run(tmp_path, ToolThenAnswerProvider(), hooks)
    assert time.monotonic() - started < 8.0, "timeout did not terminate the hook"
    assert "read_file" in result.denied_tools


def test_timeout_with_continue_policy_allows_the_tool(tmp_path: Path) -> None:
    hooks = _install_hooks(tmp_path, {
        "PreToolUse": [
            {"command": SLEEP_10, "matcher": "^read_file$", "timeout": 1, "on_failure": "continue"},
        ],
    })
    result, _before, _after = _run(tmp_path, ToolThenAnswerProvider(), hooks)
    assert "read_file" not in result.denied_tools


def test_post_and_stop_fire_and_never_change_decisions(tmp_path: Path) -> None:
    traces: list[dict] = []
    hooks = _install_hooks(tmp_path, {
        # A deny at PostToolUse is audit-only: the completed read stands.
        "PostToolUse": [{"command": EXIT_DENY, "timeout": 5}],
        "Stop": [{"command": EXIT_ALLOW, "timeout": 5}],
    })
    result, _before, _after = _run(tmp_path, ToolThenAnswerProvider(), hooks, on_trace=traces.append)
    assert result.error is None
    assert "read_file" not in result.denied_tools
    events = {e["detail"].get("event") for e in traces if e.get("code") == "hook_executed"}
    assert {"PostToolUse", "Stop"} <= events


def test_hook_output_is_redacted_in_traces(tmp_path: Path) -> None:
    (tmp_path / "secret.txt").write_text(SECRET + "\n", encoding="utf-8")
    traces: list[dict] = []
    hooks = _install_hooks(tmp_path, {
        "PostToolUse": [{"command": ECHO_SECRET, "timeout": 5}],
    })
    _result, _before, _after = _run(
        tmp_path, ToolThenAnswerProvider(), hooks, on_trace=traces.append
    )
    dump = json.dumps(traces, ensure_ascii=False)
    assert SECRET not in dump, "raw secret leaked from hook stdout into traces"
    assert "[REDACTED" in dump


def test_matcher_scopes_hooks_to_tool_names(tmp_path: Path) -> None:
    hooks = _install_hooks(tmp_path, {
        "PreToolUse": [{"command": EXIT_DENY, "matcher": "^glob$", "timeout": 5}],
    })
    result, _before, _after = _run(tmp_path, ToolThenAnswerProvider(), hooks)
    assert "read_file" not in result.denied_tools, "matcher must not hit other tools"


def test_hooks_disabled_by_env_and_bad_config_is_not_fatal(tmp_path: Path, monkeypatch) -> None:
    hooks = _install_hooks(tmp_path, {"UserPromptSubmit": [{"command": EXIT_DENY}]})
    assert hooks.enabled
    monkeypatch.setenv("MINICC_HOOKS", "0")
    assert not HookRunner(tmp_path).enabled
    monkeypatch.delenv("MINICC_HOOKS")
    (tmp_path / ".minicc" / "hooks.json").write_text(
        json.dumps({"hooks": {"NotAnEvent": []}}), encoding="utf-8"
    )
    broken = HookRunner(tmp_path)
    assert not broken.enabled
    assert broken.load_error, "bad config must surface as load_error, not raise"
    provider = AnswerOnlyProvider()
    result, _before, _after = _run(tmp_path, provider, broken)
    assert provider.calls == 1, "a broken hook set must not block the run"
    assert result.answer == "完成。"
