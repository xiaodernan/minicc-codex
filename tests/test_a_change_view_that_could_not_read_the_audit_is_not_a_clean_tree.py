"""M8-T549: a change view that could not read the audit may not answer 「没有变更」.

``_audit_paths`` is the fallback for files git cannot see, and its whole
body sat inside ``except (OSError, ValueError, TypeError): return set()`` —
the same empty set an audit trail with no writes produces.  Measured on
HEAD, through ``summary()`` and ``diff()`` (a non-repository workspace,
where the audit is the only witness):

| 形状 | total_files | audit 理由 | diff(notes.md) |
| --- | --- | --- | --- |
| A 审计文件打不开（PermissionError） | 0 | 无 | clean，空补丁 |
| B 打得开，取大小的 stat 失败 | 0 | 无 | clean，空补丁 |
| B2 「它存在吗」这一问就失败 | 抛出 OSError | — | — |
| C 没有审计文件（支持的形态） | 0 | 无 | clean，空补丁 |
| D 审计可读，记了一次写 | 1（notes.md） | 无 | modified，整文件新增 |
| F 先读到截断，再读失败 | 0，仍称 truncated=True | 无 | — |

A, B and F are "I could not read the trail"; C is a readable fact.  B2 is
worse than silence: ``Path.is_file`` on 3.11 does not swallow OSError, and
the existence check sat outside the try, so one unreadable stat turned the
whole summary into a 500.  The per-file route had the same collapse one
level down: with the audit blind, ``status`` fell back to ``clean`` and the
clean shortcut copied the file onto its own baseline — an empty patch for
a file that could have changed.

The fix separates 「the trail is empty」 from 「the trail could not be
read」: ``_audit_paths`` returns ``(paths, reason)`` and wraps every read
(existence, open, size, content) in the same refusal; ``summary()`` and
``diff()`` carry ``audit_read_error``; the clean shortcut no longer fires
while the audit is blind; and a truncation claim belongs to the read that
made it, not to a later failed one.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
from pathlib import Path

import pytest

from minicc.changes import ChangeInspector


def _git(workspace: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=str(workspace), capture_output=True, encoding="utf-8"
    )


def _plain(root: Path) -> Path:
    """A workspace with no repository: the audit is the only witness."""
    workspace = root / "ws"
    workspace.mkdir()
    (workspace / "notes.md").write_text("hello\n", encoding="utf-8")
    (workspace / "readme.txt").write_text("free\n", encoding="utf-8")
    return workspace


def _repo(root: Path) -> Path:
    workspace = root / "ws"
    workspace.mkdir()
    _git(workspace, "init")
    _git(workspace, "config", "user.email", "t@example.test")
    _git(workspace, "config", "user.name", "t")
    (workspace / "a.txt").write_text("one\n", encoding="utf-8")
    # Ignored outright: git status never mentions notes.md, so only the
    # audit trail can witness a write to it.
    (workspace / ".gitignore").write_text("notes.md\n", encoding="utf-8")
    _git(workspace, "add", "a.txt", ".gitignore")
    _git(workspace, "commit", "-m", "init")
    (workspace / "notes.md").write_text("hello\n", encoding="utf-8")
    return workspace


def _write_audit(workspace: Path, *, records: int = 1) -> Path:
    audit = workspace / ".minicc" / "audit.jsonl"
    audit.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"action": "write", "path": "notes.md"}, ensure_ascii=False)
    audit.write_text("\n".join([line] * records) + "\n", encoding="utf-8")
    return audit


class _DenyRead:
    """Make one audit path unreadable, one way per shape.

    ``open`` denies ``Path.open``; ``stat_after_open`` lets the open succeed
    and fails the stat that follows it (the size probe); ``is_file`` denies
    the existence check itself — the one that used to crash the summary.
    """

    def __init__(
        self,
        target: Path,
        *,
        open_denied: bool = True,
        stat_after_open: bool = False,
        is_file: bool = False,
    ):
        self.target = target
        self.open_denied = open_denied
        self.stat_after_open = stat_after_open
        self.is_file = is_file
        self.opened = False

    def __enter__(self):
        self.real_open = pathlib.Path.open
        self.real_stat = pathlib.Path.stat
        self.real_is_file = pathlib.Path.is_file
        probe = self

        def open_(self_, *args, **kwargs):
            if self_ == probe.target and probe.open_denied:
                raise PermissionError(13, "Access is denied", str(self_))
            if self_ == probe.target:
                probe.opened = True
            return probe.real_open(self_, *args, **kwargs)

        def stat_(self_, *args, **kwargs):
            if self_ == probe.target and probe.opened and probe.stat_after_open:
                probe.opened = False
                raise OSError(5, "I/O error", str(self_))
            return probe.real_stat(self_, *args, **kwargs)

        def is_file_(self_):
            if self_ == probe.target and probe.is_file:
                raise OSError(5, "I/O error", str(self_))
            return probe.real_is_file(self_)

        pathlib.Path.open = open_
        pathlib.Path.stat = stat_
        pathlib.Path.is_file = is_file_
        return self

    def __exit__(self, *exc):
        pathlib.Path.open = self.real_open
        pathlib.Path.stat = self.real_stat
        pathlib.Path.is_file = self.real_is_file


def test_a_permission_failure_on_the_audit_is_not_an_empty_trail(tmp_path: Path) -> None:
    workspace = _plain(tmp_path)
    audit = _write_audit(workspace)

    with _DenyRead(audit):
        summary = ChangeInspector(workspace).summary()

    reason = summary.get("audit_read_error")
    assert isinstance(reason, str) and reason, (
        f"读不出审计记录，变更视图却答了「没有审计记录」：{summary}"
    )
    assert "审计记录" in reason and "PermissionError" in reason, reason


def test_a_stat_that_failed_after_the_open_is_not_an_empty_trail(tmp_path: Path) -> None:
    workspace = _plain(tmp_path)
    audit = _write_audit(workspace)

    with _DenyRead(audit, open_denied=False, stat_after_open=True):
        summary = ChangeInspector(workspace).summary()

    reason = summary.get("audit_read_error")
    assert isinstance(reason, str) and reason, summary
    assert "OSError" in reason, reason


def test_the_existence_check_failing_is_a_reason_not_a_crash(tmp_path: Path) -> None:
    """On 3.11 ``Path.is_file`` raises; the check sat outside the try."""
    workspace = _plain(tmp_path)
    audit = _write_audit(workspace)

    with _DenyRead(audit, is_file=True):
        summary = ChangeInspector(workspace).summary()

    reason = summary.get("audit_read_error")
    assert isinstance(reason, str) and reason, summary
    assert "OSError" in reason, reason


def test_a_diff_carries_the_audit_reason(tmp_path: Path) -> None:
    workspace = _plain(tmp_path)
    audit = _write_audit(workspace)

    with _DenyRead(audit):
        diff = ChangeInspector(workspace).diff("notes.md")

    reason = diff.get("audit_read_error")
    assert isinstance(reason, str) and reason, diff
    assert "审计记录" in reason, reason


def test_a_file_no_source_could_see_does_not_diff_to_an_empty_patch(
    tmp_path: Path,
) -> None:
    """The audit was the only witness, and the clean shortcut still fired."""
    workspace = _plain(tmp_path)
    audit = _write_audit(workspace)

    with _DenyRead(audit):
        diff = ChangeInspector(workspace).diff("notes.md")

    assert diff["patch"].strip(), (
        f"审计读不出来时，diff 把可能改过的文件画成了空补丁：{diff}"
    )
    assert "+hello" in diff["patch"], diff["patch"]


def test_the_control_a_readable_audit_still_names_its_writes(tmp_path: Path) -> None:
    workspace = _plain(tmp_path)
    _write_audit(workspace)
    summary = ChangeInspector(workspace).summary()
    assert [item["path"] for item in summary["files"]] == ["notes.md"], summary
    assert summary["total_files"] == 1, summary
    assert summary["audit_window_truncated"] is False, summary
    assert summary.get("audit_read_error") is None, summary


def test_the_control_a_missing_audit_trail_is_not_a_failed_read(tmp_path: Path) -> None:
    workspace = _plain(tmp_path)
    summary = ChangeInspector(workspace).summary()
    assert summary["total_files"] == 0, summary
    assert summary.get("audit_read_error") is None, summary


def test_the_control_a_clean_file_with_a_readable_audit_still_diffs_to_nothing(
    tmp_path: Path,
) -> None:
    """The shortcut is right when the trail was actually read and silent."""
    workspace = _plain(tmp_path)
    _write_audit(workspace)
    diff = ChangeInspector(workspace).diff("readme.txt")
    assert diff.get("audit_read_error") is None, diff
    assert diff["patch"] == "", diff


def test_a_truncation_claim_does_not_survive_a_failed_read(tmp_path: Path) -> None:
    """The window flag belongs to the read that made it."""
    workspace = _plain(tmp_path)
    audit = _write_audit(workspace, records=501)
    inspector = ChangeInspector(workspace)
    first = inspector.summary()
    assert first["audit_window_truncated"] is True, first

    with _DenyRead(audit):
        second = inspector.summary()

    assert second["audit_window_truncated"] is False, (
        f"这次读失败了，却沿用上一次读到的截断说法：{second}"
    )
    assert second.get("audit_read_error"), second


def test_git_still_answers_when_the_audit_is_blind(tmp_path: Path) -> None:
    """git's half of the table is not thrown away with the audit's half."""
    workspace = _repo(tmp_path)
    (workspace / "a.txt").write_text("one\ntwo\n", encoding="utf-8")
    audit = _write_audit(workspace)

    with _DenyRead(audit):
        inspector = ChangeInspector(workspace)
        summary = inspector.summary()
        diff = inspector.diff("a.txt")

    assert [item["path"] for item in summary["files"]] == ["a.txt"], summary
    assert summary.get("audit_read_error"), summary
    assert "+two" in diff["patch"], diff["patch"]
    assert diff.get("audit_read_error"), diff
