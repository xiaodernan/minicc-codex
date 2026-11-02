"""M8-T559: 说不出动作的审计记录，被答成「改了这个文件」。

`_audit_paths` 认一条记录的动作只有两步：`action = str(item.get("action") or "")
.strip().lower()`，然后 `if action and action not in _CHANGING_AUDIT_ACTIONS:
continue`。那个 `action and` 是本批的伤口：**说不出动作的记录绕过了过滤器**，被
当成一次改动。第五百三十九批改的是同一条读取里的 `path`，本批改 `action`——同一个
`str()` 强转的另一半。在 `3d99c6f` 上实测（每个形状一个独立非仓库工作区，经
`summary()` / `diff()`）：

| 形状 | 修前 |
| --- | --- |
| `{"path": "notes.md", …}` 整条没有 `action` | `total=1`，列成 modified，diff 把整份文件画成新增 |
| `action: null` / `""` / `"   "` / `"\t"` | 同上——空串让 `action and` 短路 |
| `action: ["write"]` / `{"name": "write"}` / `123` / `true` | `total=0`，四个计数器全 0：`str()` 出来的形状落不进集合，就被当非变更跳过 |
| `action: "READ"` | 不列（大小写归一本来就是对的） |
| `action: " write "` | 列出（前后空格归一本来就是对的） |
| `action: "read"` | 不列（对） |

修法：只有**非空字符串**才是一个动作，否则计数进 `audit_records_without_action`。
与第五百三十九、五百四十批相反，这条计数**进** `diff()` 的 clean 捷径条件：一条说不出
动作的记录仍然点了一个文件，那个文件可能就是正被问的这一个——与第五百三十二批读不出来
的行同一条理由。被拒绝的行（五百四十批）与说不出路径的行（五百三十九批）什么都没点名，
所以它们不挡捷径。
"""

from __future__ import annotations

import json
from pathlib import Path

from minicc.changes import ChangeInspector

WRITE = {"action": "write", "path": "notes.md", "detail": "6 chars"}


def _workspace(root: Path) -> Path:
    workspace = root / "ws"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "notes.md").write_text("hello\n", encoding="utf-8")
    (workspace / "readme.txt").write_text("free\n", encoding="utf-8")
    return workspace


def _audit(workspace: Path, records: list[dict]) -> None:
    trail = workspace / ".minicc" / "audit.jsonl"
    trail.parent.mkdir(parents=True, exist_ok=True)
    trail.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
        encoding="utf-8",
    )


# --------------------------------------------------------------------------
# 说不出动作 = 说不清有没有改动
# --------------------------------------------------------------------------

def test_a_record_without_an_action_is_not_answered_a_change(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _audit(workspace, [{"path": "notes.md", "detail": "6 chars"}])
    summary = ChangeInspector(workspace).summary()
    assert [item["path"] for item in summary["files"]] == [], (
        f"整条记录没说它是什么动作，面板却答「改了」：{summary}"
    )
    assert summary["audit_records_without_action"] == 1, summary


def test_a_null_action_is_not_answered_a_change(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _audit(workspace, [{"action": None, "path": "notes.md"}])
    summary = ChangeInspector(workspace).summary()
    assert [item["path"] for item in summary["files"]] == [], summary
    assert summary["audit_records_without_action"] == 1, summary


def test_a_blank_action_is_not_answered_a_change(tmp_path: Path) -> None:
    for index, action in enumerate(("", "   ", "\t")):
        workspace = _workspace(tmp_path / f"blank{index}")
        _audit(workspace, [{"action": action, "path": "notes.md"}])
        summary = ChangeInspector(workspace).summary()
        assert [item["path"] for item in summary["files"]] == [], (action, summary)
        assert summary["audit_records_without_action"] == 1, (action, summary)


def test_an_action_wrapped_in_a_container_is_counted_not_dropped(tmp_path: Path) -> None:
    """「write」装进容器里就不是动作了——但它是**读出来了**的记录，得记账。"""
    for index, action in enumerate((["write"], {"name": "write"}, 123, True)):
        workspace = _workspace(tmp_path / f"boxed{index}")
        _audit(workspace, [{"action": action, "path": "notes.md"}])
        summary = ChangeInspector(workspace).summary()
        assert [item["path"] for item in summary["files"]] == [], (action, summary)
        assert summary["audit_records_without_action"] == 1, (action, summary)
        assert summary["audit_unreadable_lines"] == 0, (action, summary)


def test_a_record_with_neither_action_nor_path_is_counted_once(tmp_path: Path) -> None:
    """动作闸门在前：它不再一路走到路径闸门，也就不会被记两次。"""
    workspace = _workspace(tmp_path)
    _audit(workspace, [{"action": ["write"]}])
    summary = ChangeInspector(workspace).summary()
    assert summary["audit_records_without_action"] == 1, summary
    assert summary["audit_records_without_path"] == 0, summary


def test_an_unusable_action_holds_the_clean_shortcut(tmp_path: Path) -> None:
    """它点了一个文件，只是说不出动作——那个文件可能就是被问的这一个。"""
    workspace = _workspace(tmp_path)
    _audit(workspace, [{"action": ["write"], "path": "readme.txt"}])
    diff = ChangeInspector(workspace).diff("readme.txt")
    assert diff["patch"].strip(), (
        f"动作说不出，diff 却把它点名的文件画成没改：{diff}"
    )
    assert diff["audit_records_without_action"] == 1, diff


def test_the_diff_payload_carries_the_action_count(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _audit(workspace, [{"action": 123, "path": "readme.txt"}, WRITE])
    diff = ChangeInspector(workspace).diff("notes.md")
    assert diff["audit_records_without_action"] == 1, diff


# --------------------------------------------------------------------------
# 对照：归一化本来就对的那些形状
# --------------------------------------------------------------------------

def test_the_control_an_upper_case_non_change_lists_nothing(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _audit(workspace, [{"action": "READ", "path": "notes.md"}])
    summary = ChangeInspector(workspace).summary()
    assert [item["path"] for item in summary["files"]] == [], summary
    assert summary["audit_records_without_action"] == 0, summary


def test_the_control_a_padded_real_action_still_lists(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _audit(workspace, [{"action": " write ", "path": "notes.md"}])
    summary = ChangeInspector(workspace).summary()
    assert [item["path"] for item in summary["files"]] == ["notes.md"], summary
    assert summary["audit_records_without_action"] == 0, summary


def test_the_control_a_real_write_still_lists(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _audit(workspace, [WRITE])
    summary = ChangeInspector(workspace).summary()
    assert summary["total_files"] == 1, summary
    assert summary["audit_records_without_action"] == 0, summary


def test_the_control_a_refusal_still_does_not_hold_the_shortcut(tmp_path: Path) -> None:
    """第五百四十批那条对照在这里必须仍然绿：新计数挡住了捷径，拒绝行没有。"""
    workspace = _workspace(tmp_path)
    _audit(
        workspace,
        [{"action": "edit", "path": "notes.md", "detail": "拒绝: old 未命中任何位置"}],
    )
    diff = ChangeInspector(workspace).diff("readme.txt")
    assert diff["status"] == "clean", diff
    assert diff["patch"] == "", diff


def test_the_control_a_missing_trail_counts_nothing(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    summary = ChangeInspector(workspace).summary()
    assert summary["total_files"] == 0, summary
    assert summary["audit_records_without_action"] == 0, summary


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q", "-W", "error"]))
