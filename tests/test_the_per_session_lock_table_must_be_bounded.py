"""M8-T291: the per-session lock table must be bounded.

``session_id`` comes straight from the client, and the lock was taken
*before* ``SessionStore`` validated it.  The table only ever grew, so every
random id left a lock behind that was never released - a local page could
grow the workbench's memory without bound.

This door pins:

* the table stays bounded under many distinct session ids;
* the lock of a session that is currently running is not evicted;
* the control: the same session id still gets the same lock.
"""

from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from minicc.task_manager import _path_key
from minicc.web import AgentService


def _service(workspace: Path) -> AgentService:
    config = SimpleNamespace(
        yolo=False,
        max_concurrent_tasks=1,
        sandbox_mode="host",
        sandbox_image="python:3.11-slim",
        base_url="https://example.test/v1",
        api_key="test-key",
        model="test-model",
        timeout=10,
        tool_mode="auto",
        reasoning_effort="high",
        max_turns=4,
        compact_threshold=300_000,
        context_window_tokens=300_000,
    )
    return AgentService(workspace, config)


def test_the_lock_table_stays_bounded(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    service = _service(workspace)
    try:
        for index in range(1200):
            # The real flow: fetch the lock, take it, release it.
            session_id = f"random-{index}"
            lock = service._session_lock(workspace, session_id)
            lock.acquire()
            lock.release()
            service._mark_session_lock_used(workspace, session_id)
        assert len(service._session_locks) <= 512, (
            f"the lock table grew to {len(service._session_locks)} entries"
        )
    finally:
        service.shutdown()


def test_a_held_lock_is_not_evicted(tmp_path: Path) -> None:
    """A running turn's lock still protects it."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    service = _service(workspace)
    try:
        held = service._session_lock(workspace, "held")
        held.acquire()
        try:
            for index in range(1200):
                service._session_lock(workspace, f"random-{index}")
            key = f"{_path_key(workspace)}:held"
            assert key in service._session_locks, (
                "a held lock was evicted from the table"
            )
        finally:
            held.release()
    finally:
        service.shutdown()


def test_the_same_session_gets_the_same_lock(tmp_path: Path) -> None:
    """The control: the lock still serialises a session."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    service = _service(workspace)
    try:
        first = service._session_lock(workspace, "same")
        second = service._session_lock(workspace, "same")
        assert first is second, "the same session got two different locks"
    finally:
        service.shutdown()


def test_a_lock_handed_out_but_not_yet_taken_is_not_evicted(tmp_path: Path) -> None:
    """M8-T294: "not held" is not the same as "not in use".

    ``locked()`` is false between "handed out" and "acquired", so a lock
    that was just fetched may be evicted - and the next fetch for the same
    session would create a *second* lock, which is exactly the mutual
    exclusion the table exists to provide, gone.

    The lock here was held before, so the "never held" rule does not
    protect it; what protects it is that it is **in flight**.
    """
    workspace = tmp_path / "ws"
    workspace.mkdir()
    service = _service(workspace)
    try:
        # Held once, so it is a candidate for eviction.
        first = service._session_lock(workspace, "inflight")
        first.acquire()
        first.release()
        service._mark_session_lock_used(workspace, "inflight")
        # Fetched again: handed out, not yet taken.
        in_flight = service._session_lock(workspace, "inflight")
        assert in_flight is first
        # Push the table over its ceiling with other sessions.
        for index in range(1200):
            session_id = f"random-{index}"
            lock = service._session_lock(workspace, session_id)
            lock.acquire()
            lock.release()
            service._mark_session_lock_used(workspace, session_id)
        again = service._session_lock(workspace, "inflight")
        assert again is first, (
            "the in-flight lock was evicted, so the same session can end up "
            "with two different locks"
        )
    finally:
        service.shutdown()
