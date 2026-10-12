"""Durability contract for task persistence — the guarantees §3.2 must keep.

PROJECT_REVIEW §3.2 (2026-09-18) asks to stop writing a full snapshot on every
stream delta and instead publish small events, batch-merge them in the
background, force-flush terminal / important transitions, and keep SQLite on a
clean connection lifecycle + WAL. That is a real refactor of the write path.

Before that refactor lands, this file pins the *observable durability contract*
the new writer must not regress:

  * a force-flushed (terminal) snapshot is durably committed the moment
    ``flush()`` returns — not lost if the process dies right after;
  * a coalesced (background-merged) snapshot is durable after ``close()``;
  * SQLite is in WAL (concurrent readers/writers, crash-safe);
  * leases survive a store reopen (same file, new process);
  * malformed rows never break ``load``/``get``;
  * what lands on disk is redacted, yet identity keys stay recoverable;
  * an evicted worker (expired/replaced lease) cannot clobber its successor.

These are *current* invariants, so they pass today and become the regression
fence for the §3.2 batch-merge work.
"""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace

from minicc.task_persistence import TaskSnapshotWriter
from minicc.task_store import TaskStore


def _snapshot(task_id: str, **fields: object) -> dict:
    return {"task_id": task_id, "status": "running", **fields}


def _writer(store: TaskStore, interval: float = 100.0) -> TaskSnapshotWriter:
    """Mirror production: the writer hands a task object to ``write``, and the
    real callback serializes ``task.snapshot()`` before ``store.upsert``."""

    def write(task: object) -> None:
        store.upsert(task.snapshot)  # type: ignore[attr-defined]

    return TaskSnapshotWriter(write, interval=interval)


# --- Force-flush durability (the "终态强制落盘" guarantee) -------------------


def test_flush_is_durable_before_close(tmp_path) -> None:
    """A synchronous flush() must commit before the writer is closed.

    The manager routes terminal/important transitions through
    ``_persist_task(force=True)`` -> ``writer.flush(task)``. If flush only
    queued, a crash immediately after completion would drop the result.
    """
    path = tmp_path / "tasks.sqlite3"
    store = TaskStore(path)
    writer = _writer(store)
    writer.flush(SimpleNamespace(task_id="a", snapshot=_snapshot("a", status="completed")))
    # No close() — simulate a process that dies right after the flush returns.
    reopened = TaskStore(path)
    assert reopened.get("a") is not None
    assert reopened.get("a")["status"] == "completed"


def test_upsert_is_durable_across_store_reopen(tmp_path) -> None:
    """A direct upsert survives a full store reopen on the same file."""
    path = tmp_path / "tasks.sqlite3"
    first = TaskStore(path)
    assert first.upsert(_snapshot("t1", prompt="hello", result={"answer": "world"}))
    del first
    second = TaskStore(path)
    loaded = second.get("t1")
    assert loaded is not None
    assert loaded["prompt"] == "hello"
    assert loaded["result"] == {"answer": "world"}


# --- Coalesced (background-merged) durability --------------------------------


def test_coalesced_writer_flushes_on_close_and_survives_reopen(tmp_path) -> None:
    """Background-merged snapshots must all land once the writer is closed.

    This is the steady-state streaming path: many deltas coalesce to one dirty
    reference per task, then a final flush on close commits them.
    """
    path = tmp_path / "tasks.sqlite3"
    store = TaskStore(path)
    writer = _writer(store)
    for tid in ("a", "b", "c"):
        writer.enqueue(SimpleNamespace(task_id=tid, snapshot=_snapshot(tid, status="running")))
    writer.close()
    reopened = TaskStore(path)
    for tid in ("a", "b", "c"):
        assert reopened.get(tid) is not None


