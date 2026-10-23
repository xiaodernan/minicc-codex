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

from .config import (
    DEFAULT_TASK_EVENT_LIMIT,
    DEFAULT_TASK_STREAM_LIMIT,
    TRUTHY,
)

from .agent.loop import AgentCancelled
from .agent.protocol import PHASE_CARRYING_EVENT_KINDS
from .logging_setup import get_logger, log_task_event, register_secret
from .task_store import TaskStore
from .task_contract import (
    ALLOW_CHANGES_FLAG,
    ALLOW_NETWORK_FLAG,
    CANCEL_FILE_FLAG,
    CONFIG_FILE_FLAG,
    CONFIG_JSON_FLAG,
    CONFIG_STDIN_FLAG,
    FAKE_PROVIDER_FLAG,
    LEASE_OWNER_FLAG,
    MESSAGE_FLAG,
    MODEL_FLAG,
    PERMISSION_MODE_FLAG,
    REASONING_EFFORT_FLAG,
    REQUEST_FILE_FLAG,
    SESSION_ID_FLAG,
    STORE_PATH_FLAG,
    TASK_ID_FLAG,
    TASK_SCHEMA_VERSION,
    TaskRequest,
    TaskResult,
    WORKSPACE_FLAG,
)
from .llm.usage import add_usage_totals

LOG = get_logger("worker")
WORKER_VERSION = 2
CANCEL_POLL_SECONDS = 1.0
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


def _config_from_stdin() -> Any | None:
    """M3-T6: read the service config (incl. api_key) from stdin, never disk."""
    try:
        raw = sys.stdin.read()
    except (OSError, ValueError):
        return None
    if not raw.strip():
        return None
    return _config_from_json(raw)


#: The same floors the thread face applies to a TaskRecord; the door keeps both
#: faces answering with the same count, so a drift here cannot stay silent.
_EVENT_WINDOW_FLOOR = 32
_STREAM_WINDOW_FLOOR = 512


def _positive_int(raw: Any, floor: int) -> int:
    try:
        return max(floor, int(raw))
    except (TypeError, ValueError):
        return floor


def _window_from(config: Any) -> tuple[int, int]:
    """The task window this worker must apply, from the config it was handed.

    M8-T268: ``EVENTS_BOUND``/``STREAM_BOUND`` were module constants, so
    ``MINICC_TASK_EVENT_LIMIT`` - published in README and minicc.config.example
    and honored by the thread face - meant 768 there and 200 here, and a row
    written here declared neither the window nor the drops.
    """
    return (
        _positive_int(getattr(config, "task_event_limit", DEFAULT_TASK_EVENT_LIMIT), _EVENT_WINDOW_FLOOR),
        _positive_int(getattr(config, "task_stream_limit", DEFAULT_TASK_STREAM_LIMIT), _STREAM_WINDOW_FLOOR),
    )


