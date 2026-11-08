"""M8-T538 — 一块还在说话的表，不该被墙钟判死

`minicc/task_manager.py` 的监视线程每 0.2 秒问一次
`has_live_worker(store, snapshot)`，而那个函数只回答一件与时钟有关的事：

    lease["expires"] > time.time()

`minicc/task_store.py` 的 `heartbeat_lease` 当时还带一句 `expires > now`
（M3-T5 加的栅栏），意思是「已过期的租约不许被迟到的续租救回来」。

两句话合起来就是：**一个活着的 worker 只要被 CPU 饿住、或被系统挂起超过
45 秒，它的租约就永久作废**。它回来之后续租会被自己的 owner 拒掉，
`has_live_worker` 继续答「死了」，host 抛
`RuntimeError: worker execution lease expired before completion`。
这台机器上同时跑四组 pytest 时，`tests/test_task_worker.py` 的两条门就是这样红的：
干净 HEAD 单跑是绿的，说明它不是产品逻辑错，是「谁没抢到 CPU 谁就是死的」。

M3-T5 想防的是「一只冻住的 worker 永远复活自己的租约」。但冻住的进程**不会**
发续租，栅栏一次都没拦住它；真正被拦住的是本文件这一种——没死、只是没抢到
CPU 的 worker。租约真正的排他栅栏是 **owner**：`claim_lease` 允许别的 owner 接管
已过期的租约，一旦接管，旧 owner 的续租与带 fence 的写入都写不进去。

本文件钉两件事：

1. 同一个 owner 可以续自己那条已过期的租约，接管之后则不行（store 层）；
2. 监视线程要**自己看见**一整段静默才判死——它被饿住的那段时间不算 worker 的账。
"""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from minicc import task_manager as manager_module
from minicc import task_worker as worker_module
from minicc.task_execution import has_live_worker
from minicc.task_manager import TaskManager, TaskRecord
from minicc.task_store import TaskStore


def _task(workspace: Path, task_id: str = "task-lease") -> TaskRecord:
    return TaskRecord(task_id, "test-session", "inspect source", False, workspace_path=str(workspace))


def _manager(tmp_path: Path) -> TaskManager:
    return TaskManager(SimpleNamespace(config=SimpleNamespace(yolo=False), workspace=tmp_path))


class _ScriptedStore:
    """A store that answers from a script instead of a database.

    ``live_from`` is the first 1-based ``get_lease`` poll that reports a live
    lease; ``finish_from`` is the first ``get`` poll that reports a terminal
    snapshot.  Both are None for "never".
    """

    def __init__(self, *, live_from: int | None, finish_from: int | None) -> None:
        self.live_from = live_from
        self.finish_from = finish_from
        self.lease_polls = 0
        self.snapshot_polls = 0

    def get(self, task_id: str) -> dict[str, object]:
        self.snapshot_polls += 1
        if self.finish_from is not None and self.snapshot_polls >= self.finish_from:
            return {"task_id": task_id, "status": "completed", "result": {"answer": "done"}}
        return {"task_id": task_id, "status": "running"}

    def get_lease(self, task_id: str) -> dict[str, object] | None:
        self.lease_polls += 1
        live = self.live_from is not None and self.lease_polls >= self.live_from
        return {"task_id": task_id, "owner": "owner-scripted",
                "expires": time.time() + (45.0 if live else -45.0)}


# --- store: the owner is the fence, the clock is not ------------------------


def test_a_starved_workers_late_heartbeat_revives_its_own_lease(tmp_path: Path) -> None:
    """The exact losing shape: expired row, same owner, worker still running."""
    store = TaskStore(tmp_path / "tasks.sqlite3")
    assert store.claim_lease("task", "owner-a", pid=1)
    # Negative ttl forces expiry, exactly like 45s of being starved would.
    assert store.heartbeat_lease("task", "owner-a", pid=1, ttl=-1)
    assert not has_live_worker(store, {"task_id": "task", "status": "running"})

    assert store.heartbeat_lease("task", "owner-a", pid=1), (
        "the live worker's own late heartbeat was refused; the task is now dead "
        "while the process that owns it is running"
    )
    assert has_live_worker(store, {"task_id": "task", "status": "running"})
    # Nobody else may take a lease that is live again.
    assert not store.claim_lease("task", "owner-b", pid=2)


