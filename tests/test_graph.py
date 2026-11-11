"""M8-T787: minicc/agent/graph.py - flow graph tests.

Tests for the agent flow graph module:
- GraphNode, GraphEdge, NodeResult data classes
- StateGraph: node management, edge management, validation, execution
- DAG constants: DAG_KIND_*, READONLY_DAG_KINDS, NODE_STATUS_*, SUCCESS_STATUSES, FAILED_NODE_STATUSES
- PlanTask, DAGPlan: task planning and DAG validation
"""

from __future__ import annotations

import pytest

from minicc.agent.graph import (
    DAG_KIND_EXEC,
    DAG_KIND_MERGE,
    DAG_KIND_READONLY,
    DAG_KIND_REVIEW,
    DAG_KIND_WRITE,
    DAG_KINDS,
    GraphEdge,
    GraphNode,
    GraphValidationError,
    NODE_STATUS_COMPLETED,
    NODE_STATUS_FAILED,
    NODE_STATUS_RUNNING,
    NODE_STATUS_SKIPPED,
    NODE_STATUSES,
    READONLY_DAG_KINDS,
    READONLY_DAG_TOOLS,
    StateGraph,
    SUCCESS_STATUSES,
    VERIFY_DAG_TOOLS,
    WRITE_DAG_TOOLS,
)


# ============================================================================
# GraphNode
# ============================================================================

def test_graph_node_defaults() -> None:
    node = GraphNode(name="test_node", phase="inspect")
    assert node.name == "test_node"
    assert node.phase == "inspect"
    assert node.allowed_tools == frozenset()
    assert node.max_retries == 0


def test_graph_node_with_tools() -> None:
    node = GraphNode(
        name="test_node",
        phase="verify",
        allowed_tools={"read_file", "grep"},
        max_retries=3,
    )
    assert node.name == "test_node"
    assert node.phase == "verify"
    assert node.allowed_tools == frozenset({"read_file", "grep"})
    assert node.max_retries == 3


def test_graph_edge_defaults() -> None:
    edge = GraphEdge(source="a", target="b")
    assert edge.source == "a"
    assert edge.target == "b"
    assert edge.condition == "ok"


def test_graph_edge_with_condition() -> None:
    edge = GraphEdge(source="a", target="b", condition="error")
    assert edge.source == "a"
    assert edge.target == "b"
    assert edge.condition == "error"


def test_node_result_defaults() -> None:
    result = NodeResult()
    assert result.status == "ok"
    assert result.output == {}
    assert result.error is None
    assert result.next_node is None


def test_node_result_with_values() -> None:
    result = NodeResult(
        status="completed",
        output={"key": "value"},
        error=None,
        next_node="next_node",
    )
    assert result.status == "completed"
    assert result.output == {"key": "value"}
    assert result.error is None
    assert result.next_node == "next_node"


# ============================================================================
# DAG constants
# ============================================================================

def test_dag_kind_constants() -> None:
    assert DAG_KIND_READONLY == "readonly"
    assert DAG_KIND_WRITE == "write"
    assert DAG_KIND_EXEC == "exec"
    assert DAG_KIND_REVIEW == "review"
    assert DAG_KIND_MERGE == "merge"


def test_dag_kinds_frozenset() -> None:
    assert DAG_KINDS == frozenset({
        "readonly", "write", "exec", "review", "merge"
    })


def test_readonly_dag_kinds() -> None:
    assert READONLY_DAG_KINDS == frozenset({
        "readonly", "review", "merge"
    })


def test_readonly_dag_tools() -> None:
    assert READONLY_DAG_TOOLS == frozenset({
        "read_file", "grep", "git_status", "git_diff"
    })


# ============================================================================
# Node status constants
# ============================================================================

def test_node_status_constants() -> None:
    assert NODE_STATUS_RUNNING == "running"
    assert NODE_STATUS_COMPLETED == "completed"
    assert NODE_STATUS_FAILED == "failed"
    assert NODE_STATUS_SKIPPED == "skipped"


def test_node_statuses_frozenset() -> None:
    assert NODE_STATUSES == frozenset({
        "running", "completed", "failed", "skipped"
    })


def test_success_statuses() -> None:
    assert SUCCESS_STATUSES == frozenset({
        "ok", "done", "success", "completed", "passed"
    })


def test_failed_node_statuses() -> None:
    assert FAILED_NODE_STATUSES == frozenset({"failed", "error"})


# ============================================================================
# StateGraph
# ============================================================================

def test_state_graph_creation() -> None:
    graph = StateGraph(name="test_graph", entry="start")
    assert graph.name == "test_graph"
    assert graph.entry == "start"
    assert graph.nodes == {}
    assert graph.edges == []


def test_state_graph_add_node() -> None:
    graph = StateGraph()
    node = GraphNode(name="node1", phase="inspect")
    graph.add_node(node)
    assert "node1" in graph.nodes
    assert graph.nodes["node1"] is node


def test_state_graph_add_node_duplicate_rejected() -> None:
    graph = StateGraph()
    node = GraphNode(name="node1", phase="inspect")
    graph.add_node(node)
    with pytest.raises(GraphValidationError):
        graph.add_node(node)


def test_state_graph_add_node_negative_retries_rejected() -> None:
    graph = StateGraph()
    node = GraphNode(name="node1", phase="inspect", max_retries=-1)
    with pytest.raises(GraphValidationError):
        graph.add_node(node)


