"""Serializable runtime state, trace events, and execution budgets.

The model remains non-deterministic, but the runtime state is deliberately
boring: it records what happened, what budget remains, and why execution
stopped.  These objects are safe to persist in a task snapshot.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


class BudgetExceeded(RuntimeError):
    """A bounded runtime budget no longer permits another operation."""


@dataclass
class Budget:
    """Bound turns, tokens, tool calls, retries, and wall-clock time."""

    max_turns: int | None = None
    max_tokens: int | None = None
    max_tool_calls: int | None = None
    max_duration_seconds: float | None = None
    max_retries: int | None = None
    started_monotonic: float = field(default_factory=time.monotonic, repr=False)
    turns: int = 0
    tokens: int = 0
    tool_calls: int = 0
    retries: int = 0

    def elapsed_seconds(self) -> float:
        return max(0.0, time.monotonic() - self.started_monotonic)

    def check(self) -> None:
        limits = (
            (self.max_turns, self.turns, "最大模型轮次"),
            (self.max_tokens, self.tokens, "最大 token 预算"),
            (self.max_tool_calls, self.tool_calls, "最大工具调用数"),
            (self.max_retries, self.retries, "最大重试次数"),
        )
        for maximum, current, label in limits:
            if maximum is not None and current > maximum:
                raise BudgetExceeded(f"{label}已用尽 ({current}/{maximum})")
        if self.max_duration_seconds is not None and self.elapsed_seconds() > self.max_duration_seconds:
            raise BudgetExceeded(
                f"最大执行时间已用尽 ({self.elapsed_seconds():.1f}s/{self.max_duration_seconds:.1f}s)"
            )

    def record_turn(self) -> None:
        self.turns += 1
        self.check()

    def record_usage(self, usage: dict[str, Any]) -> None:
        value = usage.get("total_tokens")
        if isinstance(value, (int, float)):
            self.tokens += int(value)
        self.check()

    def record_tool_call(self, count: int = 1) -> None:
        self.tool_calls += max(0, int(count))
        self.check()

    def record_retry(self) -> None:
        self.retries += 1
        self.check()

    def snapshot(self) -> dict[str, Any]:
        return {
            "max_turns": self.max_turns,
            "max_tokens": self.max_tokens,
            "max_tool_calls": self.max_tool_calls,
            "max_duration_seconds": self.max_duration_seconds,
            "max_retries": self.max_retries,
            "turns": self.turns,
            "tokens": self.tokens,
            "tool_calls": self.tool_calls,
            "retries": self.retries,
            "elapsed_seconds": round(self.elapsed_seconds(), 3),
        }


@dataclass(frozen=True)
class TraceEvent:
    """One auditable runtime event; never contains private chain-of-thought."""

    kind: str
    phase: str
    status: str
    summary: str
    node: str = ""
    code: str = ""
    detail: dict[str, Any] = field(default_factory=dict)
    duration_ms: float | None = None
    tokens: int | None = None
    tool: str | None = None
    attempt: int | None = None
    event_id: str = field(default_factory=lambda: f"trace-{uuid.uuid4().hex[:12]}")
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        output: dict[str, Any] = {
            "event_id": self.event_id,
            "created_at_epoch": self.created_at,
            "kind": self.kind,
            "phase": self.phase,
            "status": self.status,
            "summary": self.summary,
        }
        for key, value in (
            ("node", self.node),
            ("code", self.code),
            ("detail", self.detail),
            ("duration_ms", self.duration_ms),
            ("tokens", self.tokens),
            ("tool", self.tool),
            ("attempt", self.attempt),
        ):
            if value not in (None, "", {}):
                output[key] = value
        return output


@dataclass
class AgentState:
    """Mutable state shared by graph nodes and the existing agent loop."""

    task_id: str
    prompt: str
    workspace_path: str = ""
    workflow: str = "coding"
    node: str = "intake"
    phase: str = "intake"
    status: str = "running"
    budget: Budget = field(default_factory=Budget)
    outputs: dict[str, Any] = field(default_factory=dict)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    trace_events: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    def add_trace(self, event: dict[str, Any] | TraceEvent) -> dict[str, Any]:
        payload = event.to_dict() if isinstance(event, TraceEvent) else dict(event)
        self.trace_events.append(payload)
        if payload.get("phase"):
            self.phase = str(payload["phase"])
        if payload.get("node"):
            self.node = str(payload["node"])
        if payload.get("status") == "error":
            summary = str(payload.get("summary") or "")
            if summary and summary not in self.errors:
                self.errors.append(summary)
        return payload

    def transition(self, node: str, *, phase: str | None = None, status: str = "ok") -> dict[str, Any]:
        self.node = node
        self.phase = phase or node
        return self.add_trace(
            TraceEvent(
                kind="state",
                node=node,
                phase=self.phase,
                status=status,
                code="node_entered",
                summary=f"进入 {node} 节点",
            )
        )

    def add_evidence(self, evidence: dict[str, Any]) -> None:
        self.evidence.append(dict(evidence))

    def finish(self, status: str = "completed", error: str | None = None) -> None:
        self.status = status
        self.phase = status
        self.finished_at = time.time()
        if error:
            self.errors.append(error)

    def metrics(self) -> dict[str, Any]:
        end = self.finished_at or time.time()
        return {
            "workflow": self.workflow,
            "node": self.node,
            "phase": self.phase,
            "status": self.status,
            "duration_seconds": round(max(0.0, end - self.started_at), 3),
            "trace_events": len(self.trace_events),
            "evidence_count": len(self.evidence),
            "error_count": len(self.errors),
            "budget": self.budget.snapshot(),
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "prompt": self.prompt,
            "workspace_path": self.workspace_path,
            "workflow": self.workflow,
            "node": self.node,
            "phase": self.phase,
            "status": self.status,
            "outputs": dict(self.outputs),
            "evidence": list(self.evidence),
            "errors": list(self.errors),
            "trace_events": list(self.trace_events),
            "created_at_epoch": self.created_at,
            "started_at_epoch": self.started_at,
            "finished_at_epoch": self.finished_at,
            "metrics": self.metrics(),
        }


__all__ = ["AgentState", "Budget", "BudgetExceeded", "TraceEvent"]
