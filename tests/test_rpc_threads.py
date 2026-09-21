"""M3-T8: bounded RPC thread cache + thread_id validation.

The ``_rpc_threads`` cache used to grow without limit on arbitrary client-
supplied ``thread_id`` keys, letting any local page inflate the workbench heap.
These tests pin the bound (insertion-order eviction at ``_RPC_THREADS_MAX``) and
the input validation (oversize / control-character ids rejected as invalid
params, which the JSON-RPC layer surfaces as -32602).
"""

from __future__ import annotations

import types
from pathlib import Path

import pytest

from minicc.task_store import TaskStore
from minicc.web import AgentService, _RPC_THREADS_MAX, _THREAD_ID_MAX_LEN


def _service(tmp_path: Path) -> AgentService:
    config = types.SimpleNamespace(
        yolo=False,
        max_concurrent_tasks=2,
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
    return AgentService(
        tmp_path, config, task_store=TaskStore(tmp_path / "tasks.sqlite3")
    )


def test_thread_cache_is_bounded_and_evicts_oldest(tmp_path: Path) -> None:
    service = _service(tmp_path)
    total = 2000  # acceptance: 2000 thread/start calls with distinct ids
    for i in range(total):
        service._rpc_thread_start({"thread_id": f"thread-client-{i:05d}"})
    with service._rpc_thread_guard:
        assert len(service._rpc_threads) <= _RPC_THREADS_MAX
        keys = list(service._rpc_threads.keys())
    # Oldest keys evicted, newest retained.
    assert "thread-client-00000" not in keys
    assert f"thread-client-{total - 1:05d}" in keys


def test_thread_read_refreshes_recency(tmp_path: Path) -> None:
    """A cache hit moves the entry to the newest end (true LRU, not FIFO)."""
    service = _service(tmp_path)
    service._rpc_thread_start({"thread_id": "thread-a"})
    others = [f"thread-o-{i:05d}" for i in range(_RPC_THREADS_MAX - 1)]
    for tid in others:
        service._rpc_thread_start({"thread_id": tid})
    with service._rpc_thread_guard:
        assert len(service._rpc_threads) == _RPC_THREADS_MAX
    # Touch thread-a so it becomes most-recently used.
    service._rpc_thread_record("thread-a")
    # One more insert evicts the oldest (others[0]), not the refreshed thread-a.
    service._rpc_thread_start({"thread_id": "thread-new"})
    with service._rpc_thread_guard:
        assert "thread-a" in service._rpc_threads
        assert others[0] not in service._rpc_threads


def test_oversize_thread_id_rejected(tmp_path: Path) -> None:
    service = _service(tmp_path)
    huge = "a" * (_THREAD_ID_MAX_LEN + 1)
    with pytest.raises(ValueError):
        service._rpc_thread_start({"thread_id": huge})
    # 8KB id (the roadmap's stress case) is far over the cap.
    with pytest.raises(ValueError):
        service._rpc_thread_start({"thread_id": "b" * 8192})


def test_oversize_thread_id_maps_to_invalid_params(tmp_path: Path) -> None:
    service = _service(tmp_path)
    huge = "a" * (_THREAD_ID_MAX_LEN + 1)
    response = service.rpc_dispatcher.dispatch(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "thread/start",
            "params": {"thread_id": huge},
        }
    )
    assert response["error"]["code"] == -32602


def test_control_character_thread_id_rejected(tmp_path: Path) -> None:
    service = _service(tmp_path)
    for bad in ("bad\nid", "bad\x00id", "bad\x1b[31mid", "bad\x7fid"):
        with pytest.raises(ValueError):
            service._rpc_thread_start({"thread_id": bad})


def test_generated_thread_id_still_accepted(tmp_path: Path) -> None:
    """No regression: omitting thread_id yields a valid generated id."""
    service = _service(tmp_path)
    view = service._rpc_thread_start({})
    assert view["thread_id"].startswith("thread-")
    with service._rpc_thread_guard:
        assert view["thread_id"] in service._rpc_threads
