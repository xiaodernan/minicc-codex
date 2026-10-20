"""M8-T272: ``get()`` must repair the id the way ``load()`` does.

``TaskStore.load`` already treated the relational primary key as
authoritative: an older version redacted the ``sk-`` substring inside
``task-...``, so the payload's own ``task_id`` was unusable and the row's
was put back.  ``get()`` did not - it selected only the payload and returned
it as-is.

Every liveness decision goes through ``get()``: ``has_live_worker`` looks
the lease up under ``snapshot["task_id"]``.  With a payload whose id was
missing or redacted, that lookup used the wrong key, the lease came back
``None``, and the code fell back to the legacy ``worker_version`` + 45 second
heartbeat heuristic.  That fallback reports a dead worker as alive (so the
task is never re-queued) and a live one as dead (so the run is killed
mid-flight).

This door pins:

* ``get()`` returns the authoritative id for a payload that lost it;
* the lease is found through ``get()``;
* the control: a payload with a good id is returned unchanged.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from minicc.task_execution import has_live_worker
from minicc.task_store import TaskStore


def _store(tmp_path: Path) -> TaskStore:
    return TaskStore(tmp_path / "tasks.sqlite3")


def _write_raw(store: TaskStore, task_id: str, payload: dict[str, object]) -> None:
    """Write a snapshot whose payload disagrees with the relational key."""
    with store._lock, store._connect() as connection:  # noqa: SLF001 - the point is the raw row
        connection.execute(
            "INSERT OR REPLACE INTO tasks(task_id, created_at, workspace_path, payload) "
            "VALUES (?, ?, ?, ?)",
            (task_id, time.time(), "", json.dumps(payload, ensure_ascii=False)),
        )


def test_get_returns_the_authoritative_id_when_the_payload_lost_it(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    _write_raw(store, "task-abc", {"status": "running", "task_id": ""})
    snapshot = store.get("task-abc")
    assert snapshot is not None
    assert snapshot["task_id"] == "task-abc"


def test_get_repairs_a_redacted_id(tmp_path: Path) -> None:
    """The shape an older version actually wrote."""
    store = _store(tmp_path)
    _write_raw(store, "task-abc", {
        "status": "running",
        "task_id": "ta[REDACTED:llm_api_key]",
    })
    snapshot = store.get("task-abc")
    assert snapshot is not None
    assert snapshot["task_id"] == "task-abc"


def test_the_lease_is_found_through_get(tmp_path: Path) -> None:
    """The control that shows why the id matters."""
    store = _store(tmp_path)
    _write_raw(store, "task-abc", {"status": "running", "task_id": ""})
    assert store.claim_lease("task-abc", "owner-1")

    snapshot = store.get("task-abc")
    assert snapshot is not None
    assert has_live_worker(store, snapshot), (
        "the lease was not found, so liveness fell back to the legacy heuristic"
    )


def test_a_payload_with_a_good_id_is_returned_unchanged(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _write_raw(store, "task-abc", {"status": "running", "task_id": "task-abc"})
    snapshot = store.get("task-abc")
    assert snapshot is not None
    assert snapshot["task_id"] == "task-abc"
    assert snapshot["status"] == "running"


def test_load_and_get_agree_on_the_repaired_id(tmp_path: Path) -> None:
    """The two doors must not answer differently about the same row."""
    store = _store(tmp_path)
    _write_raw(store, "task-abc", {"status": "running", "task_id": ""})
    loaded = [item for item in store.load() if item.get("task_id") == "task-abc"]
    assert len(loaded) == 1
    single = store.get("task-abc")
    assert single is not None
    assert single["task_id"] == loaded[0]["task_id"]


def test_a_missing_row_still_returns_none(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert store.get("task-does-not-exist") is None
