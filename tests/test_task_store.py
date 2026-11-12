"""M8-T813: minicc/task_store.py - task store tests.

Tests for:
- _IDENTITY_KEYS: identity key fields
- _SNIPPET_CONTEXT_CHARS: snippet context characters
- _MAX_MATCH_COUNT: max match count
- TaskStore: task storage operations
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from minicc.task_store import (
    _IDENTITY_KEYS,
    _MAX_MATCH_COUNT,
    _SNIPPET_CONTEXT_CHARS,
    TaskStore,
)


# ============================================================================
# Constants
# ============================================================================

def test_identity_keys() -> None:
    assert isinstance(_IDENTITY_KEYS, (list, tuple, set, frozenset))
    assert len(_IDENTITY_KEYS) > 0


def test_snippet_context_chars() -> None:
    assert isinstance(_SNIPPET_CONTEXT_CHARS, int)
    assert _SNIPPET_CONTEXT_CHARS > 0


def test_max_match_count() -> None:
    assert isinstance(_MAX_MATCH_COUNT, int)
    assert _MAX_MATCH_COUNT > 0


# ============================================================================
# TaskStore
# ============================================================================

def test_task_store_creation() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        store = TaskStore(db_path)
        assert store is not None
        store.close()


def test_task_store_upsert_and_load() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        store = TaskStore(db_path)
        result = store.upsert({"task_id": "task-1", "title": "test task", "status": "pending"})
        assert result is True
        loaded = store.load()
        assert isinstance(loaded, list)
        assert len(loaded) >= 1
        assert loaded[0]["title"] == "test task"
        store.close()


def test_task_store_upsert_many() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        store = TaskStore(db_path)
        count = store.upsert_many([
            {"task_id": "task-1", "title": "task 1", "status": "pending"},
            {"task_id": "task-2", "title": "task 2", "status": "completed"},
        ])
        assert count == 2
        store.close()


def test_task_store_search() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        store = TaskStore(db_path)
        store.upsert({"task_id": "task-1", "title": "fix login bug", "status": "open"})
        store.upsert({"task_id": "task-2", "title": "update dependencies", "status": "closed"})
        results = store.search("login")
        assert isinstance(results, list)
        store.close()


def test_task_store_list_by_session() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        store = TaskStore(db_path)
        store.upsert({"task_id": "task-1", "title": "task 1", "session_id": "sess-1", "status": "open"})
        store.upsert({"task_id": "task-2", "title": "task 2", "session_id": "sess-2", "status": "open"})
        results = store.list_by_session("sess-1")
        assert isinstance(results, list)
        store.close()


def test_task_store_claim_and_release_lease() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        store = TaskStore(db_path)
        store.upsert({"task_id": "task-1", "title": "task", "status": "pending"})
        lease = store.claim_lease("task-1", "worker-1")
        assert lease is not None
        store.release_lease("task-1", "worker-1")
        store.close()


def test_task_store_upsert_no_task_id() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        store = TaskStore(db_path)
        result = store.upsert({"title": "no task id"})
        assert result is False
        store.close()
