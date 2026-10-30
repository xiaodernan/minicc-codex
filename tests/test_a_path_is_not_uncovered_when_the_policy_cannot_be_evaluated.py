"""M8-T555 — 策略读不出来时，这条路径不是「没被规则覆盖」

`minicc/audit.py` 里「这条路径被 deny 规则覆盖吗」只有一个家：
`deny_rule_covers_path`。它的三个同门（`tool_denied_by_rule`、
`deny_rule_names_paths`、`path_rule_refusal_reason`）在 M8-T526 之后遵守同一
条判词：**读不出来的策略 = 规则未知 = 拒绝**。这个家没有：它把
`load_permission_rules` 的 error 丢掉，OSError 也答成 False——于是「策略读
不出来」被答成「这条路径没被拒绝」。

实测（修前，本机 Python 3.11.1）：

  permissions.json 合法且覆盖 secrets/key.txt   covers=True
  permissions.json 合法但不覆盖                  covers=False   （应当如此）
  permissions.json 非法（错 JSON）               covers=False   ← 同门答 True
  permissions.json 是目录                        covers=False   ← 同门答 True
  permissions.json 读时 PermissionError          covers=False   ← 同门答 True
  没有 permissions.json                          covers=False   （应当如此）

今天唯一的调用面（Web 文件树）先在工具轴上整条拒绝（M8-T526），所以浏览器
没有漏出被保护的路径；漏的是**这个家的判词**——它被 `__all__` 导出成新读路
由的「唯一的家」（T337/T338/T344 都是新路由忘了问），谁直接问它，谁就继承
了「未知 = 没有规则」。本门钉住：未知策略覆盖每一条路径；没有策略照旧一条
也不覆盖；可读策略照旧只覆盖它写下的那些。

（还有一层本批没碰：`load_permission_rules` 自己把 stat 的 PermissionError
答成「没有规则，也没有错」，于是四个同门在那种工作区里都答 False，文件树面
板会把待保护的路径列出来——见第五百三十七批 §7 第 1 位。）
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from minicc.audit import (
    deny_rule_covers_path,
    deny_rule_names_paths,
    tool_denied_by_rule,
)
from minicc.web import AgentService

DENIED = "secrets/key.txt"
DENIED_CONTAINER = "secrets"
UNTOUCHED = "public.txt"


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "ws"
    (workspace / "secrets").mkdir(parents=True)
    (workspace / "secrets" / "key.txt").write_text("SECRET\n", encoding="utf-8")
    (workspace / "public.txt").write_text("hello\n", encoding="utf-8")
    return workspace


def _policy(workspace: Path, body: str | None) -> Path:
    (workspace / ".minicc").mkdir()
    target = workspace / ".minicc" / "permissions.json"
    if body is not None:
        target.write_text(body, encoding="utf-8")
    return target


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


# --- the unknown policy covers every path -----------------------------------


def test_a_malformed_policy_covers_the_path_it_denied(tmp_path: Path) -> None:
    """The headline: a broken rules file must not turn "covered" into "free"."""
    workspace = _workspace(tmp_path)
    _policy(workspace, "{not json")
    assert deny_rule_covers_path(workspace, DENIED) is True
    assert deny_rule_covers_path(workspace, DENIED_CONTAINER) is True
    # the three siblings already answer this way (M8-T526)
    assert tool_denied_by_rule(workspace, "read_file", {"path": DENIED}) is True
    assert deny_rule_names_paths(workspace) is True


def test_a_policy_path_that_is_a_directory_covers_the_path_it_denied(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    (workspace / ".minicc").mkdir()
    (workspace / ".minicc" / "permissions.json").mkdir()
    assert deny_rule_covers_path(workspace, DENIED) is True
    assert deny_rule_names_paths(workspace) is True


def test_a_policy_that_cannot_be_read_covers_the_path_it_denied(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = _workspace(tmp_path)
    target = _policy(workspace, json.dumps({"deny": {"paths": ["secrets/*"]}}))
    real = Path.read_text

    def read_text(self, *args, **kwargs):
        if Path(self) == target:
            raise PermissionError(13, "Access is denied")
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_text)
    assert deny_rule_covers_path(workspace, DENIED) is True
    assert tool_denied_by_rule(workspace, "read_file", {"path": DENIED}) is True


# --- the boundary did not move ----------------------------------------------


def test_a_missing_policy_still_covers_nothing(tmp_path: Path) -> None:
    """The normal case: no policy file, no rules, nothing covered."""
    workspace = _workspace(tmp_path)
    assert deny_rule_covers_path(workspace, DENIED) is False
    assert deny_rule_covers_path(workspace, DENIED_CONTAINER) is False
    assert deny_rule_names_paths(workspace) is False


def test_a_readable_policy_still_draws_its_own_line(tmp_path: Path) -> None:
    """Control: a policy that can be read is still a list, not a blanket ban."""
    workspace = _workspace(tmp_path)
    _policy(workspace, json.dumps({"deny": {"paths": ["secrets/*"]}}))
    assert deny_rule_covers_path(workspace, DENIED) is True
    assert deny_rule_covers_path(workspace, DENIED_CONTAINER) is True
    assert deny_rule_covers_path(workspace, UNTOUCHED) is False


def test_a_readable_policy_naming_another_path_covers_neither(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    _policy(workspace, json.dumps({"deny": {"paths": ["other.txt"]}}))
    assert deny_rule_covers_path(workspace, DENIED) is False
    assert deny_rule_covers_path(workspace, UNTOUCHED) is False


# --- the surface that asks it keeps its promise ------------------------------


def test_the_tree_panel_still_does_not_list_the_denied_path(tmp_path: Path) -> None:
    """The only caller asks both axes; an unreadable policy stays invisible."""
    workspace = _workspace(tmp_path)
    _policy(workspace, "{not json")
    service = _service(workspace)
    try:
        result = service.file_tree()
    finally:
        service.shutdown()
    listed = {str(entry.get("path")) for entry in result.get("entries") or []}
    assert DENIED not in listed, sorted(listed)
    assert DENIED_CONTAINER not in listed, sorted(listed)
