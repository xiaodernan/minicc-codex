"""M8-T716: `/cost` asks for one session's snapshots and has never been able to read them.

Measured before this batch (`scratch/probe716.py`, `scratch/probe716b.py`):

* ``SessionStore.list_snapshots`` hands ``TaskStore`` the *workspace directory*
  where a database *file* belongs.  With a real store present the question
  answers ``OperationalError: unable to open database file``.
* With no store present, ``TaskStore.__init__`` connects to that path anyway and
  SQLite **creates a 61,440-byte file named after the workspace** — so the
  directory can never be created afterwards.  A read-only question wrote it.
* ``TaskStore`` has no ``list_by_session`` at all; the caller at
  ``minicc/session.py:359`` has been dangling.

The one home for the path is ``<workspace>/.minicc/tasks.sqlite3``
(``minicc/task_manager.py:2480``, ``minicc/task_worker.py:244``).
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import pytest

from minicc.session import SessionStore
from minicc.stats import _task_stats
from minicc.task_store import TaskStore
from minicc.tools.registry import REDACTED_LLM_API_KEY

SESSION = "cost-probe"


def _db(workspace: Path) -> Path:
    """The path the worker and the task manager both write to."""
    return workspace / ".minicc" / "tasks.sqlite3"


def _snapshot(task_id: str, session_id: str = SESSION, **extra: object) -> dict:
    payload = {
        "task_id": task_id,
        "session_id": session_id,
        "created_at_epoch": time.time(),
        "created_at": "2026-11-09T00:00:00Z",
        "status": "completed",
        "prompt": "how much did this session cost",
        "tokens_used": {"total_tokens": 1234},
        "cost_usd": 0.002,
    }
    payload.update(extra)
    return payload


def _recorded(workspace: Path, *payloads: dict) -> TaskStore:
    store = TaskStore(_db(workspace))
    for payload in payloads:
        store.upsert(payload)
    return store


def _session(workspace: Path) -> SessionStore:
    session = SessionStore(workspace, SESSION)
    session.save([{"role": "user", "content": "hi"}])
    return session


def _raw_rows(workspace: Path) -> list[tuple[str, str]]:
    with sqlite3.connect(_db(workspace)) as connection:
        return connection.execute("SELECT task_id, payload FROM tasks ORDER BY created_at ASC").fetchall()


# --------------------------------------------------------------------------
# The cells this batch owes
# --------------------------------------------------------------------------


def test_a_session_that_recorded_a_snapshot_can_read_it_back_for_its_cost(
    tmp_path: Path,
) -> None:
    """E1: the store is real, the row is there, and the question still cannot open it."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    store = _recorded(workspace, _snapshot("t1"))
    assert len(store.load()) == 1, "the fixture must really have written a row"
    session = _session(workspace)

    snapshots = session.list_snapshots()

    assert [s["task_id"] for s in snapshots] == ["t1"], snapshots
    assert snapshots[0]["tokens_used"]["total_tokens"] == 1234, snapshots


def test_asking_the_cost_of_a_workspace_that_does_not_exist_writes_nothing(
    tmp_path: Path,
) -> None:
    """E2: before this batch the question left a 61,440-byte SQLite file at ``ws``."""
    workspace = tmp_path / "never-created"
    assert not workspace.exists()
    session = SessionStore(workspace, SESSION)

    assert session.list_snapshots() == []

    assert not workspace.exists(), sorted(p.name for p in tmp_path.iterdir())
    assert sorted(p.name for p in tmp_path.iterdir()) == []


def test_the_store_can_list_one_session_oldest_first(tmp_path: Path) -> None:
    """E3: the method the caller names has to exist, and keep the ported ordering."""
    store = _recorded(
        tmp_path / "ws",
        _snapshot("later", created_at_epoch=time.time() + 10),
        _snapshot("earlier", created_at_epoch=time.time() - 10),
    )

    listed = store.list_by_session(SESSION)

    assert [s["task_id"] for s in listed] == ["earlier", "later"], listed


