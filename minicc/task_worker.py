"""Detached task worker: run one task in its own process, persist to the store.

Daemonization step 2 (``MINICC_TASK_EXECUTOR=process``): the web server spawns
this module as a subprocess per task. The worker executes the agent loop and
writes progress snapshots into the shared SQLite ``TaskStore``, so the task
outlives the web process that submitted it. Cancellation travels through a
flag file instead of an in-memory event.

Test hook: setting ``MINICC_FAKE_PROVIDER=1`` replaces the model provider with
a deterministic in-process fake (used by the automated tests only).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .config import TRUTHY

from .agent.loop import AgentCancelled
from .task_store import TaskStore
from .task_contract import TASK_SCHEMA_VERSION, TaskRequest, TaskResult
from .llm.usage import add_usage_totals

WORKER_VERSION = 2
CANCEL_POLL_SECONDS = 1.0
STREAM_BOUND = 16_000
EVENTS_BOUND = 200
FLUSH_INTERVAL = 0.2
HEARTBEAT_INTERVAL = 5.0


def _install_fake_provider() -> None:
    """Test-only deterministic provider (never contacts the network)."""
    os.environ["MINICC_FAKE_PROVIDER"] = "1"


def _config_from_json(raw: str | None) -> Any:
    """Build a service config. Real deployments fall back to load_config()."""
    if not raw:
        from .config import load_config

        return load_config()
    data = json.loads(raw)
    return SimpleNamespace(**data)


def _config_from_file(path: str | None) -> Any | None:
    if not path:
        return None
    file_path = Path(path)
    raw = file_path.read_text(encoding="utf-8")
    if os.getenv("MINICC_KEEP_WORKER_CONFIG", "").strip().lower() not in TRUTHY:
        try:
            file_path.unlink(missing_ok=True)
        except OSError:
            pass
    return _config_from_json(raw)


def _snapshot(
    task_id: str,
    *,
    workspace: Path,
    status: str,
    phase: str,
    prompt: str,
    stream_text: str,
    events: list[dict[str, Any]],
    usage: dict[str, Any] | None,
    answer: str,
    error: str,
    allow_changes: bool,
    allow_network: bool,
    permission_mode: str,
    session_id: str,
    stream_length: int | None = None,
    created_at: float | None = None,
    lease_owner: str = "",
) -> dict[str, Any]:
    created_at = created_at or time.time()
    return {
        "schema_version": TASK_SCHEMA_VERSION,
        "task_id": task_id,
        "session_id": session_id,
        "created_at_epoch": created_at,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(created_at)),
        "workspace_path": str(workspace),
        "status": status,
        "phase": phase,
        "prompt": prompt,
        "preview": prompt[:120],
        "stream_text": stream_text[-STREAM_BOUND:],
        "stream_length": len(stream_text) if stream_length is None else stream_length,
        "events": events[-EVENTS_BOUND:],
        "usage": usage or {},
        "result": {"answer": answer} if answer else None,
        "error": error,
        "allow_changes": allow_changes,
        "allow_network": allow_network,
        "permission_mode": permission_mode,
        "worker_version": WORKER_VERSION,
        "worker_pid": os.getpid(),
        "lease_owner": lease_owner,
        "heartbeat_at_epoch": time.time(),
    }


def run_worker(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).expanduser().resolve()
    store = TaskStore(Path(args.store_path)) if args.store_path else TaskStore(workspace / ".minicc" / "tasks.sqlite3")
    lease_owner = getattr(args, "lease_owner", None) or uuid.uuid4().hex
    if not store.claim_lease(args.task_id, lease_owner, pid=os.getpid()):
        return 2
    try:
        return _run_owned_worker(args, workspace, store, lease_owner)
    finally:
        # Includes malformed request/config files and service startup errors.
        store.release_lease(args.task_id, lease_owner)


def _run_owned_worker(args: argparse.Namespace, workspace: Path, store: TaskStore, lease_owner: str) -> int:
    cancel_path = Path(args.cancel_file) if args.cancel_file else None
    if args.fake_provider:
        _install_fake_provider()

    service_kwargs: dict[str, Any] = {}
    config = _config_from_file(getattr(args, "config_file", None))
    if config is None:
        config = _config_from_json(args.config_json)
    config = SimpleNamespace(**{**vars(config), "task_worker_runtime": True, "auto_resume_on_start": False})
    from .web import AgentService

    cancel_event = threading.Event()
    stop_event = threading.Event()

    def _watch_cancel() -> None:
        while not stop_event.is_set() and not cancel_event.is_set():
            if cancel_path is not None and cancel_path.is_file():
                cancel_event.set()
                return
            stop_event.wait(CANCEL_POLL_SECONDS)

    state: dict[str, Any] = {"status": "running", "phase": "planning", "stream": "", "stream_length": 0, "events": [], "usage": None, "answer": "", "error": "", "result": None}
    state_lock = threading.RLock()
    flush_lock = threading.Lock()
    created_at = time.time()
    dirty = threading.Event()
    initial_snapshot = store.get(args.task_id) or {}
    created_at = float(initial_snapshot.get("created_at_epoch") or created_at)

    request_file = getattr(args, "request_file", None)
    if request_file:
        request_path = Path(request_file)
        request = TaskRequest.from_payload(json.loads(request_path.read_text(encoding="utf-8")))
        request_path.unlink(missing_ok=True)
    else:
        request = TaskRequest.from_payload({
            "task_id": args.task_id,
            "message": args.message, "session_id": args.session_id, "workspace_path": str(workspace),
            "allow_changes": bool(args.allow_changes), "allow_network": bool(args.allow_network),
            "permission_mode": args.permission_mode, "reasoning_effort": args.reasoning_effort,
        })

    def _flush() -> None:
        # A separate writer lock orders snapshots without holding state_lock
        # across SQLite IO; streaming callbacks remain independent of disk.
        with flush_lock:
            with state_lock:
                snapshot = _snapshot(
                    args.task_id,
                    workspace=workspace,
                    status=state["status"],
                    phase=state["phase"],
                    prompt=request.message,
                    stream_text=state["stream"],
                    events=state["events"],
                    usage=state["usage"],
                    answer=state["answer"],
                    error=state["error"],
                    allow_changes=request.allow_changes,
                    allow_network=request.allow_network,
                    permission_mode=request.permission_mode,
                    session_id=request.session_id,
                    stream_length=state["stream_length"], created_at=created_at, lease_owner=lease_owner,
                )
                snapshot["reasoning_effort"] = request.reasoning_effort
                snapshot["task_kind"] = request.task_kind
                if state["result"] is not None:
                    snapshot["result"] = dict(state["result"])
                snapshot["context"] = dict(state.get("context") or {})
                snapshot["compaction_events"] = list(state.get("compaction_events") or [])
                snapshot["compaction_count"] = int(state.get("compaction_count") or 0)
                dirty.clear()
            if not store.upsert({**initial_snapshot, **snapshot}, lease_owner=lease_owner):
                cancel_event.set()
                raise AgentCancelled("Worker execution lease was lost")

    def _background_flush() -> None:
        while not stop_event.wait(FLUSH_INTERVAL):
            if dirty.is_set():
                try:
                    _flush()
                except Exception:
                    # A transient database lock must not kill the heartbeat.
                    # Final persistence is synchronous and still propagates.
                    dirty.set()

    def _heartbeat() -> None:
        # Model requests and snapshot serialization never delay lease renewal.
        while not stop_event.wait(HEARTBEAT_INTERVAL):
            try:
                if not store.heartbeat_lease(args.task_id, lease_owner, pid=os.getpid()):
                    cancel_event.set()
                    return
                dirty.set()
            except Exception:
                # A transient SQLite lock gets another attempt; snapshot
                # fencing still prevents writes once the lease expires.
                continue

    def on_event(event: dict[str, Any]) -> None:
        with state_lock:
            phase = str(event.get("phase") or "")
            if event.get("kind") in {"trace", "state", "verification"} and phase:
                state["phase"] = phase
            candidate = dict(event)
            candidate.setdefault("event_id", f"evt-{uuid.uuid4().hex[:16]}")
            candidate.setdefault("item_id", f"item-{uuid.uuid4().hex[:16]}")
            state["events"] = (state["events"] + [candidate])[-EVENTS_BOUND:]
            dirty.set()

    def on_stream(delta: str) -> None:
        with state_lock:
            state["stream"] = (state["stream"] + delta)[-STREAM_BOUND:]
            state["stream_length"] += len(delta)
            dirty.set()

    def on_usage(usage: dict[str, Any]) -> None:
        with state_lock:
            if state["usage"] is None:
                state["usage"] = {}
            add_usage_totals(state["usage"], usage)
            dirty.set()

    def on_context(context: dict[str, Any]) -> None:
        with state_lock:
            state["context"] = dict(context)
            dirty.set()

    def on_compaction(event: dict[str, Any]) -> None:
        with state_lock:
            state["compaction_events"] = (state.get("compaction_events", []) + [dict(event)])[-64:]
            state["compaction_count"] = int(state.get("compaction_count") or 0) + 1
            dirty.set()

    service = AgentService(workspace, config, task_store=store, **service_kwargs)
    flusher = threading.Thread(target=_background_flush, daemon=True, name="worker-state-flush")
    watcher = threading.Thread(target=_watch_cancel, daemon=True, name="worker-cancel-watch")
    heartbeat = threading.Thread(target=_heartbeat, daemon=True, name="worker-heartbeat")
    try:
        _flush()
        watcher.start()
        flusher.start()
        heartbeat.start()
        result = service._chat_locked(
            request.to_payload(),
            workspace=workspace,
            on_event=on_event,
            on_stream=on_stream,
            on_usage=on_usage,
            on_context=on_context,
            on_compaction=on_compaction,
            cancel_event=cancel_event,
        )
        result = TaskResult.from_payload(result).to_payload()
        with state_lock:
            cancelled = bool(result.get("cancelled"))
            state["status"] = "cancelled" if cancelled else "completed"
            state["answer"] = str(result.get("answer") or "")
            state["result"] = dict(result)
            # A cancelled task may still carry an explanatory error string;
            # the cancelled status must win over it.
            if result.get("error") and not cancelled:
                state["status"] = "failed"
                state["error"] = str(result["error"])[:500]
            state["usage"] = dict(result.get("tokens_used") or {})
        _flush()
        return 0
    except AgentCancelled:
        state["status"] = "cancelled"
        state["error"] = "任务已取消"
        _flush()
        return 0
    except BaseException as exc:  # noqa: BLE001 - the worker owns its failure record
        state["status"] = "failed"
        state["error"] = f"{type(exc).__name__}: {exc}"[:500]
        _flush()
        return 1
    finally:
        stop_event.set()
        for thread in (flusher, watcher, heartbeat):
            if thread.ident is not None:
                thread.join(timeout=2)
        service.shutdown()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="minicc-task-worker", description="Run one minicc task in a detached process")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--session-id", default="web-latest")
    parser.add_argument("--message", required=True)
    parser.add_argument("--store-path", default=None, help="SQLite path; defaults to <workspace>/.minicc/tasks.sqlite3")
    parser.add_argument("--cancel-file", default=None, help="Poll this file; its creation cancels the task")
    parser.add_argument("--config-json", default=None, help="Inline service config (tests only); defaults to load_config()")
    parser.add_argument("--config-file", default=None, help="Path to a 0600 JSON config written by the web worker launcher")
    parser.add_argument("--request-file", default=None, help="Versioned task request including attachments and recovery context")
    parser.add_argument("--lease-owner", default=None, help="Execution lease reserved by the launcher")
    parser.add_argument("--allow-changes", action="store_true")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--permission-mode", default="default")
    parser.add_argument("--reasoning-effort", default="high")
    parser.add_argument("--fake-provider", action="store_true", help="Test-only deterministic provider")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run_worker(args)


if __name__ == "__main__":
    raise SystemExit(main())
