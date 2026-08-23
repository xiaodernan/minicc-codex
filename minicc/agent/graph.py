"""Small, bounded StateGraph and DAG primitives for agent orchestration.

The graph layer owns transitions and dependency scheduling. Node handlers remain
ordinary Python callables, so the LLM protocol and existing tools do not need
to know about the orchestration implementation.
"""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Iterable

from .state import AgentState, BudgetExceeded


class GraphValidationError(ValueError):
    """A graph or plan violates its structural limits."""


@dataclass(frozen=True)
class GraphNode:
    name: str
    phase: str
    allowed_tools: frozenset[str] = frozenset()
    max_retries: int = 0


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    condition: str = "ok"


@dataclass
class NodeResult:
    status: str = "ok"
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    next_node: str | None = None


NodeHandler = Callable[[AgentState], NodeResult | Awaitable[NodeResult]]


class StateGraph:
    """A bounded conditional state machine with auditable transitions."""

    def __init__(self, name: str = "agent", entry: str = "intake") -> None:
        self.name = name
        self.entry = entry
        self.nodes: dict[str, GraphNode] = {}
        self.edges: list[GraphEdge] = []

    def add_node(self, node: GraphNode) -> "StateGraph":
        if node.name in self.nodes:
            raise GraphValidationError(f"重复节点: {node.name}")
        if node.max_retries < 0:
            raise GraphValidationError(f"节点重试次数不能为负数: {node.name}")
        self.nodes[node.name] = node
        return self

    def add_edge(self, source: str, target: str, condition: str = "ok") -> "StateGraph":
        self.edges.append(GraphEdge(source, target, condition))
        return self

    def validate(self, *, max_nodes: int = 32) -> None:
        if not self.nodes:
            raise GraphValidationError("图不能为空")
        if len(self.nodes) > max_nodes:
            raise GraphValidationError(f"节点数超过上限 {max_nodes}")
        if self.entry not in self.nodes:
            raise GraphValidationError(f"入口节点不存在: {self.entry}")
        for edge in self.edges:
            if edge.source not in self.nodes or edge.target not in self.nodes:
                raise GraphValidationError(f"边引用了未知节点: {edge.source}->{edge.target}")
            if not edge.condition:
                raise GraphValidationError("边条件不能为空")

    def next_node(self, source: str, condition: str = "ok") -> str | None:
        exact = [edge.target for edge in self.edges if edge.source == source and edge.condition == condition]
        if exact:
            return exact[0]
        fallback = [edge.target for edge in self.edges if edge.source == source and edge.condition == "*"]
        return fallback[0] if fallback else None

    def can_transition(self, source: str, target: str, condition: str = "ok") -> bool:
        return any(
            edge.source == source
            and edge.target == target
            and edge.condition in {condition, "*"}
            for edge in self.edges
        )

    async def run(
        self,
        state: AgentState,
        handlers: dict[str, NodeHandler],
        *,
        max_steps: int = 64,
    ) -> AgentState:
        self.validate()
        current = self.entry
        visits: dict[str, int] = {}
        for _step in range(max_steps):
            visits[current] = visits.get(current, 0) + 1
            node = self.nodes[current]
            if visits[current] > node.max_retries + 1:
                raise GraphValidationError(f"节点 {current} 超过重试上限")
            state.transition(current, phase=node.phase)
            handler = handlers.get(current)
            if handler is None:
                outcome = NodeResult()
            else:
                raw = handler(state)
                outcome = await raw if inspect.isawaitable(raw) else raw
                if not isinstance(outcome, NodeResult):
                    raise GraphValidationError(f"节点 {current} 返回值必须是 NodeResult")
            if outcome.output:
                state.outputs[current] = dict(outcome.output)
            if outcome.error:
                state.errors.append(outcome.error)
            condition = outcome.status
            target = outcome.next_node or self.next_node(current, condition)
            if target is None:
                if condition in {"failed", "error"}:
                    state.finish("failed", outcome.error)
                else:
                    state.finish("completed")
                return state
            if not self.can_transition(current, target, condition):
                raise GraphValidationError(f"非法转移: {current} -[{condition}]-> {target}")
            current = target
        raise BudgetExceeded(f"StateGraph 超过最大步骤 {max_steps}")