def test_coalesced_writer_keeps_only_last_snapshot_per_task(tmp_path) -> None:
    """Coalescing must collapse to one authoritative record, not duplicate."""
    path = tmp_path / "tasks.sqlite3"
    store = TaskStore(path)
    writer = _writer(store)
    writer.enqueue(SimpleNamespace(task_id="t", snapshot=_snapshot("t", step=1)))
    writer.enqueue(SimpleNamespace(task_id="t", snapshot=_snapshot("t", step=2)))
    writer.close()
    reopened = TaskStore(path)
    row = reopened.get("t")
    assert row is not None
    assert row["step"] == 2
    assert len([r for r in reopened.load(limit=100) if r.get("task_id") == "t"]) == 1


# --- SQLite connection lifecycle / WAL --------------------------------------


def test_store_uses_wal_journal_mode(tmp_path) -> None:
    """§3.2 explicitly calls for WAL under read/write load.

    WAL is a property of the database file, so any later connection to the
    same path reports it. If a refactor drops the pragma, this fails.
    """
    path = tmp_path / "tasks.sqlite3"
    TaskStore(path)
    with sqlite3.connect(path) as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode == "wal"


# --- Lease durability across restart ----------------------------------------


def test_lease_survives_store_reopen(tmp_path) -> None:
    """An active lease must still be visible after a process restart."""
    path = tmp_path / "tasks.sqlite3"
    first = TaskStore(path)
    assert first.claim_lease("t", "owner-a", pid=1)
    del first
    second = TaskStore(path)
    lease = second.get_lease("t")
    assert lease is not None
    assert lease["owner"] == "owner-a"


def test_evicted_worker_cannot_clobber_successor_after_reopen(tmp_path) -> None:
    """An expired/replaced lease blocks the old owner's upsert, and the
    successor's write is what survives a reopen.

    Prevents a late, stale running snapshot from overwriting the terminal
    result written by the process that legitimately took over.
    """
    path = tmp_path / "tasks.sqlite3"
    store = TaskStore(path)
    assert store.claim_lease("t", "owner-a", pid=1, ttl=-1)  # expires immediately
    # owner-a is now evicted; owner-b legitimately takes over.
    assert store.claim_lease("t", "owner-b", pid=2)
    stale = _snapshot("t", status="running", prompt="from dead worker")
    assert store.upsert(stale, lease_owner="owner-a") is False  # rejected
    good = _snapshot("t", status="completed", prompt="from live worker")
    assert store.upsert(good, lease_owner="owner-b") is True
    reopened = TaskStore(path)
    assert reopened.get("t")["prompt"] == "from live worker"


# --- Robustness: malformed rows ---------------------------------------------


def test_corrupt_payload_does_not_break_load_or_get(tmp_path) -> None:
    """A row with unparseable JSON must be skipped, never raise.

    Maintenance/prune and the refactor must preserve this — a single corrupt
    record must not blank out history or crash the UI projection.
    """
    path = tmp_path / "tasks.sqlite3"
    good = TaskStore(path)
    assert good.upsert(_snapshot("ok", status="completed"))
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO tasks(task_id, created_at, workspace_path, payload) VALUES (?,?,?,?)",
            ("bad", 0.0, "", "{not valid json"),
        )
    reopened = TaskStore(path)
    loaded = reopened.load(limit=100)
    ids = {row.get("task_id") for row in loaded}
    assert "ok" in ids
    assert "bad" not in ids
    assert reopened.get("bad") is None


# --- Privacy: what lands on disk is redacted, identity preserved ------------


def test_persisted_blob_is_redacted_but_identity_recoverable(tmp_path) -> None:
    """§3.2 notes redaction cost on every write; whatever is serialized must
    not contain the raw secret, yet the task_id must survive round-trip."""
    path = tmp_path / "tasks.sqlite3"
    store = TaskStore(path)
    assert store.upsert(_snapshot("t1", prompt="contact sk-abcdefghijklmnop secret"))
    with sqlite3.connect(path) as conn:
        payload = conn.execute("SELECT payload FROM tasks WHERE task_id='t1'").fetchone()[0]
    assert "sk-abcdefghijklmnop" not in payload  # raw secret never persisted
    assert "t1" in payload  # identity key recoverable
    assert store.get("t1")["task_id"] == "t1"
