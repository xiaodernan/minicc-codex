"""Worker transport and recovery helpers, independent of HTTP and scheduling."""

from __future__ import annotations

import time
from typing import Any

from .task_store import TaskStore
from .task_contract import TaskResult


class WorkerDetached(Exception):
    """The web host is shutting down; execution remains owned by its worker."""


def has_live_worker(store: TaskStore, snapshot: dict[str, Any]) -> bool:
    lease = store.get_lease(str(snapshot.get("task_id") or ""))
    if lease:
        return float(lease.get("expires") or 0) > time.time()
    # Compatibility for a worker started by the previous application version.
    return bool(snapshot.get("worker_version")) and time.time() - float(snapshot.get("heartbeat_at_epoch") or 0) < 45


class WorkerSnapshotMirror:
    """Apply snapshots using absolute stream offsets and bounded event IDs."""

    def __init__(self, task: Any) -> None:
        self.task = task
        self.last_offset = task.stream_length
        self.last_usage: dict[str, Any] | None = None
        self.last_context: dict[str, Any] | None = None
        self.last_compactions = len(task.compaction_events)

    def apply(self, snapshot: dict[str, Any]) -> None:
        task = self.task
        phase = str(snapshot.get("phase") or "")
        if phase:
            task.set_phase(phase)
        window = str(snapshot.get("stream_text") or "")
        offset = int(snapshot.get("stream_length") or len(window))
        if offset > self.last_offset:
            start = max(0, offset - len(window))
            if self.last_offset < start:
                # The consumer missed more than one retained window: replace
                # its display snapshot and publish the resynchronization.
                with task.lock:
                    task.stream_text = window[-task.stream_limit:]
                    task.stream_length = offset
                    task.state_version += 1
                    task._publish_locked("stream_delta", {
                        "delta": "", "stream_text": task.stream_text,
                        "stream_length": offset, "reset": True, "phase": task.phase,
                    })
            else:
                task.append_stream(window[self.last_offset - start:])
            self.last_offset = offset
        usage = snapshot.get("usage") or snapshot.get("tokens_used")
        if isinstance(usage, dict) and usage and usage != self.last_usage:
            task.update_usage(usage, cumulative=True)
            self.last_usage = dict(usage)
        context = snapshot.get("context")
        if isinstance(context, dict) and context != self.last_context:
            task.update_context(context)
            self.last_context = dict(context)
        compactions = snapshot.get("compaction_events") or []
        compaction_count = int(snapshot.get("compaction_count") or len(compactions))
        window_start = max(0, compaction_count - len(compactions))
        for event in compactions[max(0, self.last_compactions - window_start):]:
            if isinstance(event, dict):
                task.add_compaction(event)
        self.last_compactions = max(self.last_compactions, compaction_count)
        for event in snapshot.get("events") or []:
            if isinstance(event, dict):
                task.add_event(event)
        task.worker_metadata.update({
            key: snapshot[key]
            for key in ("worker_version", "worker_pid", "lease_owner", "heartbeat_at_epoch")
            if key in snapshot
        })

    @staticmethod
    def result(snapshot: dict[str, Any]) -> dict[str, Any]:
        result = dict(snapshot.get("result") or {})
        return TaskResult.from_payload({
            **result,
            "answer": str(result.get("answer") or snapshot.get("stream_text") or ""),
            "error": str(snapshot.get("error") or result.get("error") or ("worker task was interrupted" if snapshot.get("status") == "interrupted" else "")),
            "cancelled": snapshot.get("status") == "cancelled",
            "tokens_used": dict(snapshot.get("usage") or snapshot.get("tokens_used") or {}),
        }).to_payload()
