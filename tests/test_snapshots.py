"""Task-start snapshot capture and restore (copy-back, not git reset --hard)."""

from __future__ import annotations

import subprocess
from pathlib import Path
import json

import pytest

from minicc.snapshots import SnapshotError, SnapshotJournal, capture, restore, snapshot_dir
from minicc.tools.editor import Editor


def _git(tmp_path: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True, text=True)


def _init_repo(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "minicc@example.test")
    _git(tmp_path, "config", "user.name", "minicc")
    (tmp_path / "tracked.txt").write_text("v1\n", encoding="utf-8")
    _git(tmp_path, "add", "tracked.txt")
    _git(tmp_path, "commit", "-m", "init")


def test_capture_and_restore_dirty_files_only(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "tracked.txt").write_text("v2\n", encoding="utf-8")
    (tmp_path / "unrelated.txt").write_text("keep me\n", encoding="utf-8")
    snapshot = capture(tmp_path, "task-1")
    assert "tracked.txt" in snapshot["files"]
    (tmp_path / "tracked.txt").write_text("v3-should-revert\n", encoding="utf-8")
    (tmp_path / "created-after.txt").write_text("leave this\n", encoding="utf-8")
    outcome = restore(tmp_path, "task-1")
    assert "tracked.txt" in outcome["restored"]
    assert (tmp_path / "tracked.txt").read_text(encoding="utf-8") == "v2\n"
    assert (tmp_path / "unrelated.txt").read_text(encoding="utf-8") == "keep me\n"
    assert (tmp_path / "created-after.txt").read_text(encoding="utf-8") == "leave this\n"


def test_restore_missing_snapshot_errors(tmp_path: Path) -> None:
    with pytest.raises(SnapshotError, match="找不到任务快照"):
        restore(tmp_path, "missing-task")


def test_rejects_unsafe_task_id(tmp_path: Path) -> None:
    with pytest.raises(SnapshotError, match="非法"):
        capture(tmp_path, "../escape")


def test_unicode_spaced_paths_roundtrip(tmp_path):
    _init_repo(tmp_path)
    name = "中文 文件.txt"
    (tmp_path / name).write_text("before", encoding="utf-8")
    result = capture(tmp_path, "task-unicode")
    assert name in result["files"]
    (tmp_path / name).write_text("after", encoding="utf-8")
    restore(tmp_path, "task-unicode")
    assert (tmp_path / name).read_text(encoding="utf-8") == "before"


def test_literal_arrow_is_preserved_by_nul_parser(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from minicc.snapshots import _git_dirty_files
    monkeypatch.setattr("minicc.snapshots.subprocess.run", lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="?? literal -> name.txt\0R  新名.txt\0旧名.txt\0"))
    assert _git_dirty_files(tmp_path) == ["literal -> name.txt", "新名.txt"]


def test_snapshot_manifest_filename_cannot_collide_with_user_file(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "manifest.json").write_text('{"user":true}', encoding="utf-8")
    capture(tmp_path, "manifest-task")
    (tmp_path / "manifest.json").write_text("changed", encoding="utf-8")
    assert "manifest.json" in restore(tmp_path, "manifest-task")["restored"]
    assert json.loads((tmp_path / "manifest.json").read_text()) == {"user": True}


def test_repeated_capture_keeps_original_preimage(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "tracked.txt").write_text("before", encoding="utf-8")
    capture(tmp_path, "resume")
    (tmp_path / "tracked.txt").write_text("after", encoding="utf-8")
    capture(tmp_path, "resume")
    restore(tmp_path, "resume")
    assert (tmp_path / "tracked.txt").read_text() == "before"


def _editor(tmp_path, task="journal"):
    capture(tmp_path, task)
    journal = SnapshotJournal(tmp_path, task)
    return Editor(tmp_path, before_write=journal.before_write, after_write=journal.after_write)


def test_journal_restores_clean_edits_and_removes_only_own_created_files(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "user-dirty.txt").write_text("user before", encoding="utf-8")
    editor = _editor(tmp_path)
    editor.write_file("tracked.txt", "agent change")
    editor.write_file("tracked.txt", "second agent change")
    editor.write_file("new.txt", "created")
    (tmp_path / "user-dirty.txt").write_text("user after", encoding="utf-8")
    (tmp_path / "unrelated-new.txt").write_text("leave", encoding="utf-8")
    result = restore(tmp_path, "journal")
    assert result["restored"] == ["tracked.txt"]
    assert result["removed"] == ["new.txt"]
    assert (tmp_path / "tracked.txt").read_text() == "v1\n"
    assert (tmp_path / "user-dirty.txt").read_text() == "user after"
    assert (tmp_path / "unrelated-new.txt").exists()
    assert not (tmp_path / "new.txt").exists()


