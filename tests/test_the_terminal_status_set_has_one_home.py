"""M8-T343 — 「终态」这个事实有三个家，而其中一个家会删掉还在跑的任务

"哪些任务状态算终态"（completed / failed / cancelled / interrupted）这件事
在仓库里有**三份**手抄：

| 家 | 位置 |
| --- | --- |
| 正本 | `minicc/agent/protocol.py`（状态机与转移校验都用它） |
| 抄本 1 | `minicc/task_manager.py` |
| 抄本 2 | `minicc/task_store.py` |

三份今天内容一致，但**没有任何东西让它们保持一致**——而漂移的后果不是"两条
路径给出不同答案"这么轻：

* `task_store.prune` 删的是**终态**记录，"还在跑/在排队"的记录永远保留。
  抄本 2 若把一个活着的状态算成终态，剪枝就会**删掉一个还在跑的任务的记录**；
* `task_manager` 用它决定任务是不是已经结束、要不要再排队。抄本 1 若漏掉一个
  终态，那个任务就永远不结束。

本门钉住：终态集合只有一个家（三个名字是同一个对象）；三者对每个状态看法一
致；剪枝永远不删还在跑的任务记录。
"""

from __future__ import annotations

from pathlib import Path

from minicc import task_manager, task_store
from minicc.agent import protocol


def test_the_terminal_set_has_one_home() -> None:
    """One fact, one home: the other two modules import it."""
    assert task_manager.TERMINAL_TASK_STATUSES is protocol.TERMINAL_TASK_STATUSES
    assert task_store.TERMINAL_TASK_STATUSES is protocol.TERMINAL_TASK_STATUSES


def test_the_three_agree_on_every_status() -> None:
    """The content itself: a status is terminal for all three, or for none."""
    for status in protocol.TASK_STATUSES:
        terminal = status in protocol.TERMINAL_TASK_STATUSES
        assert (status in task_manager.TERMINAL_TASK_STATUSES) is terminal, status
        assert (status in task_store.TERMINAL_TASK_STATUSES) is terminal, status


def test_the_prune_never_deletes_a_task_that_is_still_running(tmp_path: Path) -> None:
    """The consequence of a drift, stated as a behaviour."""
    store = task_store.TaskStore(tmp_path / "tasks.sqlite3")
    for task_id, status in (
        ("live", "running"),
        ("waiting", "queued"),
        ("done", "completed"),
    ):
        store.upsert({
            "task_id": task_id,
            "status": status,
            "created_at_epoch": 0.0,
            "workspace_path": str(tmp_path),
        })
    deleted = store.prune(keep_terminal=0, max_age_days=None)
    assert "done" in deleted, deleted
    assert "live" not in deleted, deleted
    assert "waiting" not in deleted, deleted
    remaining = {str(item.get("task_id")) for item in store.load()}
    assert {"live", "waiting"} <= remaining, remaining