def test_state_graph_add_edge() -> None:
    graph = StateGraph()
    graph.add_node(GraphNode(name="a", phase="inspect"))
    graph.add_node(GraphNode(name="b", phase="verify"))
    graph.add_edge("a", "b", condition="ok")
    assert len(graph.edges) == 1
    assert graph.edges[0].source == "a"
    assert graph.edges[0].target == "b"
    assert graph.edges[0].condition == "ok"


def test_state_graph_validate_empty_rejected() -> None:
    graph = StateGraph()
    with pytest.raises(GraphValidationError):
        graph.validate()


def test_state_graph_validate_entry_missing() -> None:
    graph = StateGraph()
    graph.add_node(GraphNode(name="a", phase="inspect"))
    with pytest.raises(GraphValidationError):
        graph.validate()


def test_state_graph_validate_edge_missing_node() -> None:
    graph = StateGraph()
    graph.add_node(GraphNode(name="a", phase="inspect"))
    graph.add_edge("a", "nonexistent", condition="ok")
    with pytest.raises(GraphValidationError):
        graph.validate()


def test_state_graph_next_node() -> None:
    graph = StateGraph()
    graph.add_node(GraphNode(name="a", phase="inspect"))
    graph.add_node(GraphNode(name="b", phase="verify"))
    graph.add_edge("a", "b", condition="ok")
    assert graph.next_node("a", condition="ok") == "b"
    assert graph.next_node("a", condition="error") is None


def test_state_graph_next_node_wildcard() -> None:
    graph = StateGraph()
    graph.add_node(GraphNode(name="a", phase="inspect"))
    graph.add_node(GraphNode(name="b", phase="verify"))
    graph.add_edge("a", "b", condition="*")
    assert graph.next_node("a", condition="anything") == "b"


def test_state_graph_can_transition() -> None:
    graph = StateGraph()
    graph.add_node(GraphNode(name="a", phase="inspect"))
    graph.add_node(GraphNode(name="b", phase="verify"))
    graph.add_edge("a", "b", condition="ok")
    assert graph.can_transition("a", "b", condition="ok") is True
    assert graph.can_transition("a", "b", condition="*") is False
    assert graph.can_transition("a", "b", condition="error") is False
    assert graph.can_transition("b", "a", condition="ok") is False


# ============================================================================
# PlanTask
# ============================================================================

def test_plan_task_defaults() -> None:
    task = PlanTask(id="task1", kind="verify")
    assert task.id == "task1"
    assert task.kind == "verify"
    assert task.depends_on == ()
    assert task.allowed_tools == frozenset()
    assert task.max_retries == 0
    assert task.payload == {}


def test_plan_task_to_dict() -> None:
    task = PlanTask(
        id="task1",
        kind="verify",
        depends_on=("dep1",),
        allowed_tools={"read_file"},
        max_retries=2,
        payload={"key": "value"},
    )
    d = task.to_dict()
    assert d["id"] == "task1"
    assert d["kind"] == "verify"
    assert d["depends_on"] == ["dep1"]
    assert d["allowed_tools"] == ["read_file"]
    assert d["max_retries"] == 2
    assert d["payload"] == {"key": "value"}


# ============================================================================
# DAGPlan
# ============================================================================

def test_dag_plan_validation_empty() -> None:
    plan = DAGPlan(name="empty", tasks=[])
    with pytest.raises(GraphValidationError):
        plan.validate()


def test_dag_plan_validation_too_many_tasks() -> None:
    tasks = [
        PlanTask(id=f"task{i}", kind="verify")
        for i in range(33)
    ]
    plan = DAGPlan(name="too_many", tasks=tasks)
    with pytest.raises(GraphValidationError):
        plan.validate()


def test_dag_plan_validation_duplicate_ids() -> None:
    tasks = [
        PlanTask(id="dup", kind="verify"),
        PlanTask(id="dup", kind="verify"),
    ]
    plan = DAGPlan(name="dup", tasks=tasks)
    with pytest.raises(GraphValidationError):
        plan.validate()


def test_dag_plan_validation_self_dependency() -> None:
    tasks = [
        PlanTask(id="task1", kind="verify", depends_on=("task1",)),
    ]
    plan = DAGPlan(name="self_dep", tasks=tasks)
    with pytest.raises(GraphValidationError):
        plan.validate()


def test_dag_plan_validation_unknown_dependency() -> None:
    tasks = [
        PlanTask(id="task1", kind="verify", depends_on=("missing",)),
    ]
    plan = DAGPlan(name="unknown_dep", tasks=tasks)
    with pytest.raises(GraphValidationError):
        plan.validate()


def test_dag_plan_validation_cycle() -> None:
    tasks = [
        PlanTask(id="a", kind="verify", depends_on=("b",)),
        PlanTask(id="b", kind="verify", depends_on=("a",)),
    ]
    plan = DAGPlan(name="cycle", tasks=tasks)
    with pytest.raises(GraphValidationError):
        plan.validate()


def test_dag_plan_to_dict() -> None:
    task = PlanTask(id="task1", kind="verify", depends_on=("dep",), max_retries=1)
    plan = DAGPlan(name="test_plan", tasks=[task])
    d = plan.to_dict()
    assert d["name"] == "test_plan"
    assert len(d["tasks"]) == 1
    assert d["tasks"][0]["id"] == "task1"
    assert d["tasks"][0]["kind"] == "verify"
    assert d["tasks"][0]["depends_on"] == ["dep"]
    assert d["tasks"][0]["max_retries"] == 1