def append_bounded(items: list[dict[str, Any]], item: dict[str, Any], limit: int) -> int:
    """Append ``item`` to ``items``, keep the newest ``limit``, return what fell out.

    The live callback and the snapshot share this one trim so the number of
    evicted events has a single producer.
    """
    items.append(item)
    overflow = len(items) - max(0, int(limit))
    if overflow <= 0:
        return 0
    del items[:overflow]
    return overflow


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
    model: str = "",
    stream_length: int | None = None,
    event_limit: int = DEFAULT_TASK_EVENT_LIMIT,
    stream_limit: int = DEFAULT_TASK_STREAM_LIMIT,
    events_truncated: int = 0,
    created_at: float | None = None,
    lease_owner: str = "",
) -> dict[str, Any]:
    created_at = created_at or time.time()
    event_limit = _positive_int(event_limit, _EVENT_WINDOW_FLOOR)
    stream_limit = _positive_int(stream_limit, _STREAM_WINDOW_FLOOR)
    retained = events[-event_limit:]
    dropped_here = max(0, len(events) - len(retained))
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
        "stream_text": stream_text[-stream_limit:],
        "stream_length": len(stream_text) if stream_length is None else stream_length,
        "events": retained,
        "event_limit": event_limit,
        "stream_limit": stream_limit,
        "events_truncated": _positive_int(events_truncated, 0) + dropped_here,
        "usage": usage or {},
        "result": {"answer": answer} if answer else None,
        "error": error,
        "allow_changes": allow_changes,
        "allow_network": allow_network,
        "permission_mode": permission_mode,
        "model": model,
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
    config = None
    if getattr(args, "config_stdin", False):
        config = _config_from_stdin()
    if config is None:
        config = _config_from_file(getattr(args, "config_file", None))
    if config is None:
        config = _config_from_json(args.config_json)
    config = SimpleNamespace(**{**vars(config), "task_worker_runtime": True, "auto_resume_on_start": False})
    event_limit, stream_limit = _window_from(config)
    # The worker gets its own process, so it registers the credential to mask
    # in its own log handlers; the config never reaches the log otherwise.
    register_secret(getattr(config, "api_key", ""))
    from .web import AgentService

    cancel_event = threading.Event()
    stop_event = threading.Event()

    def _watch_cancel() -> None:
        while not stop_event.is_set() and not cancel_event.is_set():
            if cancel_path is not None and cancel_path.is_file():
                cancel_event.set()
                return
            stop_event.wait(CANCEL_POLL_SECONDS)

    state: dict[str, Any] = {"status": "running", "phase": "planning", "stream": "", "stream_length": 0, "events": [], "events_truncated": 0, "usage": None, "answer": "", "error": "", "result": None}
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
            "model": args.model,
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
                    model=request.model,
                    stream_length=state["stream_length"], created_at=created_at, lease_owner=lease_owner,
                    event_limit=event_limit,
                    stream_limit=stream_limit,
                    events_truncated=state["events_truncated"],
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

    def _final_flush(fallback_status: str) -> None:
        """Best-effort terminal snapshot: a failed final write must not escalate.

        The background flusher keeps the running-state record on disk; if this
        terminal write cannot land (lease lost -> fenced; transient SQLite
        lock), re-raising would replace the clean cancelled/failed/complete
        exit with an unhandled traceback while the record cannot improve
        anyway. Log and move on — the exit code and the log line still tell
        the truth.
        """
        try:
            _flush()
        except Exception as exc:
            LOG.error(
                "final_flush_failed task_id=%s fallback_status=%s error=%s",
                args.task_id, fallback_status, exc,
            )

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
        log_task_event(event, task_id=args.task_id)
        with state_lock:
            phase = str(event.get("phase") or "")
            # M8-T375: the event kinds that carry a phase have one home
            # (protocol.py), shared with the thread executor - so the same
            # event stream moves the phase the same way whichever executor
            # ran the task.
            if event.get("kind") in PHASE_CARRYING_EVENT_KINDS and phase:
                state["phase"] = phase
            candidate = dict(event)
            candidate.setdefault("event_id", f"evt-{uuid.uuid4().hex[:16]}")
            candidate.setdefault("item_id", f"item-{uuid.uuid4().hex[:16]}")
            state["events_truncated"] += append_bounded(state["events"], candidate, event_limit)
            dirty.set()

    def on_stream(delta: str) -> None:
        with state_lock:
            state["stream"] = (state["stream"] + delta)[-stream_limit:]
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
    LOG.info(
        "task_started task_id=%s pid=%s workspace=%s mode=%s changes=%s network=%s",
        args.task_id,
        os.getpid(),
        workspace,
        request.permission_mode,
        request.allow_changes,
        request.allow_network,
    )
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
        _final_flush("completed")
        return 0
    except AgentCancelled:
        state["status"] = "cancelled"
        state["error"] = "任务已取消"
        _final_flush("cancelled")
        return 0
    except BaseException as exc:  # noqa: BLE001 - the worker owns its failure record
        LOG.error(
            "worker_failed task_id=%s error=%s", args.task_id, exc, exc_info=exc
        )
        state["status"] = "failed"
        state["error"] = f"{type(exc).__name__}: {exc}"[:500]
        _final_flush("failed")
        return 1
    finally:
        LOG.info(
            "task_finished task_id=%s status=%s error=%s",
            args.task_id,
            state["status"],
            (state.get("error") or "-")[:200],
        )
        stop_event.set()
        for thread in (flusher, watcher, heartbeat):
            if thread.ident is not None:
                thread.join(timeout=2)
        service.shutdown()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="minicc-task-worker", description="Run one minicc task in a detached process")
    parser.add_argument(WORKSPACE_FLAG, required=True)
    parser.add_argument(TASK_ID_FLAG, required=True)
    parser.add_argument(SESSION_ID_FLAG, default="web-latest")
    parser.add_argument(MESSAGE_FLAG, required=True)
    parser.add_argument(STORE_PATH_FLAG, default=None, help="SQLite path; defaults to <workspace>/.minicc/tasks.sqlite3")
    parser.add_argument(CANCEL_FILE_FLAG, default=None, help="Poll this file; its creation cancels the task")
    parser.add_argument(CONFIG_JSON_FLAG, default=None, help="Inline service config (tests only); defaults to load_config()")
    parser.add_argument(CONFIG_FILE_FLAG, default=None, help="Path to a 0600 JSON config written by the web worker launcher")
    parser.add_argument(CONFIG_STDIN_FLAG, action="store_true", help="Read the service config JSON from stdin (M3-T6: keeps api_key off disk)")
    parser.add_argument(REQUEST_FILE_FLAG, default=None, help="Versioned task request including attachments and recovery context")
    parser.add_argument(LEASE_OWNER_FLAG, default=None, help="Execution lease reserved by the launcher")
    parser.add_argument(ALLOW_CHANGES_FLAG, action="store_true")
    parser.add_argument(ALLOW_NETWORK_FLAG, action="store_true")
    parser.add_argument(PERMISSION_MODE_FLAG, default="default")
    parser.add_argument(REASONING_EFFORT_FLAG, default="high")
    parser.add_argument(MODEL_FLAG, default="")
    parser.add_argument(FAKE_PROVIDER_FLAG, action="store_true", help="Test-only deterministic provider")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run_worker(args)


if __name__ == "__main__":
    raise SystemExit(main())
