"""M8-T320: one task's failed terminal write must not abort the shutdown of the others.

``TaskManager.shutdown()`` force-persists every queued/running task on its way out.
One of those calls is ``TaskSnapshotWriter.flush``, which re-raises when the write
fails (a contract M8-T270 pinned deliberately, so a lost snapshot stays visible to
the caller).  Nothing caught it here, so the very first task with a bad disk - a
transient SQLite lock is the ordinary case - ended the whole drain:

* the tasks after it were never cancelled and their terminal rows never landed;
* the coalescing thread and the thread pool were never shut down;
* the MCP child cleanup that ``AgentService.shutdown()`` runs after
  ``tasks.shutdown()`` was skipped as collateral damage.

And the failure itself left no trace: it was parked on ``writer.last_error``, an
attribute no production code reads.

This door pins the other half - the drain finishes, and what could not land is
named, per task id, in the log.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

from minicc.task_manager import TaskManager, TaskRecord
from minicc.task_persistence import TaskSnapshotWriter
from minicc.task_store import TaskStore

LOGGER_NAME = "minicc.task"
BROKEN = "task-broken"
HEALTHY = "task-healthy"


def _service() -> SimpleNamespace:
    return SimpleNamespace(config=SimpleNamespace(max_concurrent_tasks=2))


def _record(task_id: str, root: Path) -> TaskRecord:
    return TaskRecord(
        task_id=task_id,
        session_id=f"session-{task_id}",
        message="m",
        allow_changes=False,
        workspace_path=str(root),
        status="running",
    )


class _Harness:
    """A manager holding one task whose write fails and one that succeeds.

    The failure is injected on ``writer._write`` - the callback the writer was
    handed at construction.  Replacing ``manager._write_task_snapshot`` instead
    changes nothing, because the writer already bound the original method.
    """

    def __init__(self, tmp_path: Path) -> None:
        self.store = TaskStore(tmp_path / "tasks.sqlite3")
        self.manager = TaskManager(_service(), store=self.store)
        writer = self.manager._snapshot_writer
        assert writer is not None, "the manager was built without a store, so nothing is persisted"
        self.writer = writer
        self.writer._interval = 3600.0  # the background drain must not race this test
        self.attempts: list[str] = []
        original = self.writer._write

        def write(task: Any) -> None:
            self.attempts.append(task.task_id)
            if task.task_id == BROKEN:
                raise RuntimeError("disk quota exceeded")
            original(task)

        self.writer._write = write  # type: ignore[assignment]
        self.broken = _record(BROKEN, tmp_path)
        self.healthy = _record(HEALTHY, tmp_path)
        # Insertion order is the point: the broken task is drained first.
        self.manager.tasks[BROKEN] = self.broken
        self.manager.tasks[HEALTHY] = self.healthy
        self.executor_calls: list[tuple[bool, bool]] = []
        real_executor_shutdown = self.manager.executor.shutdown

        def executor_shutdown(*, wait: bool = True, cancel_futures: bool = False) -> None:
            self.executor_calls.append((wait, cancel_futures))
            real_executor_shutdown(wait=wait, cancel_futures=cancel_futures)

        self.manager.executor.shutdown = executor_shutdown  # type: ignore[method-assign]
        self.retired: list[str] = []
        self.manager._retire_worker_process = self.retired.append  # type: ignore[method-assign]
        self.manager._worker_processes["task-worker"] = object()

    def shutdown(self) -> BaseException | None:
        """Run the real shutdown, returning whatever escaped instead of raising."""
        try:
            self.manager.shutdown()
        except BaseException as exc:  # noqa: BLE001 - the question is whether this happens at all
            return exc
        return None


@contextmanager
def _task_log() -> Iterator[list[logging.LogRecord]]:
    """Capture the family's own logger; ``minicc`` does not propagate to the root.

    A handler on the root logger sees nothing here, and a silent capture reads
    exactly like a silent product - so the handler goes on the logger that owns
    the records.
    """
    logger = logging.getLogger(LOGGER_NAME)
    records: list[logging.LogRecord] = []

    class _Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Collect(level=logging.DEBUG)
    previous_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        yield records
    finally:
        logger.setLevel(previous_level)
        logger.removeHandler(handler)


def _lost_lines(records: list[logging.LogRecord]) -> list[str]:
    return [r.getMessage() for r in records if "task_result_lost" in r.getMessage()]


def test_one_task_s_write_failure_does_not_abort_the_shutdown_drain(tmp_path: Path) -> None:
    """The neighbour still gets its turn at the disk."""
    harness = _Harness(tmp_path)
    raised = harness.shutdown()
    assert raised is None, f"shutdown aborted on one task's write error: {type(raised).__name__}: {raised}"
    assert HEALTHY in harness.attempts, (
        f"the drain stopped at {BROKEN!r}; {HEALTHY!r} was never written (attempts={harness.attempts})"
    )


def test_a_healthy_neighbour_is_still_cancelled_when_a_sibling_write_fails(tmp_path: Path) -> None:
    """The cancel comes before the write, so the abort used to leave it unclaimed."""
    harness = _Harness(tmp_path)
    harness.shutdown()
    assert harness.healthy.status == "cancelled", (
        f"{HEALTHY!r} ended shutdown as {harness.healthy.status!r}; a task nobody cancelled "
        "keeps reporting itself as running"
    )
    assert harness.broken.status == "cancelled", (
        f"the task that failed its write ended as {harness.broken.status!r} - the cancel is not the part that broke"
    )


def test_a_healthy_neighbour_s_terminal_row_still_lands_when_a_sibling_write_fails(
    tmp_path: Path,
) -> None:
    """The row is what the next start reads; a missing one loses the task."""
    harness = _Harness(tmp_path)
    harness.shutdown()
    stored = harness.store.get(HEALTHY)
    assert stored is not None, f"{HEALTHY!r} never reached the store, so its result is gone"
    assert stored.get("status") == "cancelled", f"stored row says {stored.get('status')!r}"


def test_the_coalescing_thread_stops_when_a_terminal_write_fails(tmp_path: Path) -> None:
    harness = _Harness(tmp_path)
    assert harness.writer._thread.is_alive(), "the writer thread never started, so this leg proves nothing"
    harness.shutdown()
    assert not harness.writer._thread.is_alive(), "the coalescing thread outlived a shutdown that threw"
    assert harness.writer._stop.is_set(), "the stop flag was never set"


def test_the_thread_pool_still_shuts_down_when_a_terminal_write_fails(tmp_path: Path) -> None:
    harness = _Harness(tmp_path)
    harness.shutdown()
    assert harness.executor_calls, "executor.shutdown() was never reached"
    assert harness.manager.executor._shutdown is True, "the thread pool outlived the manager"


def test_a_failed_terminal_write_is_named_in_the_log(tmp_path: Path) -> None:
    """``last_error`` had no reader; the operator's only channel is the log."""
    harness = _Harness(tmp_path)
    with _task_log() as records:
        harness.shutdown()
    named = [r.getMessage() for r in records if BROKEN in r.getMessage()]
    assert named, f"nothing in {LOGGER_NAME} named the failed write; captured {len(records)} records"
    lost = _lost_lines(records)
    assert any(BROKEN in line for line in lost), (
        f"no task_result_lost line named {BROKEN!r}; lost lines={lost!r}"
    )
    assert not any(HEALTHY in line for line in lost), (
        f"the healthy task was reported as lost too: {lost!r}"
    )


