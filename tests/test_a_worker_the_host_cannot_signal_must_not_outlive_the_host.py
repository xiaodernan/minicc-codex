"""M8-T271: a worker the host cannot signal must not outlive the host.

Two windows in the detached-worker path could leave a child running after
the host had already given up on the task:

* ``_monitor_worker`` wrote the cancel flag without guarding the write.  A
  read-only workspace, a full disk, or a ``.minicc/cancel`` directory that
  could not be created turned a cancellation into an ``OSError`` - and the
  monitor's crash marked the task cancelled while the worker kept running
  and spending tokens against a lease the host considered finished.
* the spawn window released the lease without stopping the child.  Since the
  lease was free again, the worker re-claimed it and two writers drove the
  same task id; the handle was never reaped either.

This door pins:

* an unwritable cancel flag does not crash the monitor, and the worker it
  could not signal is stopped directly;
* the control: a writable cancel flag still delivers the signal the usual
  way (no kill);
* a failure after the spawn stops the child and reaps its handle.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from minicc.task_manager import TaskManager, TaskRecord
from minicc.task_store import TaskStore


def _record(tmp_path: Path) -> TaskRecord:
    return TaskRecord(
        task_id="t-monitor",
        session_id="s",
        message="m",
        allow_changes=False,
        workspace_path=str(tmp_path),
    )


class _FakeProcess:
    """A child that is alive until something stops it."""

    def __init__(self) -> None:
        self.terminated = False
        self.killed = False
        self.returncode: int | None = None

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -15

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode if self.returncode is not None else 0

    def stdin(self) -> Any:  # pragma: no cover - not used here
        return None


def _manager(tmp_path: Path, store: TaskStore) -> TaskManager:
    service = SimpleNamespace(config=SimpleNamespace(max_concurrent_tasks=2))
    return TaskManager(service, store=store)


def test_an_unwritable_cancel_flag_does_not_crash_the_monitor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The monitor must survive; the worker it cannot signal must be stopped."""
    store = TaskStore(tmp_path / "tasks.sqlite3")
    manager = _manager(tmp_path, store)
    task = _record(tmp_path)
    task.cancel_event.set()
    process = _FakeProcess()

    def boom(*args: object, **kwargs: object) -> None:
        raise OSError("read-only file system")

    # Both the mkdir and the write fail, as they would on a read-only
    # workspace.
    monkeypatch.setattr(Path, "mkdir", boom)

    # The monitor loops until the task reaches a terminal state; make the
    # store report one so the loop ends.
    monkeypatch.setattr(store, "get", lambda task_id: {"status": "cancelled", "events": []})

    result = manager._monitor_worker(task, store, process)

    assert process.terminated, "the worker was not stopped after the flag failed"
    assert isinstance(result, dict)


def test_a_writable_cancel_flag_delivers_the_signal_without_killing(
    tmp_path: Path,
) -> None:
    """The control: the ordinary path is untouched."""
    store = TaskStore(tmp_path / "tasks.sqlite3")
    manager = _manager(tmp_path, store)
    task = _record(tmp_path)
    task.cancel_event.set()
    process = _FakeProcess()

    monkey_flag = tmp_path / ".minicc" / "cancel" / f"{task.task_id}.flag"

    def fake_get(task_id: str) -> dict[str, Any]:
        # The flag exists by the time the store is consulted, so the monitor
        # can finish its tick.
        assert monkey_flag.is_file(), "the cancel flag was never written"
        return {"status": "cancelled", "events": []}

    store.get = fake_get  # type: ignore[method-assign]
    manager._monitor_worker(task, store, process)

    assert monkey_flag.is_file(), "the cancel flag was not written"
    assert not process.terminated, "the worker was killed although the flag landed"


def test_a_failure_after_the_spawn_stops_the_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The spawn window must not leave the child running."""
    store = TaskStore(tmp_path / "tasks.sqlite3")
    manager = _manager(tmp_path, store)
    task = _record(tmp_path)
    task.workspace_path = str(tmp_path)

    spawned: list[_FakeProcess] = []

    class _Stdin:
        def write(self, data: bytes) -> int:
            raise UnicodeEncodeError("utf-8", data, 0, 1, "surrogates not allowed")

        def close(self) -> None:
            return None

    class _Popen:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.pid = 4242
            self.stdin = _Stdin()
            self.returncode = None
            self.terminated = False
            self.killed = False
            spawned.append(self)  # type: ignore[arg-type]

        def poll(self) -> int | None:
            return self.returncode

        def terminate(self) -> None:
            self.terminated = True
            self.returncode = -15

        def kill(self) -> None:
            self.killed = True
            self.returncode = -9

        def wait(self, timeout: float | None = None) -> int:
            return self.returncode or 0

    monkeypatch.setattr("subprocess.Popen", _Popen)

    class _UnencodablePayload:
        """Truthy, but its bytes cannot be produced."""

        def __bool__(self) -> bool:
            return True

        def encode(self, *args: object, **kwargs: object) -> bytes:
            raise UnicodeEncodeError("utf-8", "payload", 0, 1, "surrogates not allowed")

    # A config the host cannot encode is the failure that lands in this
    # window: the child is already spawned when the payload is written.
    monkeypatch.setattr(manager, "_config_payload", lambda: _UnencodablePayload())

    with pytest.raises(Exception):
        manager._run_in_worker_process(task)

    assert spawned, "no child was spawned"
    assert spawned[0].terminated or spawned[0].killed, (
        "the spawned child was left running"
    )
