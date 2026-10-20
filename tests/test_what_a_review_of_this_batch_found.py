"""M8-T291 / T292 — 一次复核抓到的八条：四条是这一批自己引入的

这一批做完之后做了一次独立复核（逐个文件读 diff + 问"这个改法有没有把别的弄坏"），
复核报出八条问题，其中**四条是本批自己引入的**：

| 编号 | 问题 |
| --- | --- |
| M8-T291 | 注释说"real work 必须是写"，代码却还留着"发生过任何事"那一支——**注释与代码矛盾** |
| M8-T292 | `background` 标志只加在内部 feedback 上，Web 事件流**没有它**——那个消费者才是门真正要拦的 |
| M8-T293 | `deny_rule_names_paths` 只接了一个消费方；agent 自己的 `git_diff`（无 path）与 `grep`（path 是目录）仍能读出被拒内容 |
| M8-T294 | 取消路径把锁留在 in-flight 里，**同时满足两条逐出保护** → 永不逐出 → 表无界 |
| M8-T295 | 日志侧因为要与模型侧一致而**缩小了脱敏覆盖**（短的、带代码标点的值不再遮） |
| M8-T296 | mention 的 deny 门在 CJK 回退**之前**，收敛后没重查 → 精确路径规则被绕过 |
| M8-T297 | `changes.py` 新加的 `_resolve` 没捕 `ChangeError` → 越界软链让 diff 路由 500 |
| M8-T298 | `"create"` 被静默从"改了工作区"的名单里删掉，而注释只论证了 `backup` |

This door pins all eight.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from minicc.agent.completion import CompletionDecision, _enforce_completion_evidence
from minicc.changes import ChangeInspector
from minicc.logging_setup import redact
from minicc.mentions import apply_mentions
from minicc.tools.editor import Editor, _MUTATING_ACTIONS, audit_level


def _repo(workspace: Path) -> Path:
    workspace.mkdir(parents=True, exist_ok=True)
    for args in (
        ["init"],
        ["config", "user.email", "t@example.test"],
        ["config", "user.name", "t"],
    ):
        subprocess.run(
            ["git", *args], cwd=str(workspace), capture_output=True,
            encoding="utf-8", errors="replace",
        )
    return workspace


# --- M8-T291: "real work" means a write, and the code has to say so -----------


def test_a_read_is_not_real_work(tmp_path: Path) -> None:
    """The comment named this case; the code did not implement it.

    A writable task that only *read* a file may not certify itself with the
    user's own question.  A read is a real tool observation (so the review
    may cite it), but it is not **work** - so the conversation bucket stays
    uncitable and the review's citation of ``message-1`` is not accepted.
    """
    decision = CompletionDecision(
        status="complete", confidence=0.9, rationale="", missing=[],
        next_action="", evidence=["message-0"],
    )
    out = _enforce_completion_evidence(
        decision,
        [{"kind": "tool", "name": "read_file", "status": "ok", "path": "app.py"}],
        [],
        [{"role": "user", "content": "fix app.py"}],
        allow_changes=True,
    )
    assert out.status != "complete", (
        "a writable task that only read a file certified itself with the "
        "user's question"
    )


def test_a_read_is_still_citable_as_a_tool_observation() -> None:
    """The control: the door is not shut on a legitimate read."""
    decision = CompletionDecision(
        status="complete", confidence=0.9, rationale="", missing=[],
        next_action="", evidence=["event-1"],
    )
    out = _enforce_completion_evidence(
        decision,
        [{"kind": "tool", "name": "read_file", "status": "ok", "path": "app.py"}],
        [],
        [{"role": "user", "content": "fix app.py"}],
        allow_changes=True,
    )
    assert out.status == "complete", (
        "a real tool observation stopped being citable evidence"
    )


# --- M8-T292: the background flag reaches the event the gate reads -----------


def test_the_web_event_carries_the_background_flag() -> None:
    """The gate is fed the event list, so the flag has to be in the event."""
    source = (
        Path(__file__).resolve().parents[1] / "minicc" / "web.py"
    ).read_text(encoding="utf-8")
    marker = "def on_tool(call: ToolCall, result: ToolResult) -> None:"
    start = source.index(marker)
    branch = source[start:start + 2500]
    assert '"background": bool(feedback.get("background"))' in branch, (
        "the Web event does not carry the background flag, so the completion "
        "gate cannot see it"
    )


# --- M8-T293: a workspace-wide read carries the denied content --------------


def test_a_workspace_wide_read_is_refused_when_a_path_is_denied(tmp_path: Path) -> None:
    """``git_diff`` without a path returns the whole working-tree diff."""
    from minicc.audit import deny_rule_names_paths, tool_denied_by_rule

    workspace = _repo(tmp_path / "ws")
    (workspace / "secrets").mkdir()
    (workspace / "secrets" / "k.txt").write_text("TOPSECRET\n", encoding="utf-8")
    (workspace / ".minicc").mkdir()
    (workspace / ".minicc" / "permissions.json").write_text(
        json.dumps({"deny": {"paths": ["secrets/*"]}}), encoding="utf-8"
    )

    assert deny_rule_names_paths(workspace) is True
    # The tool's own arguments (no path) do not match the rule...
    assert tool_denied_by_rule(workspace, "git_diff", {}) is False
    # ...so the caller has to ask the wider question too.
    from minicc.agent.loop import _rule_covers_this_call

    assert _rule_covers_this_call(workspace, "git_diff", {}) is False


def test_a_workspace_wide_git_diff_is_denied_end_to_end(tmp_path: Path) -> None:
    """The behaviour: the agent's own diff cannot carry the denied content."""
    import asyncio

    from minicc.agent.loop import run_agent
    from minicc.llm.base import LLMResponse
    from minicc.tools import build_registry
    from minicc.tools.schemas import ToolCall

    workspace = _repo(tmp_path / "ws")
    (workspace / "secrets").mkdir()
    (workspace / "secrets" / "k.txt").write_text("TOPSECRET\n", encoding="utf-8")
    (workspace / ".minicc").mkdir()
    (workspace / ".minicc" / "permissions.json").write_text(
        json.dumps({"deny": {"paths": ["secrets/*"]}}), encoding="utf-8"
    )

    class _AsksForDiff:
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
                            "name": "git_diff",
                            "arguments": json.dumps({}),
                        },
                    }],
                    finish_reason="tool_calls",
                )
            return LLMResponse(content="done", finish_reason="stop")

    seen: list[str] = []

    def on_tool(call: Any, result: Any) -> None:
        seen.append((result.summary or "") + (result.output or ""))

    asyncio.run(run_agent(
        _AsksForDiff(),
        build_registry(Editor(workspace)),
        [{"role": "user", "content": "看看有什么改动"}],
        on_tool=on_tool,
        workspace=workspace,
    ))

    assert not any("TOPSECRET" in text for text in seen), (
        "the workspace-wide diff carried a denied path's content"
    )


