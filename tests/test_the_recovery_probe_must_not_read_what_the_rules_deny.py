"""M8-T338 — agent 自己的恢复探针，也不许读规则拒绝的东西

M8-T290 立了一条规则：**工作区级读取**（无 path 的 `git_diff`、目录上的
`grep`、`tree`）携带每条路径的内容——包括 deny 规则覆盖的那些——所以只要 deny
侧点名了任何路径，这次读取就必须被拒。

但这条规则当时只有**一个读者**：模型自己发起的调用。agent 自己的**恢复探针**
（停滞后收集新证据）直接跑 `git_status` / `git_diff` / `tree`，从不问规则——
而探针的结果是**进对话的**（模型下一轮看得见）。于是同一份 `secrets/*` 规则：
模型问 `git_diff` 被拒，agent 自己问就把秘密带进了上下文。

本门钉住：探针不得把被拒路径的内容送进对话；探针仍要跑（`git_status` 不在
工作区级读取之列，证据不能因为一条规则就全没了）；模型自己那条路依然被拒。
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any

from minicc.agent.loop import run_agent
from minicc.llm.base import LLMResponse
from minicc.tools import build_registry
from minicc.tools.editor import Editor


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


def _workspace(tmp_path: Path) -> Path:
    """A git workspace whose diff carries a denied path's content."""
    workspace = _repo(tmp_path / "ws")
    (workspace / "secrets").mkdir()
    key = workspace / "secrets" / "k.txt"
    key.write_text("old\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "-A"], cwd=str(workspace), capture_output=True,
        encoding="utf-8", errors="replace",
    )
    subprocess.run(
        ["git", "commit", "-m", "seed"], cwd=str(workspace), capture_output=True,
        encoding="utf-8", errors="replace",
    )
    key.write_text("TOPSECRET\n", encoding="utf-8")
    (workspace / ".minicc").mkdir()
    (workspace / ".minicc" / "permissions.json").write_text(
        json.dumps({"deny": {"paths": ["secrets/*"]}}), encoding="utf-8"
    )
    return workspace


class _Repeats:
    """A model that keeps asking for the same read, so the probe fires."""

    def __init__(self) -> None:
        self.calls = 0
        self.seen: list[str] = []

    async def chat(self, messages, tools=None, on_delta=None, **kwargs):
        self.calls += 1
        self.seen.append(json.dumps(messages, ensure_ascii=False, default=str))
        if self.calls <= 3:
            return LLMResponse(
                tool_calls=[{
                    "id": f"read-{self.calls}",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": json.dumps({"path": "secrets/k.txt"}),
                    },
                }],
                finish_reason="tool_calls",
            )
        return LLMResponse(content="done", finish_reason="stop")


def test_the_probe_never_carries_the_denied_content_into_the_conversation(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    provider = _Repeats()
    traces: list[dict[str, Any]] = []
    asyncio.run(run_agent(
        provider,
        build_registry(Editor(workspace)),
        [{"role": "user", "content": "看看密钥"}],
        max_turns=8,
        on_trace=traces.append,
        should_allow=lambda _name, _call: True,
        workspace=workspace,
    ))
    assert not any("TOPSECRET" in text for text in provider.seen), (
        "the recovery probe carried a denied path's content into the conversation"
    )
    assert not any("TOPSECRET" in json.dumps(event, ensure_ascii=False, default=str)
                   for event in traces), (
        "the recovery probe carried a denied path's content into the trace"
    )


def test_the_probe_still_runs_the_reads_the_rules_allow(tmp_path: Path) -> None:
    """A rule is a list, not a blanket ban on the probe."""
    workspace = _workspace(tmp_path)
    provider = _Repeats()
    traces: list[dict[str, Any]] = []
    asyncio.run(run_agent(
        provider,
        build_registry(Editor(workspace)),
        [{"role": "user", "content": "看看密钥"}],
        max_turns=8,
        on_trace=traces.append,
        should_allow=lambda _name, _call: True,
        workspace=workspace,
    ))
    probe = next(
        (event for event in traces if event.get("code") == "recovery_probe_finished"),
        None,
    )
    assert probe is not None, "the probe never ran"
    skipped = (probe.get("detail") or {}).get("skipped_by_rules")
    assert "git_diff" in (skipped or []), probe.get("detail")
    assert "tree" in (skipped or []), probe.get("detail")
    assert "git_status" not in (skipped or []), probe.get("detail")


def test_the_model_side_is_still_refused(tmp_path: Path) -> None:
    """The other face of the same rule keeps its answer."""
    from minicc.audit import path_rule_denies_call

    workspace = _workspace(tmp_path)
    assert path_rule_denies_call(workspace, "git_diff", {}) is True
    assert path_rule_denies_call(workspace, "tree", {}) is True
    assert path_rule_denies_call(workspace, "git_status", {}) is False
    assert path_rule_denies_call(workspace, "read_file", {"path": "secrets/k.txt"}) is True
    assert path_rule_denies_call(workspace, "read_file", {"path": "public.txt"}) is False