def test_a_takeover_is_still_a_fence_for_the_previous_owner(tmp_path: Path) -> None:
    """The double-execution guard that survives: a new owner wins, the old one is out."""
    store = TaskStore(tmp_path / "tasks.sqlite3")
    assert store.claim_lease("task", "owner-a", pid=1)
    assert store.heartbeat_lease("task", "owner-a", pid=1, ttl=-1)
    assert store.claim_lease("task", "owner-b", pid=2)

    assert not store.heartbeat_lease("task", "owner-a", pid=1)
    assert not store.upsert({"task_id": "task", "status": "running"}, lease_owner="owner-a"), (
        "the fenced write of the previous owner landed after the takeover"
    )
    assert store.upsert({"task_id": "task", "status": "running"}, lease_owner="owner-b")


def test_an_expired_lease_that_nobody_took_still_lets_its_owner_write(
    tmp_path: Path,
) -> None:
    """The third face of the same defect: the write fence used the clock too.

    A starved worker that resumes flushes before its heartbeat renews.  The
    owner is unchanged and nobody has taken the lease, so the write belongs to
    the task's one process - but the expiry clause refused it and the worker
    turned that into ``AgentCancelled`` ("lease was lost").
    """
    store = TaskStore(tmp_path / "tasks.sqlite3")
    assert store.claim_lease("task", "owner-a", pid=1, ttl=-1)
    assert store.upsert({"task_id": "task", "status": "running"}, lease_owner="owner-a"), (
        "the only owner of the lease was refused its own write because the clock expired"
    )


# --- the host: silence counts only while the host is able to watch ----------


def test_the_monitor_waits_through_a_renewal_window_instead_of_convicting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Expired on the first ticks, renewed on the third: that is a live worker.

    This is the resume race - the host polls inside the worker's 5s renewal
    window right after both wake up.  It must not be a conviction.
    """
    monkeypatch.setattr(manager_module, "LEASE_REVIVAL_GRACE_SECONDS", 1.0)
    store = _ScriptedStore(live_from=3, finish_from=6)
    manager = _manager(tmp_path)
    try:
        result = manager._monitor_worker(_task(tmp_path), store)  # type: ignore[arg-type]
    finally:
        manager.shutdown()
    assert result["answer"] == "done", result
    assert store.lease_polls >= 3


def test_a_worker_that_never_comes_back_is_still_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The grace is a wait, not an amnesty: silence that lasts is still death."""
    monkeypatch.setattr(manager_module, "LEASE_REVIVAL_GRACE_SECONDS", 0.4)
    store = _ScriptedStore(live_from=None, finish_from=None)
    manager = _manager(tmp_path)
    began = time.monotonic()
    try:
        with pytest.raises(RuntimeError, match="lease expired before completion"):
            manager._monitor_worker(_task(tmp_path), store)  # type: ignore[arg-type]
    finally:
        manager.shutdown()
    elapsed = time.monotonic() - began
    assert elapsed >= 0.4, f"the monitor convicted after {elapsed:.2f}s, inside its own grace"


def test_the_grace_is_longer_than_the_renewal_interval_it_is_waiting_for() -> None:
    """A grace shorter than one heartbeat is decoration, not a grace.

    The worker renews every ``HEARTBEAT_INTERVAL``; the host's window has to
    cover at least two of those, otherwise the first renewal after a stall is
    always too late - which is the bug this file is about.
    """
    interval = worker_module.HEARTBEAT_INTERVAL
    assert manager_module.LEASE_REVIVAL_GRACE_SECONDS >= 2 * interval, (
        manager_module.LEASE_REVIVAL_GRACE_SECONDS, interval
    )
