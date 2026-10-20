"""M8-T270: a failed terminal write must not lose the snapshot.

``TaskSnapshotWriter.flush`` dropped the pending entry *before* the write, so
a failed write had nothing left to retry from.  The recovery path
(``enqueue``) was disabled once ``close()`` had set the stop flag, and the
force path (a synchronous final flush) had no recovery at all.  So a failed
terminal write lost the snapshot: the row stayed ``running`` and the next
start adopted the task as ``interrupted`` - the user's result was gone, and
nothing said so.

The entry now goes back when the write fails, and the final drain tries a
failed task once more.

This door pins:

* a failed flush leaves the task pending, so the drain can retry it;
* the drain really does retry, and a transient failure lands the snapshot;
* the controls: a successful write clears the entry, and a permanently
  failing write is still reported (``last_error``) rather than swallowed.
"""

from __future__ import annotations

import threading
from typing import Any

import pytest

from minicc.task_persistence import TaskSnapshotWriter


class _Task:
    def __init__(self, task_id: str) -> None:
        self.task_id = task_id


def test_a_failed_flush_keeps_the_task_pending() -> None:
    """The entry must survive the failure, or there is nothing to retry."""
    written: list[str] = []

    def write(task: Any) -> None:
        written.append(task.task_id)
        raise RuntimeError("database is locked")

    writer = TaskSnapshotWriter(write, interval=3600.0)
    try:
        task = _Task("t1")
        writer.enqueue(task)
        with pytest.raises(RuntimeError):
            writer.flush(task)
        assert writer._pending, "the failed write took the task out of the queue"
    finally:
        writer.close()


def test_the_drain_retries_a_transient_failure() -> None:
    """A lock that clears is the common case; the snapshot must land."""
    attempts: list[str] = []

    def write(task: Any) -> None:
        attempts.append(task.task_id)
        if len(attempts) == 1:
            raise RuntimeError("database is locked")

    writer = TaskSnapshotWriter(write, interval=3600.0)
    try:
        task = _Task("t1")
        writer.enqueue(task)
        writer.close()
        assert attempts.count("t1") >= 2, "the failed write was never retried"
    finally:
        writer.close()


def test_a_permanently_failing_write_is_reported_not_swallowed() -> None:
    attempts: list[str] = []

    def write(task: Any) -> None:
        attempts.append(task.task_id)
        raise RuntimeError("disk is full")

    writer = TaskSnapshotWriter(write, interval=3600.0)
    try:
        task = _Task("t1")
        writer.enqueue(task)
        writer.close()
        assert writer.last_error is not None, "the failure was not reported"
        assert isinstance(writer.last_error, RuntimeError)
        assert attempts, "the write was never even attempted"
    finally:
        writer.close()


def test_a_successful_write_clears_the_entry() -> None:
    """The control: a healthy write must not leave work queued forever."""
    written: list[str] = []

    def write(task: Any) -> None:
        written.append(task.task_id)

    writer = TaskSnapshotWriter(write, interval=3600.0)
    try:
        task = _Task("t1")
        writer.enqueue(task)
        writer.flush(task)
        assert not writer._pending
        assert written == ["t1"]
    finally:
        writer.close()


def test_a_retry_survives_the_stop_flag() -> None:
    """``close()`` sets the stop flag first; a retry must still be allowed."""
    attempts: list[str] = []

    def write(task: Any) -> None:
        attempts.append(task.task_id)
        raise RuntimeError("database is locked")

    writer = TaskSnapshotWriter(write, interval=3600.0)
    writer.close()  # the stop flag is set here
    task = _Task("t1")
    writer.enqueue(task, retry=True)
    assert writer._pending, "a retry was refused after close()"
    with pytest.raises(RuntimeError):
        writer.flush(task)
    assert writer._pending, "the failed retry was dropped from the queue"
    assert attempts == ["t1"]


def test_the_background_loop_keeps_a_failed_task() -> None:
    """The periodic writer must not drop a task whose write failed."""
    attempts: list[str] = []
    fail = threading.Event()
    fail.set()

    def write(task: Any) -> None:
        attempts.append(task.task_id)
        if fail.is_set():
            raise RuntimeError("database is locked")

    writer = TaskSnapshotWriter(write, interval=0.02)
    try:
        task = _Task("t1")
        writer.enqueue(task)
        deadline = 0
        while not writer._pending and deadline < 200:
            deadline += 1
            threading.Event().wait(0.01)
        assert writer._pending, "the background loop dropped the failed task"
    finally:
        fail.clear()
        writer.close()
