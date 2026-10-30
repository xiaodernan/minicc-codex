"""M8-T553: a trail under a non-directory ``.minicc`` is not a missing trail.

``_audit_paths`` answers 「有没有审计记录」 with ``is_file()`` and then
``exists()`` (M8-T552).  When ``.minicc`` itself is a regular file, the trail
path cannot exist: the audit writer could never have written a record, and
every write it tried to record was lost.  The view answered that state with
``return set(), None`` — the same answer as a workspace that never had a
trail.  Measured on HEAD on a non-repository workspace (the audit is the only
witness):

| 形状 | total_files | audit 理由 | diff(notes.md) |
| --- | --- | --- | --- |
| A .minicc 是普通文件 | 0 | 无 | clean，空补丁 |
| B 没有 .minicc（对照） | 0 | 无 | clean，空补丁 |
| C .minicc 是目录、没有审计文件（对照） | 0 | 无 | clean，空补丁 |
| D 可读审计，记了一次写（对照） | 1 | 无 | modified，整文件新增 |
| E .minicc/audit.jsonl 是目录（对照） | 0 | 不是一个文件 | clean，非空补丁 |

The fix asks whether the trail's parent exists but is not a directory: that is
a parent that cannot hold a trail, so it carries a reason.  A missing parent
and a directory parent with no trail are still ``None`` — those are true
absences, not failed reads.
"""

from __future__ import annotations

import json
from pathlib import Path

from minicc.changes import ChangeInspector

GOOD = json.dumps({"action": "write", "path": "notes.md"}, ensure_ascii=False)


def _workspace(root: Path) -> Path:
    workspace = root / "ws"
    workspace.mkdir()
    (workspace / "notes.md").write_text("hello\n", encoding="utf-8")
    (workspace / "readme.txt").write_text("free\n", encoding="utf-8")
    return workspace


def _minicc_is_a_file(workspace: Path) -> None:
    (workspace / ".minicc").write_text("not a directory\n", encoding="utf-8")


def _readable_trail(workspace: Path) -> None:
    trail = workspace / ".minicc" / "audit.jsonl"
    trail.parent.mkdir()
    trail.write_text(GOOD + "\n", encoding="utf-8")


def _directory_trail(workspace: Path) -> None:
    (workspace / ".minicc" / "audit.jsonl").mkdir(parents=True)


def test_a_trail_under_a_file_parent_is_not_a_missing_trail(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _minicc_is_a_file(workspace)
    summary = ChangeInspector(workspace).summary()
    reason = summary.get("audit_read_error")
    assert isinstance(reason, str) and reason, (
        f".minicc 是个普通文件，变更视图却答了「没有审计记录」：{summary}"
    )
    assert "父路径" in reason, reason
    assert "不是一个目录" in reason, reason
    assert summary["total_files"] == 0, summary


def test_the_diff_carries_the_parent_reason(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _minicc_is_a_file(workspace)
    diff = ChangeInspector(workspace).diff("notes.md")
    reason = diff.get("audit_read_error")
    assert isinstance(reason, str) and "父路径" in reason, diff


def test_a_modified_file_under_a_file_parent_does_not_diff_to_nothing(tmp_path: Path) -> None:
    """With the trail unreadable, 「clean」 would make the file its own baseline."""
    workspace = _workspace(tmp_path)
    _minicc_is_a_file(workspace)
    diff = ChangeInspector(workspace).diff("notes.md")
    assert diff["patch"].strip(), (
        f"审计记录读不出来，diff 把改过的文件画成了空补丁：{diff}"
    )
    assert "+hello" in diff["patch"], diff["patch"]


def test_the_control_no_minicc_is_still_none(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    summary = ChangeInspector(workspace).summary()
    assert summary["total_files"] == 0, summary
    assert summary.get("audit_read_error") is None, summary


def test_the_control_a_directory_parent_without_a_trail_is_still_none(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    (workspace / ".minicc").mkdir()
    summary = ChangeInspector(workspace).summary()
    assert summary["total_files"] == 0, summary
    assert summary.get("audit_read_error") is None, summary


def test_the_control_a_readable_trail_still_lists_the_write(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _readable_trail(workspace)
    summary = ChangeInspector(workspace).summary()
    assert [item["path"] for item in summary["files"]] == ["notes.md"], summary
    assert summary.get("audit_read_error") is None, summary


def test_the_control_a_directory_shaped_trail_keeps_its_own_reason(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _directory_trail(workspace)
    reason = ChangeInspector(workspace).summary().get("audit_read_error")
    assert isinstance(reason, str) and "不是一个文件" in reason, reason
    assert "父路径" not in reason, reason
