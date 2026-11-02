"""M8-T558: 一条被拒绝的操作，在变更面板里是一次修改。

`minicc/tools/editor.py` 的每个拒绝点都在落盘**之前**记一行（`_check_expected_digest`
的两种 digest 拒绝、`apply_edit` 的三种锚点拒绝），并且用同一个 `audit_level()`
把它们标成 warning——`/api/audit` 早就按这个级别过滤了。变更面板读同一份
`.minicc/audit.jsonl`，却只问「动作是不是会改文件的那种」，从不问「这一行的操作
到底发生了没有」。在 HEAD 上实测（每个形状一个独立工作区，经 `summary()` / `diff()`）：

| 形状 | 面板答 |
| --- | --- |
| A1 非仓库工作区，唯一一行是 `edit` + `拒绝: old 未命中任何位置` | `notes.md` modified，diff 把整个文件画成 +2 行 |
| A2 git 仓库、HEAD 与工作区同一个内容 | `notes.md` modified，但补丁是空的——面板说改了，详情说没改 |
| A3 `write` + `拒绝: STALE_CONTEXT (…)` | 同 A1 |
| A4 前缀变体：前导空格 / `Refused:` / `denied:` / 裸「拒绝」 | 四条都算一次修改 |
| A5 五条拒绝 + 一条真写 | `total_files=2`，其中一个文件从没被写过 |

对照（今天就该绿，防修法过头）：真改动先记、拒绝后记，仍然列出；描述里**含**
「拒绝」二字（`替换 1 处（旧文含 拒绝 二字）`）不是拒绝，仍然列出；没有 `detail`
键的记录仍然列出。

修法是问同一个家：`audit_level(action, detail) == "warning"` 的行没发生，
不点名任何文件，计数进 `audit_refused_records`。它和第五百三十九批那条一样
**不进** `diff()` 的 clean 捷径条件——拒绝行说「我没写」，也就没说「这个文件写过」。
"""

from __future__ import annotations

import json
import pathlib
from pathlib import Path

from minicc.changes import ChangeInspector

REPO = pathlib.Path(__file__).resolve().parents[1]

REFUSAL = "拒绝: old 未命中任何位置"


def _workspace(root: Path) -> Path:
    workspace = root / "ws"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "notes.md").write_text("hello\nworld\n", encoding="utf-8")
    (workspace / "readme.txt").write_text("free\n", encoding="utf-8")
    return workspace


def _audit(workspace: Path, records: list[dict]) -> None:
    audit = workspace / ".minicc" / "audit.jsonl"
    audit.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(json.dumps(record, ensure_ascii=False) for record in records)
    audit.write_text(body + "\n", encoding="utf-8")


def _record(action: str = "edit", path: str = "notes.md", **extra) -> dict:
    item = {"timestamp": "2026-11-02T00:00:00+00:00", "action": action, "path": path}
    item.update(extra)
    return item


# --------------------------------------------------------------------------
# 被拒绝的行不点名文件
# --------------------------------------------------------------------------

