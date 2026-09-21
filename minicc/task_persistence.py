"""Coalesced task persistence, independent of agent callbacks and scheduling."""

from __future__ import annotations

import threading
from typing import Any, Callable


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

    def enqueue(self, task: Any) -> None:
        with self._lock:
            if not self._stop.is_set():
                self._pending[task.task_id] = task

    def flush(self, task: Any) -> None:
        with self._lock:
            self._pending.pop(task.task_id, None)
        self._write(task)
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
                    self.enqueue(task)

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=6)
        with self._lock:
            pending = list(self._pending.values())
            self._pending.clear()
        # M3-T9: one failing flush (e.g. a transient SQLite lock) must not abort
        # the remaining terminal writes; record the error and keep going. flush()
        # clears last_error on success, so retain the first failure locally.
        first_error: Exception | None = None
        for task in pending:
            try:
                self.flush(task)
            except Exception as exc:  # noqa: BLE001 - surfaced via last_error
                if first_error is None:
                    first_error = exc
        if first_error is not None:
            self.last_error = first_error