@dataclass(frozen=True)
class PlanTask:
    id: str
    kind: str
    depends_on: tuple[str, ...] = ()
    allowed_tools: frozenset[str] = frozenset()
    max_retries: int = 0
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "depends_on": list(self.depends_on),
            "allowed_tools": sorted(self.allowed_tools),
            "max_retries": self.max_retries,
            "payload": dict(self.payload),
        }


@dataclass
class DAGPlan:
    name: str
    tasks: tuple[PlanTask, ...]

    def validate(self, *, max_nodes: int = 32, max_depth: int = 16) -> tuple[str, ...]:
        if not self.tasks:
            raise GraphValidationError("DAG 不能为空")
        if len(self.tasks) > max_nodes:
            raise GraphValidationError(f"DAG 节点数超过上限 {max_nodes}")
        ids = [task.id for task in self.tasks]
        if len(ids) != len(set(ids)) or any(not item for item in ids):
            raise GraphValidationError("DAG 节点 id 必须唯一且非空")
        task_map = {task.id: task for task in self.tasks}
        indegree = {task.id: 0 for task in self.tasks}
        outgoing: dict[str, list[str]] = {task.id: [] for task in self.tasks}
        for task in self.tasks:
            if task.max_retries < 0:
                raise GraphValidationError(f"节点重试次数不能为负数: {task.id}")
            if task.id in task.depends_on:
                raise GraphValidationError(f"节点不能依赖自身: {task.id}")
            for dependency in task.depends_on:
                if dependency not in task_map:
                    raise GraphValidationError(f"节点 {task.id} 依赖未知节点 {dependency}")
                indegree[task.id] += 1
                outgoing[dependency].append(task.id)
        ready = [task.id for task in self.tasks if indegree[task.id] == 0]
        order: list[str] = []
        depths = {item: 1 for item in ready}
        while ready:
            current = ready.pop(0)
            order.append(current)
            for child in outgoing[current]:
                depths[child] = max(depths.get(child, 1), depths[current] + 1)
                indegree[child] -= 1
                if indegree[child] == 0:
                    ready.append(child)
        if len(order) != len(self.tasks):
            raise GraphValidationError("DAG 存在环")
        if max(depths.values(), default=0) > max_depth:
            raise GraphValidationError(f"DAG 深度超过上限 {max_depth}")
        return tuple(order)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "tasks": [task.to_dict() for task in self.tasks]}


@dataclass
class DAGResult:
    status: str
    completed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    attempts: dict[str, int] = field(default_factory=dict)


async def execute_dag(
    plan: DAGPlan,
    handler: Callable[[PlanTask], dict[str, Any] | Awaitable[dict[str, Any]]],
    *,
    max_concurrency: int = 4,
) -> DAGResult:
    """Execute ready nodes in bounded waves; failed dependencies skip children."""
    plan.validate()
    if max_concurrency < 1:
        raise GraphValidationError("max_concurrency 必须至少为 1")
    task_map = {task.id: task for task in plan.tasks}
    pending = set(task_map)
    result = DAGResult(status="running")
    while pending:
        blocked = [
            task_id
            for task_id in pending
            if any(dependency in result.failed or dependency in result.skipped for dependency in task_map[task_id].depends_on)
        ]
        for task_id in blocked:
            pending.remove(task_id)
            result.skipped.append(task_id)
            result.outputs[task_id] = {"status": "skipped", "reason": "dependency_failed"}

        ready = [
            task_map[task_id]
            for task_id in pending
            if all(dependency in result.completed for dependency in task_map[task_id].depends_on)
        ]
        if not ready:
            if pending:
                raise GraphValidationError("DAG 调度停滞：剩余节点没有满足依赖")
            break
        wave = ready[:max_concurrency]

        async def run_one(task: PlanTask) -> tuple[PlanTask, dict[str, Any], int]:
            attempts = 0
            while True:
                attempts += 1
                result.attempts[task.id] = attempts
                try:
                    raw = handler(task)
                    output = await raw if inspect.isawaitable(raw) else raw
                    if not isinstance(output, dict):
                        output = {"value": output}
                    if output.get("status", "completed") in {"failed", "error"}:
                        raise RuntimeError(str(output.get("error") or output.get("status")))
                    return task, {**output, "status": "completed"}, attempts
                except Exception as exc:  # noqa: BLE001 - node failure is data
                    if attempts > task.max_retries:
                        return task, {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}, attempts

        wave_results = await asyncio.gather(*(run_one(task) for task in wave))
        for task, output, attempts in wave_results:
            pending.remove(task.id)
            result.outputs[task.id] = output
            result.attempts[task.id] = attempts
            if output.get("status") == "completed":
                result.completed.append(task.id)
            else:
                result.failed.append(task.id)
    result.status = "failed" if result.failed else "completed"
    return result


