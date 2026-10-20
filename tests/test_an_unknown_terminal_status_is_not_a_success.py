"""M8-T317 — 状态词表是**开放**的，所以"不认识"不等于"成功"

`StateGraph.run` 的终局判定只有一句：

```python
if target is None:
    if condition in {"failed", "error"}:
        state.finish("failed", outcome.error)
    else:
        state.finish("completed")
```

而 `NodeResult.status` 是一个**自由字符串**（默认 "ok"）。于是：

* 一个返回 `denied`（**写入被拒绝**）的节点 → 图以 **completed** 结束；
* 一个返回 `cancelled` 的节点 → 同样 completed；
* `AgentState.metrics()["status"]` 也就是 "completed"。

也就是说：**一次拒绝可以让整次运行把自己认证成成功**。

本门禁钉住：只有"成功"那几种状态才以 completed 结束；其余终局状态都是失败，
而且**说得清是哪一种**。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from minicc.agent.graph import GraphNode, NodeResult, StateGraph
from minicc.agent.state import AgentState


def _run(status: str) -> AgentState:
    graph = StateGraph("t", entry="a")
    graph.add_node(GraphNode("a", "phase"))
    graph.validate()
    state = AgentState("t", "phase")
    asyncio.run(graph.run(state, {"a": lambda _state: NodeResult(status=status)}))
    return state


def test_a_denied_node_is_not_a_completed_run() -> None:
    """The refusal must not certify the run."""
    state = _run("denied")
    assert state.status != "completed", (
        f"a denied node ended the run as completed: {state.metrics()}"
    )
    assert state.status == "failed", state.metrics()
    assert state.errors, "the refusal left no trace"


def test_a_cancelled_node_is_not_a_completed_run() -> None:
    """The same for a cancellation."""
    state = _run("cancelled")
    assert state.status == "failed", state.metrics()


def test_an_unknown_status_is_not_a_completed_run() -> None:
    """The vocabulary is open, so an unknown status is not a success."""
    state = _run("something-else")
    assert state.status == "failed", state.metrics()


def test_ok_still_completes() -> None:
    """The control: the ordinary path is unchanged."""
    state = _run("ok")
    assert state.status == "completed", state.metrics()
    assert not state.errors, state.errors


def test_failed_still_fails() -> None:
    """The control: the ordinary path is unchanged."""
    state = _run("failed")
    assert state.status == "failed", state.metrics()


def test_the_error_the_node_gave_is_kept() -> None:
    """A failure keeps the node's own explanation.

    (It is recorded twice - once by the node, once by ``finish`` - which is
    the long-standing behaviour of the ``failed`` path and not this
    batch's business; what this door pins is that the explanation is not
    **lost**.)
    """
    graph = StateGraph("t", entry="a")
    graph.add_node(GraphNode("a", "phase"))
    graph.validate()
    state = AgentState("t", "phase")
    asyncio.run(graph.run(state, {
        "a": lambda _state: NodeResult(status="denied", error="权限被拒绝")
    }))
    assert state.errors, "the node's own explanation was lost"
    assert all("权限被拒绝" in item for item in state.errors), state.errors
