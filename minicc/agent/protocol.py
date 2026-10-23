"""Small runtime protocol primitives shared by the task and agent layers.

The public Codex CLI separates a thread, a turn, and the events emitted by a
turn.  This module keeps the same useful boundary without importing the CLI's
Rust implementation: events are append-only and replayable, task status
changes are validated, and cancellation can flow from a parent task to its
children.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from ..trace import trace_event


TASK_STATUSES = frozenset({"queued", "running", "completed", "failed", "cancelled", "interrupted"})
TERMINAL_TASK_STATUSES = frozenset({"completed", "failed", "cancelled", "interrupted"})
#: The statuses that mean "the task has not finished yet" - the third
#: question about a task's state, and the one that had no name.
#:
#: M8-T372: this fact was written out by hand in **twelve** places (seven in
#: the backend, five in the frontend) and every copy had to spell
#: ``{"queued", "running"}`` correctly.  The two other facts already had
#: names right here, and this one is *derivable* from them - so it is
#: derived, rather than written down a twelfth time.
ACTIVE_TASK_STATUSES = frozenset(TASK_STATUSES - TERMINAL_TASK_STATUSES)
#: The terminal statuses that mean "the task did not succeed" (failed or interrupted).
#: A task that was cancelled was not asked to succeed — it was asked to stop.
#: A task that failed or was interrupted was expected to succeed but did not.
TASK_UNSUCCESSFUL_STATUSES = frozenset({"failed", "interrupted"})
#: The event kinds whose ``phase`` field moves the task's phase.
#:
#: M8-T375: this question was asked by **both** executors - the thread
#: executor in ``task_manager`` and the detached process worker in
#: ``task_worker`` - and each of them wrote the three kinds out by hand.
#: The two copies are the same fact, and the roadmap even claimed they were
#: "one vocabulary" - a claim nothing enforced.  A task that runs in a
#: worker and the same task run in a thread could therefore show
#: **different phases** for the same event stream.
PHASE_CARRYING_EVENT_KINDS = frozenset({"trace", "state", "verification"})

# A terminal state is immutable.  In particular, a late provider callback may
# finish after cancellation, but it cannot turn the task green again.
ALLOWED_STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"running", "failed", "cancelled", "interrupted"}),
    "running": frozenset({"completed", "failed", "cancelled", "interrupted"}),
    "completed": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
    "interrupted": frozenset(),
}


class InvalidStatusTransition(RuntimeError):
    """Raised when a worker attempts to overwrite an already terminal task."""


class CancellationToken:
    """A threading.Event-compatible token with parent cancellation support."""

    def __init__(self, parent: "CancellationToken | None" = None) -> None:
        self._event = threading.Event()
        self._parent = parent
        self._lock = threading.RLock()
        self._reason = ""

    def is_set(self) -> bool:
        return self._event.is_set() or bool(self._parent and self._parent.is_set())

    def set(self) -> None:
        """Keep the Event API used by existing tools and tests."""
        self.cancel()

    def cancel(self, reason: str = "cancelled") -> None:
        with self._lock:
            if not self._event.is_set():
                self._reason = str(reason or "cancelled")
                self._event.set()

    @property
    def reason(self) -> str:
        with self._lock:
            if self._reason:
                return self._reason
        return self._parent.reason if self._parent else ""

    def wait(self, timeout: float | None = None) -> bool:
        """Wait while also observing a parent token without a second thread."""
        if self.is_set():
            return True
        if timeout is None:
            while not self.is_set():
                self._event.wait(0.1)
            return True
        deadline = time.monotonic() + max(0.0, timeout)
        while not self.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return self.is_set()
            self._event.wait(min(0.1, remaining))
        return True

    def child(self) -> "CancellationToken":
        return CancellationToken(parent=self)


@dataclass(frozen=True)
class RuntimeEvent:
    """One replayable task event, independent of the UI representation."""

    sequence: int
    task_id: str
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)
    thread_id: str = ""
    turn_id: int = 0
    event_id: str = field(default_factory=lambda: f"evt-{uuid.uuid4().hex[:16]}")
    # ``item_id`` is the stable identity of the user-visible item represented
    # by this event. It is deliberately separate from the transport event id:
    # one item may receive more than one transport update in richer clients.
    item_id: str = ""
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": "minicc.events.v1",
            "event_type": "task_event",
            "sequence": self.sequence,
            "event_id": self.event_id,
            "task_id": self.task_id,
            "thread_id": self.thread_id,
            "turn_id": self.turn_id,
            "item_id": self.item_id or self.event_id,
            "kind": self.kind,
            "payload": dict(self.payload),
            "created_at_epoch": self.created_at,
        }


class EventLog:
    """Bounded append-only log with condition-based replay for SSE clients."""

    def __init__(self, *, task_id: str, limit: int = 1024, start_sequence: int = 0) -> None:
        self.task_id = task_id
        self.limit = max(32, int(limit))
        self._next_sequence = max(0, int(start_sequence))
        self._events: deque[RuntimeEvent] = deque(maxlen=self.limit)
        self._event_ids: set[str] = set()
        self._condition = threading.Condition(threading.RLock())
        self._closed = False

    @property
    def cursor(self) -> int:
        with self._condition:
            return self._next_sequence

    @property
    def closed(self) -> bool:
        with self._condition:
            return self._closed

    @property
    def oldest_sequence(self) -> int:
        with self._condition:
            return self._events[0].sequence if self._events else self._next_sequence + 1

    def append(
        self,
        kind: str,
        payload: dict[str, Any] | None = None,
        *,
        thread_id: str = "",
        turn_id: int = 0,
        event_id: str | None = None,
        item_id: str | None = None,
    ) -> RuntimeEvent | None:
        with self._condition:
            if self._closed:
                return None
            if event_id and event_id in self._event_ids:
                return None
            self._next_sequence += 1
            resolved_event_id = str(event_id or f"evt-{uuid.uuid4().hex[:16]}")
            event = RuntimeEvent(
                sequence=self._next_sequence,
                task_id=self.task_id,
                kind=str(kind),
                payload=dict(payload or {}),
                thread_id=str(thread_id or ""),
                turn_id=max(0, int(turn_id or 0)),
                event_id=resolved_event_id,
                item_id=str(item_id or resolved_event_id),
            )
            if len(self._events) == self.limit:
                removed = self._events[0]
                self._event_ids.discard(removed.event_id)
            self._events.append(event)
            self._event_ids.add(event.event_id)
            self._condition.notify_all()
            return event

    def read(self, after: int = 0, timeout: float | None = None) -> tuple[list[RuntimeEvent], bool]:
        """Return events after a cursor and whether a replay gap exists."""
        cursor = max(0, int(after or 0))
        deadline = None if timeout is None else time.monotonic() + max(0.0, timeout)
        with self._condition:
            while not self._closed and self._next_sequence <= cursor:
                if deadline is None:
                    self._condition.wait()
                else:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    self._condition.wait(remaining)
            # A restored task has a cursor but no live in-memory replay
            # entries. Treat an older cursor as a gap so the transport sends
            # a fresh snapshot instead of silently dropping history.
            gap = (
                cursor < self._events[0].sequence - 1
                if self._events
                else cursor < self._next_sequence
            )
            return [event for event in self._events if event.sequence > cursor], gap

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._condition.notify_all()


def budget_exceeded_event(
    stage: str,
    error: object,
    tokens_used: dict[str, Any] | None,
    *,
    name: str,
    phase: str,
) -> dict[str, Any]:
    """The one witness for a budget trip: a named event with a three-key detail.

    Six folds used to hand-write this event - the CLI subagent fold, the web
    subagent fold, the batch merge, the planner DAG, the planner fold and the
    completion judge.  The detail answers three questions in one shape:
    which stage tripped, what the trip said, and what had been spent when it
    tripped.  A detail that forgets ``tokens_used`` still publishes - the
    event is on the timeline and the spend is simply unattributed, which is
    how a trip used to look like free work.
    """
    return trace_event(
        name=name,
        status="error",
        phase=phase,
        code="budget_exceeded",
        summary=str(error),
        detail={
            "stage": stage,
            "error": str(error),
            "tokens_used": dict(tokens_used or {}),
        },
    )


def validate_status_transition(current: str, target: str) -> None:
    current = str(current or "")
    target = str(target or "")
    if current not in TASK_STATUSES or target not in TASK_STATUSES:
        raise InvalidStatusTransition(f"未知任务状态: {current!r} -> {target!r}")
    if current == target:
        return
    if target not in ALLOWED_STATUS_TRANSITIONS[current]:
        raise InvalidStatusTransition(f"非法任务状态转移: {current} -> {target}")


__all__ = [
    "ACTIVE_TASK_STATUSES",
    "ALLOWED_STATUS_TRANSITIONS",
    "CancellationToken",
    "EventLog",
    "InvalidStatusTransition",
    "PHASE_CARRYING_EVENT_KINDS",
    "RuntimeEvent",
    "TASK_STATUSES",
    "TASK_UNSUCCESSFUL_STATUSES",
    "TERMINAL_TASK_STATUSES",
    "validate_status_transition",
]
