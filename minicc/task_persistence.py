"""Coalesced task persistence, independent of agent callbacks and scheduling."""

from __future__ import annotations

import threading
from typing import Any, Callable

from .logging_setup import get_logger

LOG = get_logger("task")


class TaskSnapshotWriter:
    """Keep one dirty reference per task and provide a synchronous final flush.

    References are read at flush time rather than capturing stale running
    snapshots. The write callback owns serialization so it can release task
    locks before disk IO and reject stale snapshots using its serial number.
    """

    def __init__(self, write: Callable[[Any], None], *, interval: float = 0.35) -> None:
        self._write = write
        self._interval = interval
        self._pending: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.last_error: Exception | None = None
        self._thread = threading.Thread(target=self._run, name="task-snapshot-writer", daemon=True)
        self._thread.start()

    def enqueue(self, task: Any, *, retry: bool = False) -> None:
        """Remember ``task`` as dirty.

        ``retry`` keeps the entry even after ``close()`` has set the stop
        flag: a write that failed must still be handed to the final drain,
        and the stop flag used to disable exactly that.
        """
        with self._lock:
            if retry or not self._stop.is_set():
                self._pending[task.task_id] = task

    def flush(self, task: Any) -> None:
        """Write ``task`` now, and keep it pending until the write lands.

        M8-T270: the pending entry used to be dropped *before* the write, so
        a failed write had nothing left to retry from - and the recovery path
        (``enqueue``) was disabled once ``close()`` had set the stop flag.
        A failed terminal write therefore lost the snapshot: the row stayed
        ``running`` and the next start adopted the task as ``interrupted``,
        so the user's result was simply gone.  The entry goes back when the
        write fails, which gives the final drain another chance.
        """
        with self._lock:
            self._pending.pop(task.task_id, None)
        try:
            self._write(task)
        except BaseException:
            self.enqueue(task, retry=True)
            raise
        self.last_error = None

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            with self._lock:
                pending = list(self._pending.values())
                self._pending.clear()
            for task in pending:
                try:
                    self.flush(task)
                except Exception as exc:  # callbacks stay responsive; final writes surface errors
                    self.last_error = exc
                    LOG.warning(
                        "task_snapshot_write_failed task_id=%s source=drain_loop error=%s: %s",
                        getattr(task, "task_id", "?"),
                        type(exc).__name__,
                        str(exc)[:200],
                    )
                    self.enqueue(task, retry=True)

    def close(self) -> list[tuple[str, BaseException]]:
        """Stop the thread, drain what is still dirty, name what never landed.

        M8-T320: the failures used to end up only on ``last_error`` - an attribute
        no production code reads - and a failed attempt left no trace an operator
        could find in the log.  The caller now gets the ids whose terminal snapshot
        is still missing after every retry this drain has.
        """
        self._stop.set()
        self._thread.join(timeout=6)
        with self._lock:
            pending = list(self._pending.values())
            self._pending.clear()
        # M3-T9: one failing flush (e.g. a transient SQLite lock) must not abort
        # the remaining terminal writes, and a failed task is tried once more -
        # the drain is the last chance to land a terminal snapshot.  A task that
        # lands on the second attempt is not reported as lost.
        lost: dict[str, BaseException] = {}
        for task in pending:
            task_id = str(getattr(task, "task_id", "?"))
            for attempt in range(2):
                try:
                    self.flush(task)
                except Exception as exc:  # noqa: BLE001 - surfaced to the caller and the log
                    lost[task_id] = exc
                    LOG.warning(
                        "task_snapshot_write_failed task_id=%s attempt=%d error=%s: %s",
                        task_id,
                        attempt + 1,
                        type(exc).__name__,
                        str(exc)[:200],
                    )
                else:
                    lost.pop(task_id, None)
                    break
        if lost:
            self.last_error = next(iter(lost.values()))
        return list(lost.items())
