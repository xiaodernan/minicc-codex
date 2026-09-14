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
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .agent.loop import AgentCancelled
from .task_store import TaskStore

WORKER_VERSION = 1
CANCEL_POLL_SECONDS = 1.0
STREAM_BOUND = 16_000
EVENTS_BOUND = 200


def _fake_provider_state() -> dict[str, int]:
    return {"turn": 0}


def _install_fake_provider() -> None:
    """Test-only deterministic provider (never contacts the network)."""
    from minicc import web as web_module
    from minicc.llm.base import LLMResponse

    class FakeProvider:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def chat(self, messages, tools, on_delta=None):
            state = _fake_provider_state()
            state["turn"] += 1
            if tools is None:
                decision = json.dumps({
                    "status": "complete", "confidence": 0.9, "rationale": "worker fake",
                    "missing": [], "next_action": "", "evidence": ["worker"],
                }, ensure_ascii=False)
                return LLMResponse(content=decision)
            return LLMResponse(content="worker-fake-answer")

        async def close(self):
            return None

    web_module.OpenAICompatibleProvider = FakeProvider


def _config_from_json(raw: str | None) -> Any:
    """Build a service config. Real deployments fall back to load_config()."""
    if not raw:
        from .config import load_config

        return load_config()
    data = json.loads(raw)
    return SimpleNamespace(**data)


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
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "session_id": session_id,
        "created_at_epoch": time.time(),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "workspace_path": str(workspace),
        "status": status,
        "phase": phase,
        "prompt": prompt,
        "preview": prompt[:120],
        "stream_text": stream_text[-STREAM_BOUND:],
        "events": events[-EVENTS_BOUND:],
        "usage": usage or {},
        "result": {"answer": answer} if answer else None,
        "error": error,
        "allow_changes": allow_changes,
        "allow_network": allow_network,
        "permission_mode": permission_mode,
        "worker_version": WORKER_VERSION,
        "heartbeat_at_epoch": time.time(),
    }


def run_worker(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).expanduser().resolve()
    cancel_path = Path(args.cancel_file) if args.cancel_file else None
    if args.fake_provider:
        _install_fake_provider()

    store = TaskStore(Path(args.store_path)) if args.store_path else TaskStore(workspace / ".minicc" / "tasks.sqlite3")
    service_kwargs: dict[str, Any] = {}
    config = _config_from_json(args.config_json)
    from .web import AgentService

    cancel_event = threading.Event()

    def _watch_cancel() -> None:
        while not cancel_event.is_set():
            if cancel_path is not None and cancel_path.is_file():
                cancel_event.set()
                return
            time.sleep(CANCEL_POLL_SECONDS)

    watcher = threading.Thread(target=_watch_cancel, daemon=True, name="worker-cancel-watch")
    watcher.start()

    state: dict[str, Any] = {"status": "running", "phase": "planning", "stream": "", "events": [], "usage": None, "answer": "", "error": ""}

    def _flush() -> None:
        store.upsert(_snapshot(
            args.task_id,
            workspace=workspace,
            status=state["status"],
            phase=state["phase"],
            prompt=args.message,
            stream_text=state["stream"],
            events=state["events"],
            usage=state["usage"],
            answer=state["answer"],
            error=state["error"],
            allow_changes=bool(args.allow_changes),
            allow_network=bool(args.allow_network),
            permission_mode=args.permission_mode,
            session_id=args.session_id,
        ))

    def on_event(event: dict[str, Any]) -> None:
        phase = str(event.get("phase") or "")
        if event.get("kind") in {"trace", "state", "verification"} and phase:
            state["phase"] = phase
        state["events"] = (state["events"] + [event])[-EVENTS_BOUND:]
        _flush()

    def on_stream(delta: str) -> None:
        state["stream"] = (state["stream"] + delta)[-STREAM_BOUND:]
        _flush()

    def on_usage(usage: dict[str, Any]) -> None:
        state["usage"] = dict(usage)
        _flush()

    service = AgentService(workspace, config, **service_kwargs)
    try:
        result = service._chat_locked(
            {
                "message": args.message,
                "session_id": args.session_id,
                "allow_changes": bool(args.allow_changes),
                "allow_network": bool(args.allow_network),
                "permission_mode": args.permission_mode,
                "reasoning_effort": args.reasoning_effort,
                "workspace_path": str(workspace),
            },
            workspace=workspace,
            on_event=on_event,
            on_stream=on_stream,
            on_usage=on_usage,
            cancel_event=cancel_event,
        )
        cancelled = bool(result.get("cancelled"))
        state["status"] = "cancelled" if cancelled else "completed"
        state["answer"] = str(result.get("answer") or "")[:8000]
        # A cancelled task may still carry an explanatory error string; the
        # cancelled status must win over it.
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
        service.shutdown()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="minicc-task-worker", description="Run one minicc task in a detached process")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--session-id", default="web-latest")
    parser.add_argument("--message", required=True)
    parser.add_argument("--store-path", default=None, help="SQLite path; defaults to <workspace>/.minicc/tasks.sqlite3")
    parser.add_argument("--cancel-file", default=None, help="Poll this file; its creation cancels the task")
    parser.add_argument("--config-json", default=None, help="Inline service config (tests); defaults to load_config()")
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
