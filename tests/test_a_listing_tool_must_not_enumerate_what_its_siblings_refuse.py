"""M8-T339 — 列举型工具也有两张脸：被拒的路径不该被列出来

M8-T290/M8-T338 的规则说：**工作区级读取**（整棵树、整个 diff、整目录的
grep）携带每条路径的内容与名字，所以只要 deny 侧点名了路径，这次读取就得
被拒。那份名单里原本有三个成员，而**列举型工具**其实有四个：

* `tree` 在名单里 → 有 deny 规则的工作区里，agent 的 `tree` 被拒；
* `glob` 不在名单里 → 同一个工作区里，agent 用 `glob` 把 `secrets/k.txt`
  列了出来——**deny 规则差一步就成了摆设**。

另一张脸在内建保护上：`read_file`/`write_file`/`edit_file` 拒绝敏感文件
（`.env`、`id_rsa`、`*.pem`），`grep` 跳过它们——而 `tree` 与 `glob` **照列**。
能读不能列不算漏洞，但"列出来"让 agent 知道了那些路径存在。

本门钉住：`glob` 与 `tree` 都进工作区级名单；两个列举工具都不再列出内建
敏感文件；控制组——普通文件照列、没有规则的工作区行为不变。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from minicc.audit import path_rule_denies_call
from minicc.tools import build_registry
from minicc.tools.editor import Editor
from minicc.tools.schemas import ToolCall


def _repo(workspace: Path) -> Path:
    workspace.mkdir(parents=True, exist_ok=True)
    for args in (["init"], ["config", "user.email", "t@example.test"], ["config", "user.name", "t"]):
        subprocess.run(
            ["git", *args], cwd=str(workspace), capture_output=True,
            encoding="utf-8", errors="replace",
        )
    return workspace


def _workspace(tmp_path: Path, *, deny_paths: list[str] | None) -> Path:
    workspace = tmp_path / "ws"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "secrets").mkdir()
    (workspace / "secrets" / "k.txt").write_text("TOPSECRET\n", encoding="utf-8")
    (workspace / "src").mkdir()
    (workspace / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")
    (workspace / ".env").write_text("TOKEN=abc\n", encoding="utf-8")
    # The file **name** is what the built-in rule judges; the content is
    # irrelevant here (and must not look like a real key to the commit hook).
    (workspace / "id_rsa").write_text("private key material\n", encoding="utf-8")
    if deny_paths is not None:
        (workspace / ".minicc").mkdir()
        (workspace / ".minicc" / "permissions.json").write_text(
            json.dumps({"deny": {"paths": deny_paths}}), encoding="utf-8"
        )
    return workspace


def test_glob_is_a_workspace_wide_read_too(tmp_path: Path) -> None:
    """The listing tool the rule never named."""
    workspace = _workspace(tmp_path, deny_paths=["secrets/*"])
    assert path_rule_denies_call(workspace, "tree", {}) is True
    assert path_rule_denies_call(workspace, "glob", {"pattern": "**/*"}) is True
    assert path_rule_denies_call(workspace, "git_diff", {}) is True
    assert path_rule_denies_call(workspace, "grep", {"pattern": "x"}) is True
    # A path nobody denied is still readable.
    assert path_rule_denies_call(workspace, "read_file", {"path": "src/app.py"}) is False


def test_the_glob_call_is_refused_end_to_end(tmp_path: Path) -> None:
    """The behaviour: the denied path never reaches the model."""
    import asyncio

    from minicc.agent.loop import run_agent
    from minicc.llm.base import LLMResponse

    workspace = _workspace(tmp_path, deny_paths=["secrets/*"])

    class _AsksForGlob:
        def __init__(self) -> None:
            self.calls = 0

        async def chat(self, messages, tools=None, on_delta=None, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return LLMResponse(
                    tool_calls=[{
                        "id": "call-0",
                        "type": "function",
                        "function": {"name": "glob", "arguments": json.dumps({"pattern": "**/*"})},
                    }],
                    finish_reason="tool_calls",
                )
            return LLMResponse(content="done", finish_reason="stop")

    seen: list[str] = []

    def on_tool(call: object, result: object) -> None:
        seen.append(
            (result.summary or "") + (result.output or "") + (result.head or "") + (result.tail or "")
        )

    asyncio.run(run_agent(
        _AsksForGlob(),
        build_registry(Editor(workspace)),
        [{"role": "user", "content": "看看工作区"}],
        on_tool=on_tool,
        should_allow=lambda _name, _call: True,
        workspace=workspace,
    ))
    assert not any("secrets/k.txt" in text for text in seen), (
        "glob listed a path the deny rules cover"
    )


def test_the_listing_tools_do_not_enumerate_sensitive_files(tmp_path: Path) -> None:
    """The built-in protection applies to the listing tools as well."""
    workspace = _workspace(tmp_path, deny_paths=None)
    registry = build_registry(Editor(workspace))
    for call in (
        ToolCall("glob", {"pattern": "**/*"}),
        ToolCall("tree", {}),
    ):
        result = registry.execute(call)
        text = (result.output or "") + (result.head or "") + (result.tail or "")
        assert ".env" not in text, (call.tool, text)
        assert "id_rsa" not in text, (call.tool, text)
        # The control: ordinary workspace content is still listed.
        assert "app.py" in text, (call.tool, text)


def test_read_file_still_refuses_those_files(tmp_path: Path) -> None:
    """The control: the protection the listing tools now follow."""
    workspace = _workspace(tmp_path, deny_paths=None)
    registry = build_registry(Editor(workspace))
    result = registry.execute(ToolCall("read_file", {"path": ".env"}))
    assert result.status == "error", result.summary
    assert "敏感" in result.summary, result.summary
