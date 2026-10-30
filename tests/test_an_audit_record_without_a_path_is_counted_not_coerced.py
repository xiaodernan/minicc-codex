"""M8-T557: a record that names no path is not a record that named a file.

``_audit_paths`` pre-filtered on the substring ``"path"``, parsed the line,
and then coerced the field with ``str(item.get("path") or "")``.  Two
different lies came out of that one expression, measured on HEAD through
``summary()``:

| 形状 | 结果 |
| --- | --- |
| A `path: 123`，工作区里真有一个叫 `123` 的文件 | 那个文件被列成已改：记录点的是数字，面板答的是文件 |
| B `path: 456`（没有这个文件） | total=0，计数 0，没有任何披露 |
| C `path: null` / `""` / `"   "` | total=0，计数 0 |
| D `path: {"a": "b"}` / `["notes.md"]` | total=0，计数 0 |
| E 没有 `path` 键，但别的字段里带 `path` 字样 | total=0，计数 0 |
| F 没有 `path` 键，整行没有 `path` 字样 | 连解析都没发生（预过滤跳掉） |
| G 对照：`path: "123"`（字符串），文件存在 | total=1（这是真记录） |
| H 对照：一条坏记录 + 一个没被点名的文件 | diff 答 clean、空补丁（坏记录没点名它） |

The fix parses every line in the window, accepts only a non-blank string as
a path, and counts the rest in ``audit_records_without_path``.  A pathless
record names nothing, so unlike an unreadable line it does **not** hold the
``clean`` shortcut in ``diff()`` - it cannot have named the file being asked
about.  Neither count changes ``total_files``.
"""

from __future__ import annotations

import json
from pathlib import Path

from minicc.changes import ChangeInspector


def _audit(workspace: Path, *records: object) -> Path:
    audit = workspace / ".minicc" / "audit.jsonl"
    audit.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        record if isinstance(record, str) else json.dumps(record, ensure_ascii=False)
        for record in records
    ]
    audit.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return audit


def _workspace(root: Path) -> Path:
    workspace = root / "ws"
    workspace.mkdir()
    (workspace / "notes.md").write_text("hello\n", encoding="utf-8")
    return workspace


def test_a_numeric_path_does_not_name_an_existing_file(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    (workspace / "123").write_text("not this file\n", encoding="utf-8")
    _audit(workspace, {"action": "write", "path": 123})
    summary = ChangeInspector(workspace).summary()
    assert summary["total_files"] == 0, summary
    assert summary.get("audit_records_without_path") == 1, summary


def test_a_numeric_path_with_no_such_file_is_counted(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _audit(workspace, {"action": "write", "path": 456})
    summary = ChangeInspector(workspace).summary()
    assert summary["total_files"] == 0, summary
    assert summary.get("audit_records_without_path") == 1, summary


def test_a_null_path_is_counted(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _audit(workspace, {"action": "write", "path": None})
    summary = ChangeInspector(workspace).summary()
    assert summary.get("audit_records_without_path") == 1, summary


def test_a_blank_path_is_counted(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _audit(
        workspace,
        {"action": "write", "path": ""},
        {"action": "write", "path": "   "},
    )
    summary = ChangeInspector(workspace).summary()
    assert summary["total_files"] == 0, summary
    assert summary.get("audit_records_without_path") == 2, summary


def test_a_collection_path_is_counted(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _audit(
        workspace,
        {"action": "write", "path": {"a": "b"}},
        {"action": "write", "path": ["notes.md"]},
    )
    summary = ChangeInspector(workspace).summary()
    assert summary.get("audit_records_without_path") == 2, summary


def test_a_record_that_lost_its_path_key_is_counted(tmp_path: Path) -> None:
    """One line still says ``path`` somewhere; one lost the word entirely."""
    workspace = _workspace(tmp_path)
    _audit(
        workspace,
        {"action": "write", "detail": "the path is gone"},
        {"action": "write", "detail": "gone"},
    )
    summary = ChangeInspector(workspace).summary()
    assert summary.get("audit_records_without_path") == 2, summary


def test_a_string_path_that_looks_numeric_still_names_the_file(tmp_path: Path) -> None:
    """Control: ``"123"`` is a path; ``123`` is not.  Only the type decides."""
    workspace = _workspace(tmp_path)
    (workspace / "123").write_text("this file\n", encoding="utf-8")
    _audit(workspace, {"action": "write", "path": "123"})
    summary = ChangeInspector(workspace).summary()
    assert [item["path"] for item in summary["files"]] == ["123"], summary
    assert summary.get("audit_records_without_path", 0) == 0, summary


def test_the_control_a_good_record_counts_nothing(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _audit(workspace, {"action": "write", "path": "notes.md"})
    summary = ChangeInspector(workspace).summary()
    assert [item["path"] for item in summary["files"]] == ["notes.md"], summary
    assert summary.get("audit_records_without_path", 0) == 0, summary


def test_a_pathless_record_does_not_hold_the_clean_shortcut(tmp_path: Path) -> None:
    """Control: the record names no file, so the untouched file stays clean."""
    workspace = _workspace(tmp_path)
    (workspace / "readme.txt").write_text("free\n", encoding="utf-8")
    _audit(workspace, {"action": "write", "path": 456})
    diff = ChangeInspector(workspace).diff("readme.txt")
    assert diff["status"] == "clean", diff
    assert diff["patch"] == "", diff


def test_the_diff_carries_the_count(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _audit(
        workspace,
        {"action": "write", "path": "notes.md"},
        {"action": "write", "path": 456},
    )
    diff = ChangeInspector(workspace).diff("notes.md")
    assert diff.get("audit_records_without_path") == 1, diff
