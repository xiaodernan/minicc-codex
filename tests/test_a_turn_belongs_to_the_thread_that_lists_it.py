"""M8-T298 — 一个线程的 turn，不能被另一个线程读走

`turn/read` 同时接受**线程 id**与**turn id**。原来 turn 是从**全局**任务表
里取的，而返回的载荷又把 `thread_id` **覆盖**成请求里的那个——于是：

* 读 B 线程的 turn，却挂在 A 线程名下返回；
* 载荷自相矛盾（`turn.thread_id` 是真的，顶层的 `thread_id` 是假的）；
* 一个会话能读到另一个会话的 turn 内容。

turn **属于**列出它的那���线程；不属于的，就是那里没有。
"""

from __future__ import annotations

import types
from pathlib import Path

import pytest

from minicc.task_store import TaskStore
from minicc.web import AgentService


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


def _submit(service: AgentService, thread_id: str, message: str) -> str:
    """Open a thread and run one turn in it."""
    service._rpc_thread_start({
        "thread_id": thread_id,
        "workspace_path": str(service.workspace),
    })
    started = service._rpc_turn_start({
        "thread_id": thread_id,
        "workspace_path": str(service.workspace),
        "message": message,
    })
    return str(started["turn_id"])


def test_a_turn_of_another_thread_is_not_readable(tmp_path: Path) -> None:
    """The hole: thread A naming thread B's turn."""
    service = _service(tmp_path)
    try:
        _submit(service, "thread-a", "A 的问题")
        other_turn = _submit(service, "thread-b", "B 的问题")

        with pytest.raises(KeyError):
            service._rpc_turn_read({
                "thread_id": "thread-a",
                "turn_id": other_turn,
            })
    finally:
        service.shutdown()


def test_a_turn_of_its_own_thread_is_readable(tmp_path: Path) -> None:
    """The control: the ordinary path is unchanged."""
    service = _service(tmp_path)
    try:
        own_turn = _submit(service, "thread-a", "A 的问题")
        payload = service._rpc_turn_read({
            "thread_id": "thread-a",
            "turn_id": own_turn,
        })
        assert payload["turn_id"] == own_turn
        assert payload["thread_id"] == "thread-a"
    finally:
        service.shutdown()


def test_a_turn_read_without_a_thread_still_works(tmp_path: Path) -> None:
    """The control: the thread-less form keeps working."""
    service = _service(tmp_path)
    try:
        turn = _submit(service, "thread-a", "A 的问题")
        payload = service._rpc_turn_read({"turn_id": turn})
        assert payload["turn_id"] == turn
    finally:
        service.shutdown()
