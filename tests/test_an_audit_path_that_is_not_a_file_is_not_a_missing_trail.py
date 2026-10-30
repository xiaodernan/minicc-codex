"""M8-T552: an audit path that is not a file is not a missing trail.

``_audit_paths`` decided 「有没有审计记录」 with ``is_file()``.  A directory
named ``audit.jsonl`` is present but cannot be read as the trail, and it got
the same answer as a trail that was never written.  Measured on HEAD on a
non-repository workspace (the audit is the only witness):

| 形状 | total_files | audit 理由 | diff(notes.md) |
| --- | --- | --- | --- |
| A .minicc/audit.jsonl 是目录 | 0 | 无 | clean，空补丁 |
| B 没有审计文件（对照） | 0 | 无 | clean，空补丁 |
| C 可读审计，记了一次写（对照） | 1 | 无 | modified，整文件新增 |

The fix asks ``exists()`` after ``is_file()`` said no: a present path that
cannot be read as a trail carries a reason, the same way the unreadable-file
shapes of M8-T549 do.  A missing trail is still ``None`` — that is a true
statement, not a failed read.
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


def _directory_trail(workspace: Path) -> None:
    trail = workspace / ".minicc" / "audit.jsonl"
    trail.mkdir(parents=True)
    (trail / "moved-away").write_text("x\n", encoding="utf-8")


def _readable_trail(workspace: Path) -> None:
    trail = workspace / ".minicc" / "audit.jsonl"
    trail.parent.mkdir(parents=True, exist_ok=True)
    trail.write_text(GOOD + "\n", encoding="utf-8")


def test_a_directory_shaped_trail_is_not_a_missing_trail(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _directory_trail(workspace)
    summary = ChangeInspector(workspace).summary()
    reason = summary.get("audit_read_error")
    assert isinstance(reason, str) and reason, (
        f"审计记录是个目录，变更视图却答了「没有记录」：{summary}"
    )
    assert "不是一个文件" in reason, reason
    assert summary["total_files"] == 0, summary


def test_the_diff_carries_the_same_reason(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _directory_trail(workspace)
    diff = ChangeInspector(workspace).diff("notes.md")
    reason = diff.get("audit_read_error")
    assert isinstance(reason, str) and reason, diff


def test_a_modified_file_does_not_diff_to_nothing(tmp_path: Path) -> None:
    """With the trail unreadable, 「clean」 would make the file its own baseline."""
    workspace = _workspace(tmp_path)
    _directory_trail(workspace)
    diff = ChangeInspector(workspace).diff("notes.md")
    assert diff["patch"].strip(), (
        f"审计记录读不出来，diff 把改过的文件画成了空补丁：{diff}"
    )
    assert "+hello" in diff["patch"], diff["patch"]


def test_the_control_a_missing_trail_is_still_none(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    summary = ChangeInspector(workspace).summary()
    assert summary["total_files"] == 0, summary
    assert summary.get("audit_read_error") is None, summary


def test_the_control_a_readable_trail_still_lists_the_write(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _readable_trail(workspace)
    summary = ChangeInspector(workspace).summary()
    assert [item["path"] for item in summary["files"]] == ["notes.md"], summary
    assert summary.get("audit_read_error") is None, summary


def test_the_control_a_clean_file_still_diffs_to_nothing(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _readable_trail(workspace)
    diff = ChangeInspector(workspace).diff("readme.txt")
    assert diff.get("audit_read_error") is None, diff
    assert diff["patch"] == "", diff