def build_coding_workflow() -> StateGraph:
    """Return the fixed coding workflow from the roadmap."""
    graph = StateGraph("coding", entry="intake")
    for node, phase, retries in (
        ("intake", "intake", 0),
        ("plan", "planning", 0),
        ("inspect", "inspect", 0),
        ("implement", "implement", 0),
        ("verify", "verify", 2),
        ("repair", "repair", 2),
        ("summarize", "summarize", 0),
    ):
        graph.add_node(GraphNode(node, phase, max_retries=retries))
    graph.add_edge("intake", "plan")
    graph.add_edge("plan", "inspect")
    graph.add_edge("inspect", "implement")
    graph.add_edge("implement", "verify")
    graph.add_edge("verify", "summarize", "ok")
    graph.add_edge("verify", "repair", "failed")
    graph.add_edge("repair", "verify", "ok")
    graph.add_edge("repair", "summarize", "failed")
    graph.validate()
    return graph


def fixed_plan(name: str, *, task_count: int = 0) -> DAGPlan:
    """Build one of the bounded templates described in the roadmap."""
    if name == "inspect_summarize":
        tasks = (
            PlanTask("inspect", "readonly", allowed_tools=frozenset({"read_file", "grep", "git_status"})),
            PlanTask("summarize", "readonly", depends_on=("inspect",)),
        )
    elif name == "inspect_implement_verify":
        tasks = (
            PlanTask("inspect", "readonly", allowed_tools=frozenset({"read_file", "grep", "git_status"})),
            PlanTask("implement", "write", depends_on=("inspect",), allowed_tools=frozenset({"write_file", "edit_file"})),
            PlanTask("verify", "exec", depends_on=("implement",), allowed_tools=frozenset({"bash", "git_diff"})),
            PlanTask("summarize", "readonly", depends_on=("verify",)),
        )
    elif name == "parallel_inspect":
        count = max(1, min(16, int(task_count)))
        scans = tuple(
            PlanTask(f"inspect-{index}", "readonly", allowed_tools=frozenset({"read_file", "grep", "git_status"}))
            for index in range(1, count + 1)
        )
        tasks = scans + (
            PlanTask("merge", "readonly", depends_on=tuple(task.id for task in scans)),
            PlanTask("implement", "write", depends_on=("merge",), allowed_tools=frozenset({"write_file", "edit_file"})),
            PlanTask("verify", "exec", depends_on=("implement",), allowed_tools=frozenset({"bash", "git_diff"})),
            PlanTask("summarize", "readonly", depends_on=("verify",)),
        )
    else:
        raise GraphValidationError(f"未知固定模板: {name}")
    return DAGPlan(name, tasks)


__all__ = [
    "DAGPlan",
    "DAGResult",
    "GraphEdge",
    "GraphNode",
    "GraphValidationError",
    "NodeResult",
    "PlanTask",
    "StateGraph",
    "build_coding_workflow",
    "execute_dag",
    "fixed_plan",
]