def test_a_refused_edit_is_not_answered_a_change(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _audit(workspace, [_record(detail=REFUSAL, before_digest="abc")])
    summary = ChangeInspector(workspace).summary()
    assert summary["total_files"] == 0, (
        f"一行「拒绝」什么都没写，面板却把 notes.md 算成改了：{summary}"
    )
    assert summary["audit_refused_records"] == 1, summary


def test_a_refused_edit_diffs_as_clean(tmp_path: Path) -> None:
    """A1 的详情页：拒绝行让整份文件被画成新增。"""
    workspace = _workspace(tmp_path)
    _audit(workspace, [_record(detail=REFUSAL, before_digest="abc")])
    diff = ChangeInspector(workspace).diff("notes.md")
    assert diff["status"] == "clean", diff
    assert diff["patch"] == "", diff


def test_a_refused_write_is_not_answered_a_change(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _audit(
        workspace,
        [_record("write", detail="拒绝: STALE_CONTEXT (digest 不匹配: expected a actual b)")],
    )
    summary = ChangeInspector(workspace).summary()
    assert [item["path"] for item in summary["files"]] == [], summary
    assert summary["audit_refused_records"] == 1, summary


def test_a_refused_create_does_not_name_the_file_it_refused(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _audit(workspace, [_record("create", "gone.md", detail="拒绝: 目标已存在")])
    summary = ChangeInspector(workspace).summary()
    assert [item["path"] for item in summary["files"]] == [], summary
    assert summary["audit_refused_records"] == 1, summary


def test_every_refusal_spelling_is_a_refusal(tmp_path: Path) -> None:
    """/api/audit 认的前缀，面板必须认同一份——包括前导空格与大小写。"""
    for index, detail in enumerate(
        (
            REFUSAL,
            "  " + REFUSAL,
            "Refused: anchor not found",
            "denied: too large",
            "拒绝",
        )
    ):
        workspace = _workspace(tmp_path / f"case{index}")
        _audit(workspace, [_record(detail=detail)])
        summary = ChangeInspector(workspace).summary()
        assert [item["path"] for item in summary["files"]] == [], (detail, summary)
        assert summary["audit_refused_records"] == 1, (detail, summary)


def test_five_refusals_count_five(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    (workspace / "other.md").write_text("brand new\n", encoding="utf-8")
    _audit(
        workspace,
        [_record(detail=REFUSAL)] * 5 + [_record("write", "other.md", detail="10 chars")],
    )
    summary = ChangeInspector(workspace).summary()
    assert [item["path"] for item in summary["files"]] == ["other.md"], summary
    assert summary["audit_refused_records"] == 5, summary


# --------------------------------------------------------------------------
# 对照：真正发生的改动仍然要列出来
# --------------------------------------------------------------------------

def test_a_real_change_recorded_before_a_refusal_still_lists(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _audit(
        workspace,
        [_record("write", detail="12 chars", after_digest="xyz"), _record(detail=REFUSAL)],
    )
    summary = ChangeInspector(workspace).summary()
    assert [item["path"] for item in summary["files"]] == ["notes.md"], summary
    assert summary["audit_refused_records"] == 1, summary


def test_a_change_whose_detail_only_says_the_word_is_not_a_refusal(tmp_path: Path) -> None:
    """「拒绝」出现在描述中间不是拒绝——前缀才是 `audit_level` 的判据。"""
    workspace = _workspace(tmp_path)
    _audit(workspace, [_record(detail="替换 1 处（旧文含 拒绝 二字）", after_digest="xyz")])
    summary = ChangeInspector(workspace).summary()
    assert [item["path"] for item in summary["files"]] == ["notes.md"], summary
    assert summary["audit_refused_records"] == 0, summary


def test_a_record_without_a_detail_is_still_a_change(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _audit(workspace, [_record("write")])
    summary = ChangeInspector(workspace).summary()
    assert [item["path"] for item in summary["files"]] == ["notes.md"], summary
    assert summary["audit_refused_records"] == 0, summary


def test_the_stored_level_does_not_decide(tmp_path: Path) -> None:
    """拒绝行写错了级别也还是拒绝：面板问规则，不信记录自己说的那格。"""
    workspace = _workspace(tmp_path)
    _audit(workspace, [_record(detail=REFUSAL, level="notice")])
    summary = ChangeInspector(workspace).summary()
    assert [item["path"] for item in summary["files"]] == [], summary


def test_a_refusal_does_not_hold_the_clean_shortcut(tmp_path: Path) -> None:
    """`readme.txt` 没被任何记录点名，拒绝行更没点过它——捷径照常走。"""
    workspace = _workspace(tmp_path)
    _audit(workspace, [_record(detail=REFUSAL)])
    diff = ChangeInspector(workspace).diff("readme.txt")
    assert diff["status"] == "clean", diff
    assert diff["patch"] == "", diff


def test_the_diff_payload_carries_the_refusal_count(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    (workspace / "other.md").write_text("new\n", encoding="utf-8")
    _audit(
        workspace,
        [_record(detail=REFUSAL), _record("write", "other.md", detail="4 chars")],
    )
    diff = ChangeInspector(workspace).diff("other.md")
    assert diff["audit_refused_records"] == 1, diff


def test_the_control_a_trail_of_only_real_changes_counts_nothing(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _audit(workspace, [_record("write", detail="12 chars")])
    summary = ChangeInspector(workspace).summary()
    assert summary["total_files"] == 1, summary
    assert summary["audit_refused_records"] == 0, summary


def test_the_control_a_missing_trail_counts_nothing(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    summary = ChangeInspector(workspace).summary()
    assert summary["total_files"] == 0, summary
    assert summary["audit_refused_records"] == 0, summary


def test_the_refusal_rule_has_one_home() -> None:
    """前缀表只有 `editor.py` 一份；面板问的是同一个 `audit_level`。"""
    holders = [
        path.name
        for path in sorted((REPO / "minicc").rglob("*.py"))
        if "_DENIED_PREFIXES = " in path.read_text(encoding="utf-8")
    ]
    assert holders == ["editor.py"], holders
    source = (REPO / "minicc" / "changes.py").read_text(encoding="utf-8")
    assert "audit_level(" in source, "变更面板不再自己判断拒绝，才有同一个答案"


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q", "-W", "error"]))