def test_a_torn_row_beside_the_session_does_not_destroy_the_readable_answer(
    tmp_path: Path,
) -> None:
    """E4: one unparseable payload must not take the whole answer down with it.

    This is why the ported SQL was **not** copied verbatim.  The backup branch
    filters with ``json_extract(payload, '$.session_id') = ?``; measured on this
    interpreter (SQLite 3.39.4) that raises ``OperationalError: malformed JSON``
    for the torn row, so a single bad record — even one belonging to another
    session — costs every readable record its seat.
    """
    workspace = tmp_path / "ws"
    store = _recorded(workspace, _snapshot("good"))
    with sqlite3.connect(_db(workspace)) as connection:
        connection.execute(
            "INSERT INTO tasks(task_id, created_at, workspace_path, payload) VALUES (?, ?, ?, ?)",
            ("torn", time.time(), str(workspace), '{"session_id": "cost-probe", '),
        )
    assert len(_raw_rows(workspace)) == 2, _raw_rows(workspace)

    listed = store.list_by_session(SESSION)

    assert [s["task_id"] for s in listed] == ["good"], listed


def test_a_redacted_id_is_repaired_from_the_primary_key_like_load_does(
    tmp_path: Path,
) -> None:
    """E5: the ported method keeps ``load()``'s repair, not a second spelling of it."""
    workspace = tmp_path / "ws"
    store = _recorded(workspace, _snapshot("t-clean"))
    # ``upsert`` redacts on the way in and refuses an empty id, so the shape the
    # repair exists for — a clean primary key over a redacted payload id — can
    # only be written by the older writer this repair was added for.
    payload = dict(_snapshot(f"task-{REDACTED_LLM_API_KEY}"))
    with sqlite3.connect(_db(workspace)) as connection:
        connection.execute(
            "UPDATE tasks SET payload = ? WHERE task_id = ?",
            (json.dumps(payload, ensure_ascii=False), "t-clean"),
        )
    assert REDACTED_LLM_API_KEY in _raw_rows(workspace)[0][1]

    listed = store.list_by_session(SESSION)

    assert [s["task_id"] for s in listed] == ["t-clean"], listed


def test_a_store_with_no_row_for_this_session_is_an_empty_list(tmp_path: Path) -> None:
    """E6: absent data and unreadable data are different answers; this is the former."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _recorded(workspace, _snapshot("other", session_id="a-different-session"))
    session = _session(workspace)

    assert session.list_snapshots() == []
    assert _db(workspace).is_file(), "the store was there; only this session had no row"


# --------------------------------------------------------------------------
# Controls: these already hold, and this batch may not change their answer
# --------------------------------------------------------------------------


def test_the_fixture_really_writes_where_the_worker_writes(tmp_path: Path) -> None:
    """D0: if the row were somewhere else, E1 would pass by finding nothing."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    store = _recorded(workspace, _snapshot("t1"))
    assert _db(workspace).is_file()
    assert store.path == _db(workspace)
    assert [s["task_id"] for s in store.load()] == ["t1"]
    assert json.loads(_raw_rows(workspace)[0][1])["session_id"] == SESSION


def test_an_absent_store_is_reported_absent_and_not_created(tmp_path: Path) -> None:
    """C1: ``stats`` already draws the line E2 extends to ``/cost``."""
    state = tmp_path / "state"
    state.mkdir()

    # Hermetic: pin the workspace root to this tmp dir — without it the probe
    # falls back to the developer's cwd and answers "present" from matching
    # rows in the shared home store (which hard-fails on a machine that ran
    # real work), while staying green on a clean runner.
    reported = _task_stats(state, tmp_path)

    assert reported["present"] is False, reported
    assert reported["total"] == 0, reported
    assert not (state / "tasks.sqlite3").exists()


def test_a_store_path_that_is_a_directory_is_a_failure_not_an_empty_session(
    tmp_path: Path,
) -> None:
    """C3: the honest absence test is ``exists``, not ``is_file``.

    ``is_file()`` would answer ``[]`` for a directory sitting where the database
    belongs — "this session has no tasks" in place of "I could not open the
    store".  The failure has to reach ``/cost``'s ``读取快照失败`` branch.
    """
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _db(workspace).mkdir(parents=True)
    session = _session(workspace)

    with pytest.raises(sqlite3.OperationalError):
        session.list_snapshots()