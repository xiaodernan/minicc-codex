"""Event durability contract — the boundary §3.2 must preserve.

PROJECT_REVIEW §3.2 (2026-09-18) is about "流事件持久化": stop writing a full
snapshot on every delta, publish small events, batch-merge in the background,
force-flush terminal transitions. Before that refactor, this file pins what
"event durability" actually means in the current code, so the refactor cannot
silently weaken it:

  * The durable event record is the per-task snapshot's ``events`` field
    (``task_manager.TaskRecord.snapshot()`` embeds ``list(self.events)`` at
    ``minicc/task_manager.py:805``). Surviving a restart == surviving in the
    snapshot.
  * ``EventLog`` (``minicc/agent/protocol.py:121``) is an in-memory, bounded
    replay buffer for SSE clients. It has NO disk backing — a fresh instance
    starts empty. So event durability is carried by the snapshot, not the log.
  * The in-memory list is bounded by ``limit``; overflow drops the oldest. This
    bounds the size of every persisted snapshot (the cost §3.2 wants to cut).
  * A terminal force-flush (``writer.flush``) must carry the full event history
    the moment it returns — the "终态强制落盘" guarantee applied to events.

These are current invariants; they pass today and fence the §3.2 work.
"""

from __future__ import annotations

from types import SimpleNamespace

from minicc.agent.protocol import EventLog
from minicc.task_persistence import TaskSnapshotWriter
from minicc.task_store import TaskStore


def _writer(store: TaskStore, interval: float = 100.0) -> TaskSnapshotWriter:
    def write(task: object) -> None:
        store.upsert(task.snapshot)  # type: ignore[attr-defined]

    return TaskSnapshotWriter(write, interval=interval)


def _snapshot_with_events(task_id: str, events: list[dict], **fields: object) -> dict:
    return {
        "task_id": task_id,
        "status": "running",
        "events": events,
        "events_truncated": 0,
        **fields,
    }


# --- The snapshot is the sole durable event record ---------------------------


def test_event_history_persists_in_snapshot_and_survives_reopen(tmp_path) -> None:
    """Events ride the snapshot: what is upserted is what is recovered."""
    path = tmp_path / "tasks.sqlite3"
    store = TaskStore(path)
    events = [
        {"event_id": "e1", "name": "read_file", "path": "a.py"},
        {"event_id": "e2", "name": "edit_file", "path": "b.py"},
        {"event_id": "e3", "name": "run_tests", "path": "b.py"},
    ]
    assert store.upsert(_snapshot_with_events("t", events))
    reopened = TaskStore(path)
    loaded = reopened.get("t")
    assert loaded is not None
    assert loaded["events"] == events


def test_event_truncation_marker_is_persisted(tmp_path) -> None:
    """A recovered task must know its history was truncated (honest UI).

    The snapshot carries ``events_truncated``; the refactor must keep it in the
    durable record rather than recomputing from a partial in-memory log.
    """
    path = tmp_path / "tasks.sqlite3"
    store = TaskStore(path)
    assert store.upsert(_snapshot_with_events("t", [{"event_id": "e1"}], events_truncated=7))
    reopened = TaskStore(path)
    assert reopened.get("t")["events_truncated"] == 7


# --- EventLog is in-memory only; durability comes from the snapshot ---------


def test_fresh_event_log_has_no_disk_backing(tmp_path) -> None:
    """A brand-new EventLog starts empty: events are not persisted to disk.

    This is the architectural boundary the §3.2 refactor must respect — replay
    history is rebuilt from the snapshot, never read back from a log file.
    """
    log = EventLog(task_id="t", limit=1024)
    buffered, gap = log.read(after=0, timeout=0)
    assert buffered == []
    assert log.oldest_sequence == 1  # no events have ever existed


def test_live_event_log_buffers_but_close_does_not_persist(tmp_path) -> None:
    """close() only flips a flag; the buffer stays in the instance, and a
    separate instance still starts empty — durability is the snapshot's job."""
    live = EventLog(task_id="t", limit=1024)
    live.append("read_file", {"path": "a.py"}, event_id="e1")
    live.close()
    buffered, _ = live.read(after=0)
    assert len(buffered) == 1  # still in memory until the object is gone
    # A distinct instance (the shape of a post-restart replay log) has nothing.
    assert EventLog(task_id="t", limit=1024).read(after=0, timeout=0)[0] == []


def test_event_log_is_bounded_by_limit(tmp_path) -> None:
    """Overflow drops the oldest event; this bounds every snapshot's size.

    The §3.2 batch-merge work must not let the in-memory (and thus persisted)
    event list grow without bound. ``EventLog`` floors the limit at 32 so a
    misconfigured tiny limit cannot OOM the process.
    """
    assert EventLog(task_id="t", limit=2).limit == 32  # floor enforced
    log = EventLog(task_id="t", limit=32)
    for index in range(40):
        log.append("step", {"i": index}, event_id=f"e{index}")
    buffered, _ = log.read(after=0)
    assert len(buffered) == 32
    assert [e.event_id for e in buffered] == [f"e{i}" for i in range(8, 40)]


# --- Terminal force-flush carries event history immediately ------------------


def test_terminal_force_flush_carries_event_history(tmp_path) -> None:
    """The §3.2 "终态强制落盘" guarantee, applied to events: once a terminal
    snapshot is force-flushed, its event history is durable without close()."""
    path = tmp_path / "tasks.sqlite3"
    store = TaskStore(path)
    writer = _writer(store)
    events = [{"event_id": f"e{i}", "name": "tool", "path": f"f{i}.py"} for i in range(4)]
    writer.flush(
        SimpleNamespace(
            task_id="a",
            snapshot=_snapshot_with_events("a", events, status="completed"),
        )
    )
    reopened = TaskStore(path)
    loaded = reopened.get("a")
    assert loaded is not None
    assert loaded["status"] == "completed"
    assert loaded["events"] == events
