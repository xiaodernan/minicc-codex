"""M3-T9: TaskSnapshotWriter.close() must flush every pending terminal task.

The old ``close()`` looped ``for task in pending: self.flush(task)`` with no
guard, so a single failing flush (e.g. a transient SQLite lock) aborted the loop
and silently dropped the remaining terminal snapshots. Each flush is now
independent: a failure is recorded on ``last_error`` and the rest still land.
"""

from __future__ import annotations

from types import SimpleNamespace

from minicc.task_persistence import TaskSnapshotWriter


def test_close_continues_after_first_flush_fails() -> None:
    written: list[str] = []

    def write(task: SimpleNamespace) -> None:
        if task.task_id == "bad":
            raise RuntimeError("transient sqlite lock")
        written.append(task.task_id)

    # A long interval keeps the background thread from flushing before close().
    writer = TaskSnapshotWriter(write, interval=100.0)
    for task_id in ("bad", "good-1", "good-2"):
        writer.enqueue(SimpleNamespace(task_id=task_id))

    writer.close()

    assert "good-1" in written
    assert "good-2" in written
    assert isinstance(writer.last_error, RuntimeError)


def test_close_flushes_all_when_none_fail() -> None:
    written: list[str] = []
    writer = TaskSnapshotWriter(lambda task: written.append(task.task_id), interval=100.0)
    for task_id in ("a", "b", "c"):
        writer.enqueue(SimpleNamespace(task_id=task_id))
    writer.close()
    assert sorted(written) == ["a", "b", "c"]
    assert writer.last_error is None
