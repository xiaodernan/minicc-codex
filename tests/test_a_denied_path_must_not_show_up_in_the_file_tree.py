"""M8-T337 — 被 deny 的路径，在文件树面板里也不该露面

M8-T290 说 `permissions.json` 的 deny 规则是绝对否决，并且亲手修了 Web 面的
两条读路由：预览（`file_preview`）与差异（`changes`）。**文件树**
（`file_tree` → `/api/files`）漏了：它列的是工作区，规则却从来没问过。

于是同一个策略有两张脸：

* agent 侧：`tree` 调用在有路径规则的工作区被**整条拒绝**（M8-T290 的规则）；
* Web 侧：面板照旧列出 `data/secret.txt`——路径、名字、大小都在。

deny 规则保护的是**路径**，所以被拒的路径不该在任何一张脸上可见。本门钉住：
被规则覆盖的文件不列出；被规则整体覆盖的目录（`data/*` 这种）连目录本身
也不列出；没被规则碰到的路径照旧列出（面板不是一刀切）；没有规则的工作区
行为不变。
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


def _workspace(tmp_path: Path, *, deny_paths: list[str] | None) -> Path:
    workspace = tmp_path / "ws"
    (workspace / "data").mkdir(parents=True)
    (workspace / "data" / "secret.txt").write_text("TOPSECRET\n", encoding="utf-8")
    (workspace / "data" / "notes.md").write_text("ordinary\n", encoding="utf-8")
    (workspace / "public.txt").write_text("hello\n", encoding="utf-8")
    if deny_paths is not None:
        (workspace / ".minicc").mkdir()
        (workspace / ".minicc" / "permissions.json").write_text(
            json.dumps({"deny": {"paths": deny_paths}}), encoding="utf-8"
        )
    return workspace


def _paths(result: dict) -> set[str]:
    return {str(entry.get("path")) for entry in result.get("entries") or []}


def test_a_denied_file_is_not_listed(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, deny_paths=["data/secret.txt"])
    service = _service(workspace)
    try:
        listed = _paths(service.file_tree())
        assert "data/secret.txt" not in listed, sorted(listed)
    finally:
        service.shutdown()


def test_a_denied_directory_is_not_listed_either(tmp_path: Path) -> None:
    """``data/*`` covers the whole subtree, so the container goes too."""
    workspace = _workspace(tmp_path, deny_paths=["data/*"])
    service = _service(workspace)
    try:
        listed = _paths(service.file_tree())
        assert "data" not in listed, sorted(listed)
        assert "data/secret.txt" not in listed, sorted(listed)
        assert "data/notes.md" not in listed, sorted(listed)
    finally:
        service.shutdown()


def test_a_path_with_no_rule_is_still_listed(tmp_path: Path) -> None:
    """The control: the rule is a list, not a blanket ban on the panel."""
    workspace = _workspace(tmp_path, deny_paths=["data/secret.txt"])
    service = _service(workspace)
    try:
        listed = _paths(service.file_tree())
        assert "public.txt" in listed, sorted(listed)
        assert "data/notes.md" in listed, sorted(listed)
        assert "data" in listed, sorted(listed)
    finally:
        service.shutdown()


def test_a_workspace_with_no_rules_lists_everything(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, deny_paths=None)
    service = _service(workspace)
    try:
        listed = _paths(service.file_tree())
        assert {"public.txt", "data", "data/secret.txt", "data/notes.md"} <= listed, sorted(listed)
    finally:
        service.shutdown()


def test_the_agent_side_still_refuses_the_whole_tree(tmp_path: Path) -> None:
    """The two faces agree: a denied path is not visible through either."""
    from minicc.audit import deny_rule_covers_path, deny_rule_names_paths

    workspace = _workspace(tmp_path, deny_paths=["data/*"])
    assert deny_rule_names_paths(workspace) is True
    assert deny_rule_covers_path(workspace, "data/secret.txt") is True
    assert deny_rule_covers_path(workspace, "data") is True
    assert deny_rule_covers_path(workspace, "public.txt") is False