def test_close_names_the_tasks_it_could_not_land_and_only_those() -> None:
    """The report is per task id, not one flag for the whole batch."""
    attempts: list[str] = []

    def write(task: Any) -> None:
        attempts.append(task.task_id)
        if task.task_id == BROKEN:
            raise RuntimeError("disk is full")

    writer = TaskSnapshotWriter(write, interval=3600.0)
    broken, healthy = SimpleNamespace(task_id=BROKEN), SimpleNamespace(task_id=HEALTHY)
    writer.enqueue(broken)
    writer.enqueue(healthy)
    lost = writer.close()
    assert isinstance(lost, list), f"close() returned {lost!r}, not the list of tasks it could not land"
    assert [task_id for task_id, _ in lost] == [BROKEN], f"close() reported {lost!r}"
    assert isinstance(lost[0][1], RuntimeError), "the report must carry the error that refused the write"
    assert HEALTHY in attempts, f"the healthy write never ran: {attempts}"
    # The task that **landed** must not still be queued.  The one that did
    # *not* land is queued on purpose - ``flush`` re-enqueues it so a later
    # drain can try again (M3-T9) - so the check is about the landed task,
    # not about the queue being empty.
    assert all(task_id != HEALTHY for task_id in writer._pending), (
        "a landed task stayed queued"
    )


def test_a_transient_failure_that_lands_on_retry_is_not_reported_as_lost() -> None:
    """A lock that clears is the common case - it must not be called a loss."""
    attempts: list[str] = []

    def write(task: Any) -> None:
        attempts.append(task.task_id)
        if len(attempts) == 1:
            raise RuntimeError("database is locked")

    writer = TaskSnapshotWriter(write, interval=3600.0)
    task = SimpleNamespace(task_id="t1")
    writer.enqueue(task)
    lost = writer.close()
    assert isinstance(lost, list), f"close() returned {lost!r}, not an empty list of losses"
    assert lost == [], f"a snapshot that landed on the retry was reported lost: {lost!r}"
    assert attempts == ["t1", "t1"], f"expected one failed attempt and one landing, got {attempts}"


def test_the_failure_does_not_escape_the_manager_s_shutdown(tmp_path: Path) -> None:
    """Everything scheduled after the writes still runs.

    ``AgentService.shutdown()`` closes the MCP manager right after this, so an
    escaping exception strands those children too; inside the manager, the
    worker-process reaper is the call that must still be reached.
    """
    harness = _Harness(tmp_path)
    raised = harness.shutdown()
    assert raised is None, f"the failure escaped shutdown: {type(raised).__name__}: {raised}"
    assert harness.retired == ["task-worker"], (
        f"the worker reaper after the write phase was skipped: {harness.retired!r}"
    )
