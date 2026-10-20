"""M8-T267: a deny rule the parent is subject to must reach the child.

The child's ``run_agent`` was called without a ``workspace``, so the child
loop had no way to ask ``permissions.json`` at all.  A delegation could then
read what the parent was forbidden to read: the parent's ``deny`` rule stopped
at the parent, while the child - holding the same tools over the same
workspace - walked straight past it.

The tool tier already keeps the child inside the parent's permission mode (a
write or exec tier exists only under acceptEdits / yolo), so the piece that
was missing is the absolute veto.

This door pins:

* a deny rule on a path blocks the child's read of that path;
* the denied payload never reaches the child's model;
* the controls: a child read with no matching rule still works.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from minicc.agent.subagent import build_task_tool_spec
from minicc.llm.base import LLMResponse
from minicc.tools import build_registry
from minicc.tools.editor import Editor

SECRET = "TOP-SECRET-PAYLOAD"


class _ReadOneFileProvider:
    """第 1 轮请求 read_file(path)，之后记录消息并给出最终答复。"""

    def __init__(self, path: str) -> None:
        self.path = path
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
                        "arguments": json.dumps({"path": self.path}),
                    },
                }],
                finish_reason="tool_calls",
            )
        return LLMResponse(content="子代理结论：已完成。", finish_reason="stop")

    async def close(self) -> None:
        return None


def _workspace(tmp_path: Path, *, deny_paths: list[str] | None = None) -> Path:
    workspace = tmp_path / "ws"
    (workspace / "secrets").mkdir(parents=True)
    (workspace / "secrets" / "k.txt").write_text(f"{SECRET}\n", encoding="utf-8")
    (workspace / "public.txt").write_text("hello\n", encoding="utf-8")
    if deny_paths is not None:
        (workspace / ".minicc").mkdir()
        (workspace / ".minicc" / "permissions.json").write_text(
            json.dumps({"deny": {"paths": deny_paths}}), encoding="utf-8"
        )
    return workspace


def _run(workspace: Path, path: str) -> tuple[Any, _ReadOneFileProvider]:
    provider = _ReadOneFileProvider(path)
    spec = build_task_tool_spec(
        provider_factory=lambda: provider,
        workspace=workspace,
        system_prompt="你是 minicc 测试系统提示。",
        base_registry=build_registry(Editor(workspace)),
    )
    result = spec.handler({"description": "读取文件", "prompt": f"读取 {path} 并总结。"})
    return result, provider


def _conversation_text(provider: _ReadOneFileProvider) -> str:
    return json.dumps(provider.requests, ensure_ascii=False, default=str)


def test_a_deny_rule_blocks_the_childs_read_of_that_path(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, deny_paths=["secrets/*"])
    _result, provider = _run(workspace, "secrets/k.txt")
    body = _conversation_text(provider)
    assert SECRET not in body, "the child read the payload the parent was denied"


def test_the_denial_is_visible_to_the_childs_model(tmp_path: Path) -> None:
    """A silent empty result would read like a failed read, not a veto."""
    workspace = _workspace(tmp_path, deny_paths=["secrets/*"])
    _result, provider = _run(workspace, "secrets/k.txt")
    body = _conversation_text(provider)
    assert "deny" in body.lower() or "拒绝" in body, (
        "the child was not told the call was denied by a rule"
    )


def test_a_child_read_with_no_matching_rule_still_works(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, deny_paths=["secrets/*"])
    _result, provider = _run(workspace, "public.txt")
    body = _conversation_text(provider)
    assert "hello" in body, "an unrelated child read was blocked"


def test_no_rule_at_all_leaves_the_child_alone(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _result, provider = _run(workspace, "secrets/k.txt")
    body = _conversation_text(provider)
    assert SECRET in body
