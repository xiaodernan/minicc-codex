"""M8-T344 — Web 的读路由要用「它真正执行的那个工具」去问规则

M8-T290 把 deny 规则接到了 Web 的预览与差异两条读路由上，但它问的是**工具名**
——而路由问的名字必须**是它真正执行的那个工具**：

| 路由 | 实际执行 | 之前问的是 | 后果 |
| --- | --- | --- | --- |
| `changes(path)` | **git diff** | `read_file` | 工具轴上的 `deny.tools: ["git_diff"]` 对 agent 生效、对浏览器**失效** |
| `file_tree()` | **tree 遍历** | 只问了路径规则 | 工具轴上的 `deny.tools: ["tree"]` 同上 |
| `file_preview(path)` | 读文件 | `read_file` ✓ | 一致 |

实测：一份 `{"deny": {"tools": ["git_diff"]}}` 的规则下，agent 自己的 `git_diff`
调用被拒（`tool_denied_by_rule(workspace, "git_diff", …) == True`），而 Web 的
差异路由问 `read_file` 得到 False —— 浏览器成了绕开规则的通道。

本门钉住：差异路由问 `git_diff`、文件树问 `tree`；路径轴的行为**没有因为换
工具名而丢失**；两面对同一条规则给出同一个答案；无规则时照旧服务。
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from minicc.web import AgentService


def _service(workspace: Path) -> AgentService:
    config = SimpleNamespace(
        yolo=False,
        max_concurrent_tasks=1,
        sandbox_mode="host",
        sandbox_image="python:3.11-slim",
        base_url="https://example.test/v1",
        api_key="test-key",
        model="test-model",
        timeout=10,
        tool_mode="auto",
        reasoning_effort="high",
        max_turns=4,
        compact_threshold=300_000,
        context_window_tokens=300_000,
    )
    return AgentService(workspace, config)


def _workspace(tmp_path: Path, *, deny: dict | None) -> Path:
    workspace = tmp_path / "ws"
    (workspace / "data").mkdir(parents=True)
    (workspace / "data" / "secret.txt").write_text("TOPSECRET\n", encoding="utf-8")
    (workspace / "public.txt").write_text("hello\n", encoding="utf-8")
    if deny is not None:
        (workspace / ".minicc").mkdir()
        (workspace / ".minicc" / "permissions.json").write_text(
            json.dumps({"deny": deny}), encoding="utf-8"
        )
    return workspace


def test_a_tool_rule_on_git_diff_refuses_the_diff_route(tmp_path: Path) -> None:
    """The route performs a git diff, so that is the tool the rule is asked about."""
    workspace = _workspace(tmp_path, deny={"tools": ["git_diff"]})
    service = _service(workspace)
    try:
        result = service.changes("public.txt")
        assert result.get("status") == "error", (
            "the diff route served a call the agent would be refused"
        )
        wide = service.changes()
        assert wide.get("status") == "error", wide
    finally:
        service.shutdown()


def test_a_tool_rule_on_tree_refuses_the_file_tree_route(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, deny={"tools": ["tree"]})
    service = _service(workspace)
    try:
        result = service.file_tree()
        assert result.get("status") == "error", (
            "the file tree route served a call the agent would be refused"
        )
        assert not (result.get("entries") or []), result
    finally:
        service.shutdown()


def test_the_path_axis_still_reaches_the_diff_route(tmp_path: Path) -> None:
    """The control: asking about another tool must not lose the path rules."""
    workspace = _workspace(tmp_path, deny={"paths": ["data/*"]})
    service = _service(workspace)
    try:
        result = service.changes("data/secret.txt")
        assert result.get("status") == "error", (
            "the path rule stopped reaching the diff route"
        )
    finally:
        service.shutdown()


def test_the_two_faces_give_the_same_answer(tmp_path: Path) -> None:
    """The agent's own call is refused by the same rule the browser now faces."""
    from minicc.audit import tool_denied_by_rule

    workspace = _workspace(tmp_path, deny={"tools": ["git_diff"]})
    assert tool_denied_by_rule(workspace, "git_diff", {}) is True
    assert tool_denied_by_rule(workspace, "git_diff", {"path": "public.txt"}) is True


def test_without_rules_the_routes_still_serve(tmp_path: Path) -> None:
    """The control: no rules, no refusal."""
    workspace = _workspace(tmp_path, deny=None)
    service = _service(workspace)
    try:
        assert service.file_tree().get("status") != "error"
        assert service.changes("public.txt").get("status") != "error"
    finally:
        service.shutdown()
