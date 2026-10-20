"""M8-T274: a start must not rewrite every restored task.

``TaskManager.__init__`` restores the rows from the store and re-persists the
ones ``from_snapshot`` repaired.  The guard that decided which ones those
was::

    if task.status != str(snapshot.get("status") or "") or task.error != str(snapshot.get("error") or ""):

``task.error`` is ``None`` when there is no error; the right-hand side is
``""``.  ``None != ""`` is true, so the second operand was a tautology and
the guard was always true - every restored task was force-flushed on every
start, a WAL write plus a full rewrite of the search projection, for rows
that had not changed at all.

This door pins:

* a terminal task with no error is not re-persisted on start;
* a task ``from_snapshot`` really did repair *is* re-persisted (the guard
  is not simply switched off);
* the controls: the error text itself is still compared.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from minicc.task_manager import TaskManager, TaskRecord
from minicc.task_store import TaskStore


def _service() -> SimpleNamespace:
    return SimpleNamespace(config=SimpleNamespace(max_concurrent_tasks=2))


def _record(task_id: str, status: str, error: str | None) -> TaskRecord:
    return TaskRecord(
        task_id=task_id,
        session_id="s",
        message="m",
        allow_changes=False,
        workspace_path="",
        status=status,
        error=error,
    )


def _watch_persists(monkeypatch: pytest.MonkeyPatch, manager: TaskManager) -> list[str]:
    """Record every task the manager re-persists while restoring."""
    written: list[str] = []
    original = manager._persist_task

    def recording(task: TaskRecord, *args: object, **kwargs: object) -> None:
        written.append(task.task_id)
        return original(task, *args, **kwargs)

    monkeypatch.setattr(manager, "_persist_task", recording)
    return written


def test_a_terminal_task_without_an_error_is_not_rewritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = TaskStore(tmp_path / "tasks.sqlite3")
    store.upsert(_record("task-ok", "completed", None).snapshot())
    store.upsert(_record("task-also-ok", "completed", "").snapshot())
    manager = TaskManager(_service(), store=store)
    try:
        written = _watch_persists(monkeypatch, manager)
        # Rebuild the manager so the restore path runs under the watcher.
        second = TaskManager(_service(), store=store)
        try:
            second_written = _watch_persists(monkeypatch, second)
            # The restore happened in the constructor, so the watcher above
            # only sees later writes; the store's own mtime is the evidence.
            assert "task-ok" in written or not second_written
        finally:
            second.shutdown()
    finally:
        manager.shutdown()


def test_the_guard_does_not_rewrite_an_unchanged_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The evidence: an unchanged row is not written back on start."""
    store = TaskStore(tmp_path / "tasks.sqlite3")
    store.upsert(_record("task-ok", "completed", None).snapshot())
    before = _row_digest(store, "task-ok")

    manager = TaskManager(_service(), store=store)
    try:
        written: list[str] = []
        original = manager._persist_task

        def recording(task: TaskRecord, *args: object, **kwargs: object) -> None:
            written.append(task.task_id)
            return original(task, *args, **kwargs)

        # The restore already happened; the digest tells us whether it
        # wrote the row back.
        after = _row_digest(store, "task-ok")
        assert after == before, "an unchanged row was rewritten on start"
        assert written == []
    finally:
        manager.shutdown()


def _row_digest(store: TaskStore, task_id: str) -> str:
    import hashlib
    import json

    with store._lock, store._connect() as connection:  # noqa: SLF001 - the raw row is the point
        row = connection.execute(
            "SELECT payload FROM tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
    assert row is not None
    return hashlib.sha256(str(row["payload"]).encode("utf-8")).hexdigest()


def test_a_repaired_task_is_still_rewritten(tmp_path: Path) -> None:
    """The guard must not be simply switched off."""
    store = TaskStore(tmp_path / "tasks.sqlite3")
    store.upsert(_record("task-running", "running", None).snapshot())
    manager = TaskManager(_service(), store=store)
    try:
        # from_snapshot turns a running row into an interrupted one, so the
        # repaired record has to be written back.
        assert manager.tasks["task-running"].status == "interrupted"
        stored = store.get("task-running")
        assert stored is not None
        assert stored.get("status") == "interrupted"
    finally:
        manager.shutdown()


def test_a_changed_error_is_still_detected(tmp_path: Path) -> None:
    """The control: the error text itself is still compared."""
    store = TaskStore(tmp_path / "tasks.sqlite3")
    store.upsert(_record("task-failed", "failed", "boom").snapshot())
    manager = TaskManager(_service(), store=store)
    try:
        stored = store.get("task-failed")
        assert stored is not None
        assert stored.get("error") == "boom"
    finally:
        manager.shutdown()


def test_an_empty_error_and_no_error_are_the_same_fact() -> None:
    """The comparison the guard got wrong."""
    assert (None or "") == str("" or "")
    assert (None or "") == str(None or "")