# --- M8-T294: a cancelled request must not pin its lock forever --------------


def test_a_cancelled_request_does_not_pin_its_lock(tmp_path: Path) -> None:
    """An entry that satisfies **both** eviction guards can never be evicted."""
    from minicc.web import AgentService

    workspace = tmp_path / "ws"
    workspace.mkdir()
    service = AgentService(workspace, SimpleNamespaceConfig())
    try:
        lock = service._session_lock(workspace, "cancelled-session")
        service._release_session_lock_inflight(workspace, "cancelled-session")
        key = next(iter(service._session_locks))
        assert key not in service._session_locks_inflight, (
            "the cancelled request's lock is still marked in flight, so it can "
            "never be evicted"
        )
        assert lock is not None
    finally:
        service.shutdown()


def SimpleNamespaceConfig() -> Any:
    from types import SimpleNamespace

    return SimpleNamespace(
        yolo=False, max_concurrent_tasks=1, sandbox_mode="host",
        sandbox_image="python:3.11-slim", base_url="https://example.test/v1",
        api_key="test-key", model="test-model", timeout=10, tool_mode="auto",
        reasoning_effort="high", max_turns=4, compact_threshold=300_000,
        context_window_tokens=300_000,
    )


# --- M8-T295: the log may be stricter, never looser -----------------------


@pytest.mark.parametrize(
    "raw,needle",
    [
        ('{"api_key": "abcd1234efgh5678"}', "abcd1234efgh5678"),
        ("password=abc", "abc"),
        ("api_key=a(b", "a(b"),
    ],
)
def test_the_log_masks_every_labelled_value(raw: str, needle: str) -> None:
    masked = redact(raw)
    assert needle not in masked, f"the log left {needle!r} in {raw!r}"


# --- M8-T296: the deny gate is re-checked on the converged path --------------


def test_an_exact_path_rule_survives_the_cjk_tail(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    (workspace / "secrets").mkdir(parents=True)
    (workspace / "secrets" / "k.txt").write_text("TOPSECRET\n", encoding="utf-8")
    (workspace / ".minicc").mkdir()
    (workspace / ".minicc" / "permissions.json").write_text(
        json.dumps({"deny": {"paths": ["secrets/k.txt"]}}), encoding="utf-8"
    )
    message, records = apply_mentions("@secrets/k.txt是什么", workspace)
    assert "TOPSECRET" not in message, (
        "an exact-path deny rule was defeated by the CJK tail"
    )
    assert any(item.get("status") == "rejected" for item in records), records


# --- M8-T297: a path that leaves the workspace does not 500 the diff route ---


def test_a_diff_over_a_path_outside_the_workspace_does_not_raise(
    tmp_path: Path,
) -> None:
    workspace = _repo(tmp_path / "ws")
    (workspace / "a.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "-A"], cwd=str(workspace), capture_output=True,
        encoding="utf-8", errors="replace",
    )
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=str(workspace), capture_output=True,
        encoding="utf-8", errors="replace",
    )
    outside = tmp_path / "outside.txt"
    outside.write_text("y\n", encoding="utf-8")
    try:
        (workspace / "link.txt").symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this platform")

    # The status table must not raise while keying the paths.
    inspector = ChangeInspector(workspace)
    result = inspector.summary()
    assert isinstance(result.get("files"), list)


# --- M8-T298: "create" is a change ------------------------------------------


def test_a_creation_is_a_workspace_change() -> None:
    assert "create" in _MUTATING_ACTIONS, (
        "a file that did not exist and exists now is a change"
    )
    assert audit_level("create", "") == "notice"
    assert "backup" not in _MUTATING_ACTIONS, (
        "a backup writes a copy; it does not change the file"
    )
