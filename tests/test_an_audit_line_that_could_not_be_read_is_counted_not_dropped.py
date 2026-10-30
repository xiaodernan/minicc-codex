"""M8-T550: an audit line that could not be read is not a line that never was.

``_audit_paths`` pre-filters lines containing ``"path"``, then parses them.
A line that fails ``json.loads`` was skipped without a word; a line that
parses into anything but an object crashed the whole panel — ``item.get`` on
a list.  Measured on HEAD through ``summary()``:

| 形状 | 结果 |
| --- | --- |
| A 一条好记录 + 一行 `["path", …]` | summary 与 diff 都抛 AttributeError |
| B 一条好记录 + 一行截断的 JSON | total=1，无任何披露 |
| C 只有好记录（对照） | total=1 |
| D 287000 字节的尾巴，首行被 256KB 切口截断 | total=1，无任何披露 |

The fix counts the lines the window could not read (``audit_unreadable_
lines``) and never lets one crash the answer.  The first line of a tail cut
at the byte ceiling is a *known* partial line, not an unreadable one — it is
dropped before the count, so a big audit history does not bill itself a
broken record on every read.  A non-zero count also holds the ``clean``
shortcut in ``diff()``: the bad line could have named this file.
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


def _audit(workspace: Path, body: str) -> Path:
    audit = workspace / ".minicc" / "audit.jsonl"
    audit.parent.mkdir(parents=True, exist_ok=True)
    audit.write_text(body, encoding="utf-8")
    return audit


def test_a_line_that_is_not_an_object_does_not_crash_the_summary(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _audit(workspace, GOOD + "\n" + '["path", "notes.md"]' + "\n")
    summary = ChangeInspector(workspace).summary()
    assert [item["path"] for item in summary["files"]] == ["notes.md"], summary
    assert summary.get("audit_unreadable_lines") == 1, summary


def test_a_line_that_is_not_an_object_does_not_crash_the_diff(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _audit(workspace, GOOD + "\n" + '["path", "notes.md"]' + "\n")
    diff = ChangeInspector(workspace).diff("notes.md")
    assert "+hello" in diff["patch"], diff


def test_a_truncated_json_line_is_counted(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _audit(workspace, GOOD + "\n" + '{"action": "write", "path": "no' + "\n")
    summary = ChangeInspector(workspace).summary()
    assert [item["path"] for item in summary["files"]] == ["notes.md"], summary
    assert summary.get("audit_unreadable_lines") == 1, summary


def test_the_partial_first_line_of_a_cut_tail_is_not_counted(tmp_path: Path) -> None:
    """A >256KB trail starts mid-record by construction, not by corruption.

    The records are ~900 bytes each, so the cut's fragment sits inside the
    500-line window: billing it would be a false 「读不出来的记录」.
    """
    workspace = _workspace(tmp_path)
    long_record = json.dumps(
        {"action": "write", "padding": "p" * 850, "path": "notes.md"}, ensure_ascii=False
    )
    line = long_record + "\n"
    per = len(line.encode("utf-8"))
    body = line * 600
    cut = len(body.encode("utf-8")) - 256_000
    assert 0 < cut % per < long_record.index('"path"'), (cut, per)
    _audit(workspace, body)
    summary = ChangeInspector(workspace).summary()
    assert [item["path"] for item in summary["files"]] == ["notes.md"], summary
    assert summary.get("audit_unreadable_lines") == 0, summary


def test_the_diff_carries_the_unreadable_count(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _audit(workspace, GOOD + "\n" + '["path", "notes.md"]' + "\n")
    diff = ChangeInspector(workspace).diff("notes.md")
    assert diff.get("audit_unreadable_lines") == 1, diff


def test_a_bad_line_holds_the_clean_shortcut(tmp_path: Path) -> None:
    """No readable record names readme.txt, and the bad line might have."""
    workspace = _workspace(tmp_path)
    _audit(workspace, '["path", "notes.md"]' + "\n")
    diff = ChangeInspector(workspace).diff("readme.txt")
    assert diff["patch"].strip(), (
        f"有一行读不出来，diff 却把没被任何记录点名的文件画成没改：{diff}"
    )
    assert "+free" in diff["patch"], diff["patch"]


def test_the_control_only_readable_records_count_nothing(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _audit(workspace, GOOD + "\n")
    summary = ChangeInspector(workspace).summary()
    assert [item["path"] for item in summary["files"]] == ["notes.md"], summary
    assert summary.get("audit_unreadable_lines", 0) == 0, summary
    assert summary.get("audit_read_error") is None, summary


def test_the_control_a_missing_trail_counts_nothing(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    summary = ChangeInspector(workspace).summary()
    assert summary["total_files"] == 0, summary
    assert summary.get("audit_unreadable_lines", 0) == 0, summary