def test_journal_preserves_concurrent_edits_and_reports_conflicts(tmp_path):
    _init_repo(tmp_path)
    editor = _editor(tmp_path)
    editor.write_file("tracked.txt", "agent change")
    (tmp_path / "tracked.txt").write_text("user later", encoding="utf-8")
    result = restore(tmp_path, "journal")
    assert result["conflicts"] == ["tracked.txt"]
    assert result["restored"] == []
    assert (tmp_path / "tracked.txt").read_text() == "user later"


def test_journal_handles_deletions_and_moves_without_git(tmp_path):
    (tmp_path / "delete.txt").write_text("restore deleted", encoding="utf-8")
    (tmp_path / "source.txt").write_text("restore moved", encoding="utf-8")
    editor = _editor(tmp_path)
    editor.delete("delete.txt")
    editor.move("source.txt", "destination.txt")
    result = restore(tmp_path, "journal")
    assert set(result["restored"]) == {"delete.txt", "source.txt"}
    assert result["removed"] == ["destination.txt"]
    assert (tmp_path / "delete.txt").read_text() == "restore deleted"
    assert (tmp_path / "source.txt").read_text() == "restore moved"


def test_snapshot_rejects_absolute_manifest_entries(tmp_path):
    _init_repo(tmp_path)
    capture(tmp_path, "tampered")
    manifest = snapshot_dir(tmp_path, "tampered") / "manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["files"] = ["/tracked.txt", "C:/outside.txt", "../escape", ".git/config"]
    manifest.write_text(json.dumps(data), encoding="utf-8")
    assert len(restore(tmp_path, "tampered")["skipped"]) == 4


def test_more_than_400_dirty_files_are_not_silently_dropped(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from minicc.snapshots import _git_dirty_files
    records = "".join(f"?? file-{index}.txt\0" for index in range(450))
    monkeypatch.setattr("minicc.snapshots.subprocess.run", lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=records))
    assert len(_git_dirty_files(tmp_path)) == 450


def test_restore_rejects_active_workspace(tmp_path):
    import threading
    from types import SimpleNamespace
    from minicc.web import AgentService
    service = object.__new__(AgentService)
    service.workspace = tmp_path
    service.tasks = SimpleNamespace(lock=threading.RLock(), get=lambda task: {"workspace_path": str(tmp_path)}, has_active=lambda workspace: True)
    with pytest.raises(SnapshotError, match="仍有任务运行"):
        service.restore_task_snapshot("running")


def test_corrupted_snapshot_bytes_are_not_restored(tmp_path):
    _init_repo(tmp_path)
    editor = _editor(tmp_path)
    editor.write_file("tracked.txt", "agent result")
    (snapshot_dir(tmp_path, "journal") / "files" / "tracked.txt").write_text("corrupted", encoding="utf-8")
    result = restore(tmp_path, "journal")
    assert result["skipped"] == ["tracked.txt"]
    assert (tmp_path / "tracked.txt").read_text() == "agent result"


def test_capture_limits_are_explicit_and_refuse_unprotected_write(tmp_path, monkeypatch):
    from minicc.snapshots import SnapshotJournal
    from minicc.tools.editor import Editor
    _init_repo(tmp_path)
    (tmp_path / "tracked.txt").write_text("large dirty data")
    monkeypatch.setattr("minicc.snapshots.MAX_SNAPSHOT_FILE_BYTES", 4)
    summary = capture(tmp_path, "limited")
    assert summary["captured"] is False and summary["partial"] is True
    assert "tracked.txt" in summary["skipped_reasons"]
    journal = SnapshotJournal(tmp_path, "limited")
    editor = Editor(tmp_path, before_write=journal.before_write, after_write=journal.after_write)
    with pytest.raises(SnapshotError, match="拒绝编辑"):
        editor.write_file("tracked.txt", "overwrite")
    assert (tmp_path / "tracked.txt").read_text() == "large dirty data"


def test_dirty_file_changed_after_capture_is_not_overwritten(tmp_path):
    from minicc.snapshots import SnapshotJournal
    from minicc.tools.editor import Editor
    _init_repo(tmp_path)
    (tmp_path / "tracked.txt").write_text("user dirty")
    capture(tmp_path, "external")
    (tmp_path / "tracked.txt").write_text("later user edit")
    journal = SnapshotJournal(tmp_path, "external")
    editor = Editor(tmp_path, before_write=journal.before_write, after_write=journal.after_write)
    with pytest.raises(SnapshotError, match="外部修改"):
        editor.write_file("tracked.txt", "agent")
    assert (tmp_path / "tracked.txt").read_text() == "later user edit"


def test_external_edit_between_agent_writes_is_not_overwritten(tmp_path):
    _init_repo(tmp_path)
    editor = _editor(tmp_path)
    editor.write_file("tracked.txt", "agent first")
    (tmp_path / "tracked.txt").write_text("user after first")
    with pytest.raises(SnapshotError, match="发生变化"):
        editor.write_file("tracked.txt", "agent second")
    assert (tmp_path / "tracked.txt").read_text() == "user after first"
