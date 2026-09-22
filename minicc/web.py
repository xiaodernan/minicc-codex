"""Local Web UI bridge for the minicc agent.

The server intentionally stays small: static assets are served by the Python
stdlib and chat requests reuse the existing agent loop and tool registry.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import binascii
from collections import deque
import hashlib
import inspect
import json
import math
import mimetypes
import re
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
import dataclasses
import os
import sys
from dataclasses import dataclass, field
from types import SimpleNamespace
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

try:  # httpx ships with the OpenAI SDK dependency; keep the import guarded.
    import httpx
except ModuleNotFoundError:  # pragma: no cover - depends on the HTTP stack.
    httpx = None  # type: ignore[assignment]

from .agent.graph import DAGPlan, PlanTask, build_coding_workflow, execute_dag, fixed_plan
from .agent.completion import CompletionDecision, judge_completion
from .agent.loop import AgentCancelled, TurnResult, build_tool_feedback, chat_with_cancellation, run_agent
from .agent.orchestration import assess_complexity, build_auto_subtasks
from .agent.planner import (
    DEFAULT_ALLOWED_TOOLS,
    PLANNER_SYSTEM_PROMPT,
    PlanBuildResult,
    PlannerPolicy,
    build_plan,
    build_planner_prompt,
    parse_planner_response,
)
from .agent.repair import repair_scope
from .agent.retrieval import LocalEvidenceIndex, get_evidence_index
from .agent.subagent import build_task_tool_spec
from .webauth import (
    WebAuth,
    WebAuthError,
    cors_origin,
    is_loopback_host,
    load_or_create_token,
    token_store_path,
)
from .agent.router import StageRouter
from .agent.state import AgentState, Budget, BudgetExceeded
from .agent.protocol import (
    CancellationToken,
    EventLog,
    InvalidStatusTransition,
    validate_status_transition,
)
from .agent.rpc import RpcDispatcher
from .agent.verifier import Verifier, VerificationResult
from .agent.verification_plan import build_verification_plan, changed_paths_from_events
from .audit import AuthorizationDecision, authorize_tool, normalize_permission_mode
from .changes import ChangeError, ChangeInspector
from .commands import discover_commands, expand_slash_command
from .mentions import apply_mentions
from .permissions import load_permission_rules, match_permission_rule
from .config import (
    ConfigError,
    TRUTHY,
    home_dir,
    load_config,
    normalize_reasoning_effort,
)
from .allowlist import AllowlistError, add_session_rule, replace_session_rules, session_rules
from .cli_io import cli_out
from .hooks import HookRunner
from .llm.base import system_msg, user_msg
from .llm.anthropic_provider import AnthropicProvider
from .llm.fake import FakeProvider
from .llm.openai_provider import OpenAICompatibleProvider
from .logging_setup import (
    configure_logging,
    get_logger,
    log_task_event,
    quiet_loop_teardown,
    register_secret,
)
from .snapshots import SnapshotError, SnapshotJournal, exists as workspace_snapshot_exists, restore as restore_workspace_snapshot
from .llm.usage import add_usage_totals, cache_summary
from .mcp import McpError, McpManager
from .prompt import build_system_prompt
from .sandbox import SandboxRunner
from .session import SessionError, SessionStore, list_sessions
from .tools import Editor, ToolCall, ToolResult, build_registry
from .tools.editor import AUDIT_LEVELS, audit_level
from .tools.registry import redact_text
from .task_store import TaskStore
from .worktree import WorktreeError, WorktreeManager
from .webserver import MiniccHTTPServer, MiniccRequestHandler  # noqa: F401 - re-export
from .workspaces import WorkspaceCatalog, resolve_workspace_path

from .task_manager import (  # noqa: F401 - re-export for tests and AgentService
    CHANGE_INTENT_MARKERS,
    COMPLETION_WRITE_TOOLS,
    DEFAULT_TASK_COMPACTION_LIMIT,
    DEFAULT_TASK_EVENT_LIMIT,
    DEFAULT_TASK_QUEUE_LIMIT,
    DEFAULT_TASK_STREAM_LIMIT,
    DEFAULT_TASK_USAGE_LIMIT,
    MAX_ATTACHMENT_BYTES,
    MAX_ATTACHMENT_TOTAL_BYTES,
    MAX_ATTACHMENTS,
    MAX_BATCH_TASKS,
    NO_CHANGE_MARKERS,
    READONLY_PLAN_KINDS,
    READONLY_PLAN_TOOLS,
    TASK_SHUTDOWN_GRACE_SECONDS,
    TASK_STREAM_INTERVAL,
    TERMINAL_TASK_STATUSES,
    TaskManager,
    TaskRecord,
    _attachment_content_parts,
    _child_result_digest,
    _completion_followup,
    _completion_guard_message,
    _completion_review_event,
    _event_fingerprint,
    _is_bounded_readonly_plan,
    _iso,
    _merge_turn_results,
    _multimodal_content,
    _normalize_attachments,
    _path_key,
    _resolve_task_permissions,
)

# M3-T8: bounded RPC thread cache + thread_id validation.
_RPC_THREADS_MAX = 512
_THREAD_ID_MAX_LEN = 256
LOG = get_logger("service")

# M7-T3: interactive Web approvals wait at most this long, then auto-deny.
APPROVAL_TIMEOUT_SECONDS = 60.0


@dataclass
class _ApprovalGroup:
    """One pending approval; identical in-flight calls merge into it."""

    request_id: str
    merge_key: str
    waiters: list[threading.Event] = field(default_factory=list)
    decision: str = "deny"
    resolved: bool = False
    timed_out: bool = False


def _validate_thread_id(raw: Any) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("thread_id 不能为空")
    thread_id = raw.strip()
    if len(thread_id) > _THREAD_ID_MAX_LEN:
        raise ValueError(f"thread_id 超过长度上限 ({_THREAD_ID_MAX_LEN})")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in thread_id):
        raise ValueError("thread_id 含非法控制字符")
    return thread_id


def _audit_level_filter(
    *,
    levels: list[str] | None = None,
    min_level: str | None = None,
) -> set[str] | None:
    """Resolve ``/api/audit`` level filters into an allow-list (``None`` = all).

    Unknown level names raise ``ValueError`` (a 400 with ``invalid_request``),
    never a silent empty result that would look like "no findings".
    """
    allowed: set[str] | None = None
    if levels:
        allowed = set()
        for raw in levels:
            name = str(raw).strip().casefold()
            if name not in AUDIT_LEVELS:
                raise ValueError(f"未知审计级别: {raw}（可选：{', '.join(AUDIT_LEVELS)}）")
            allowed.add(name)
    if min_level:
        name = str(min_level).strip().casefold()
        if name not in AUDIT_LEVELS:
            raise ValueError(f"未知审计级别: {min_level}（可选：{', '.join(AUDIT_LEVELS)}）")
        floor = set(AUDIT_LEVELS[AUDIT_LEVELS.index(name):])
        allowed = floor if allowed is None else allowed & floor
    return allowed


class AgentService:
    """Bridge HTTP requests to isolated agent runs and background tasks."""

    def __init__(self, workspace: Path, config: Any, *, task_store: "TaskStore | None" = None) -> None:
        self.workspace = workspace
        self.config = config
        # M8-T5: the provider key must never reach a log line, and it does not
        # always match a known secret shape, so register the exact value.
        register_secret(getattr(config, "api_key", ""))
        self.system_prompt = build_system_prompt(workspace)
        self.workspace_catalog = WorkspaceCatalog()
        self.workspace_catalog.remember(workspace)
        self._workspace_guard = threading.RLock()
        self.sandbox = SandboxRunner(config.sandbox_mode, config.sandbox_image)
        self.worktrees = WorktreeManager(workspace)
        self._mcp_guard = threading.RLock()
        self._mcp_by_workspace: dict[str, McpManager | None] = {}
        self.mcp: McpManager | None = None
        self.mcp_error = ""
        self._set_current_mcp(workspace)
        self._session_guard = threading.Lock()
        self._session_locks: dict[str, threading.Lock] = {}
        # M7-T3: request_id -> pending approval group; merge_key -> group id.
        self._approval_guard = threading.Lock()
        self._approval_groups: dict[str, _ApprovalGroup] = {}
        self._approval_by_key: dict[str, str] = {}
        self.tasks = TaskManager(self, store=task_store or TaskStore(home_dir() / "tasks.sqlite3"))
        self._rpc_thread_guard = threading.RLock()
        self._rpc_threads: dict[str, dict[str, Any]] = {}
        self.rpc_dispatcher = RpcDispatcher(
            {
                "thread/start": self._rpc_thread_start,
                "thread/read": self._rpc_thread_read,
                "turn/start": self._rpc_turn_start,
                "turn/read": self._rpc_turn_read,
                "turn/interrupt": self._rpc_turn_interrupt,
                # M4-3: read-only inspection surface (10 methods total, each
                # with its own test in tests/test_http_surface.py).
                "workspace/read": self._rpc_workspace_read,
                "models/list": self._rpc_models_list,
                "changes/read": self._rpc_changes_read,
                "sessions/list": self._rpc_sessions_list,
                "permissions/read": self._rpc_permissions_read,
            }
        )
        self.rpc = self.rpc_dispatcher

    def _mcp_for_workspace(self, workspace: Path) -> McpManager | None:
        key = _path_key(workspace)
        with self._mcp_guard:
            if key in self._mcp_by_workspace:
                return self._mcp_by_workspace[key]
            try:
                manager: McpManager | None = McpManager(workspace)
            except McpError:
                manager = None
            self._mcp_by_workspace[key] = manager
            return manager

    def _set_current_mcp(self, workspace: Path) -> None:
        manager = self._mcp_for_workspace(workspace)
        self.mcp = manager
        self.mcp_error = "" if manager is not None else "MCP 配置不可用"

    def _session_lock(self, workspace: Path, session_id: str) -> threading.Lock:
        lock_key = f"{_path_key(workspace)}:{session_id}"
        with self._session_guard:
            return self._session_locks.setdefault(lock_key, threading.Lock())

    # ------------------------------------------------------------------
    # M7-T3: interactive Web approvals (approval_request frames over SSE)
    # ------------------------------------------------------------------

    @staticmethod
    def _approval_preview(tool: str, arguments: dict[str, Any]) -> str:
        raw = str((arguments or {}).get("command") or (arguments or {}).get("path") or "")
        if not raw:
            raw = json.dumps(arguments or {}, ensure_ascii=False, sort_keys=True)
        preview, _ = redact_text(raw)
        return preview.strip()[:400]

    def request_approval(
        self,
        *,
        session_id: str,
        task_id: str,
        tool: str,
        arguments: dict[str, Any],
        risk: str,
        reason: str,
        on_event: Any = None,
        cancel_event: "threading.Event | None" = None,
        timeout: float = APPROVAL_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        """Block the agent thread until the user (or the timeout) decides.

        Returns {decision: allow|always|deny, timed_out, cancelled, merged,
        request_id}. The request frame is emitted *before* waiting so the
        event stream is never blocked by an approval; the wait is sliced so
        task cancellation exits promptly. Identical in-flight calls (same
        session/tool/redacted preview) merge into one prompt.
        """
        preview = self._approval_preview(tool, arguments)
        merge_key = f"{session_id}|{tool}|{preview}"
        waiter = threading.Event()
        with self._approval_guard:
            existing = self._approval_groups.get(self._approval_by_key.get(merge_key, ""))
            merged = existing is not None and not existing.resolved
            if merged:
                group = existing
                group.waiters.append(waiter)
            else:
                group = _ApprovalGroup(request_id=uuid.uuid4().hex, merge_key=merge_key)
                group.waiters.append(waiter)
                self._approval_groups[group.request_id] = group
                self._approval_by_key[merge_key] = group.request_id
        if not merged and on_event is not None:
            on_event({
                "kind": "approval_request",
                "name": tool,
                "status": "pending",
                "phase": "permission",
                "code": "approval_requested",
                "summary": f"等待用户批准 {tool}：{reason}",
                "risk": risk,
                "request_id": group.request_id,
                "task_id": task_id,
                "tool": tool,
                "preview": preview,
                "reason": reason,
                "timeout_seconds": float(timeout),
            })
        deadline = time.monotonic() + max(0.0, float(timeout))
        while not group.resolved:
            if cancel_event is not None and cancel_event.is_set():
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            waiter.wait(min(remaining, 0.25))
        cancelled = cancel_event is not None and cancel_event.is_set()
        timed_out = not group.resolved and not cancelled
        with self._approval_guard:
            if group.resolved:
                decision, group_timed_out = group.decision, group.timed_out
            elif not merged:
                # The creator owns the prompt frame: it finalizes and removes
                # the group. A merged waiter that gives up only detaches
                # itself and must not clobber the pending prompt.
                decision, group_timed_out = "deny", timed_out
                group.resolved = True
                group.decision = decision
                group.timed_out = group_timed_out
                self._approval_groups.pop(group.request_id, None)
                if self._approval_by_key.get(group.merge_key) == group.request_id:
                    self._approval_by_key.pop(group.merge_key, None)
            else:
                decision, group_timed_out = "deny", timed_out
                if waiter in group.waiters:
                    group.waiters.remove(waiter)
        if not merged and on_event is not None:
            on_event({
                "kind": "approval_resolved",
                "name": tool,
                "status": "ok" if decision in {"allow", "always"} else "denied",
                "phase": "permission",
                "code": "approval_resolved",
                "summary": (
                    f"审批结果：{decision}"
                    + ("（超时自动拒绝）" if group_timed_out else "")
                    + ("（任务已取消）" if cancelled else "")
                ),
                "request_id": group.request_id,
                "task_id": task_id,
                "decision": decision,
                "timed_out": group_timed_out,
                "cancelled": cancelled,
            })
        return {
            "decision": decision,
            "timed_out": group_timed_out,
            "cancelled": cancelled,
            "merged": merged,
            "request_id": group.request_id,
        }

    def resolve_approval(self, request_id: str, decision: str) -> dict[str, Any]:
        """Apply a user decision to a pending approval (allow|always|deny)."""
        if decision not in {"allow", "always", "deny"}:
            raise ValueError("审批决定必须是 allow|always|deny")
        with self._approval_guard:
            group = self._approval_groups.get(str(request_id or "").strip())
            if group is None or group.resolved:
                return {"resolved": False, "request_id": str(request_id or "")}
            group.decision = decision
            group.resolved = True
            self._approval_groups.pop(group.request_id, None)
            if self._approval_by_key.get(group.merge_key) == group.request_id:
                self._approval_by_key.pop(group.merge_key, None)
            waiters = list(group.waiters)
        for event in waiters:
            event.set()
        return {"resolved": True, "request_id": group.request_id, "decision": decision}

    def _deny_all_approvals(self) -> None:
        with self._approval_guard:
            groups = list(self._approval_groups.values())
            for group in groups:
                if not group.resolved:
                    group.resolved = True
                    group.decision = "deny"
            self._approval_groups.clear()
            self._approval_by_key.clear()
            waiters = [waiter for group in groups for waiter in group.waiters]
        for event in waiters:
            event.set()

    def _rpc_workspace_path(self, params: dict[str, Any]) -> Path:
        raw_path = params.get("workspace_path")
        if raw_path is None:
            raw_path = params.get("cwd")
        return resolve_workspace_path(
            raw_path,
            roots=tuple(getattr(self.config, "workspace_roots", ()) or ()),
            default=self.workspace,
        )

    @staticmethod
    def _rpc_session_id(params: dict[str, Any]) -> str:
        raw = params.get("session_id")
        if raw is None:
            return f"rpc-{uuid.uuid4().hex[:12]}"
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError("session_id 不能为空")
        return raw.strip()

    def _rpc_thread_tasks(self, record: dict[str, Any]) -> list[dict[str, Any]]:
        session_id = str(record["session_id"])
        workspace_key = _path_key(str(record["workspace_path"]))
        task_thread_id = str(record.get("task_thread_id") or record["thread_id"])
        with self.tasks.lock:
            tasks = [
                task
                for task in self.tasks.tasks.values()
                if task.thread_id == task_thread_id
                or (
                    task.session_id == session_id
                    and _path_key(task.workspace_path) == workspace_key
                )
            ]
        tasks.sort(key=lambda item: item.created_at)
        return [task.snapshot() for task in tasks]

    def _rpc_thread_put(self, thread_id: str, record: dict[str, Any]) -> None:
        """Insert/refresh a thread record as most-recently-used, evicting oldest."""
        self._rpc_threads.pop(thread_id, None)
        self._rpc_threads[thread_id] = record
        while len(self._rpc_threads) > _RPC_THREADS_MAX:
            oldest = next(iter(self._rpc_threads))
            self._rpc_threads.pop(oldest, None)

    def _rpc_thread_record(self, thread_id: str) -> dict[str, Any]:
        with self._rpc_thread_guard:
            record = self._rpc_threads.get(thread_id)
            if record is not None:
                self._rpc_thread_put(thread_id, record)
                return dict(record)
        with self.tasks.lock:
            matching = [task for task in self.tasks.tasks.values() if task.thread_id == thread_id]
        if not matching:
            raise KeyError(thread_id)
        first = min(matching, key=lambda item: item.created_at)
        record = {
            "id": thread_id,
            "thread_id": thread_id,
            "session_id": first.session_id,
            "workspace_path": first.workspace_path,
            "task_thread_id": first.thread_id,
            "created_at_epoch": first.created_at,
        }
        with self._rpc_thread_guard:
            record = self._rpc_threads.setdefault(thread_id, record)
            self._rpc_thread_put(thread_id, record)
            return dict(record)

    def _rpc_thread_view(self, record: dict[str, Any]) -> dict[str, Any]:
        tasks = self._rpc_thread_tasks(record)
        turns = [self._rpc_turn_payload(item, thread_id=str(record["thread_id"])) for item in tasks]
        latest = turns[-1] if turns else None
        result = {
            "id": record["thread_id"],
            "thread_id": record["thread_id"],
            "session_id": record["session_id"],
            "workspace_path": record["workspace_path"],
            "created_at_epoch": record.get("created_at_epoch"),
            "created_at": _iso(float(record["created_at_epoch"])) if record.get("created_at_epoch") else None,
            "status": latest.get("status", "idle") if latest else "idle",
            "active": bool(latest and latest.get("status") in {"queued", "running"}),
            "turn_ids": [item["turn_id"] for item in turns],
            "turns": turns,
        }
        return result

    def _rpc_thread_start(self, params: dict[str, Any]) -> dict[str, Any]:
        workspace = self._rpc_workspace_path(params)
        session_id = self._rpc_session_id(params)
        task_thread_id = TaskManager._thread_id(str(workspace), session_id)
        requested_id = params.get("thread_id")
        if requested_id is None:
            thread_id = task_thread_id
        else:
            thread_id = _validate_thread_id(requested_id)
        with self._rpc_thread_guard:
            record = self._rpc_threads.setdefault(
                thread_id,
                {
                    "id": thread_id,
                    "thread_id": thread_id,
                    "session_id": session_id,
                    "workspace_path": str(workspace),
                    "task_thread_id": task_thread_id,
                    "created_at_epoch": time.time(),
                },
            )
            self._rpc_thread_put(thread_id, record)
            record = dict(record)
        return self._rpc_thread_view(record)

    def _rpc_thread_read(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._rpc_thread_view(self._rpc_thread_for_params(params))

    def _rpc_turn_payload(self, snapshot: dict[str, Any], *, thread_id: str | None = None) -> dict[str, Any]:
        task_id = str(snapshot["task_id"])
        payload = dict(snapshot)
        payload.update({
            "id": task_id,
            "turn_id": task_id,
            "task_id": task_id,
            "thread_id": thread_id or snapshot.get("thread_id"),
        })
        payload["turn"] = dict(snapshot)
        return payload

    def _rpc_thread_for_params(self, params: dict[str, Any]) -> dict[str, Any]:
        raw_thread_id = params.get("thread_id") or params.get("thread")
        if raw_thread_id is None:
            raw_thread_id = params.get("id")
        if not isinstance(raw_thread_id, str) or not raw_thread_id.strip():
            raise ValueError("thread_id 不能为空")
        return self._rpc_thread_record(_validate_thread_id(raw_thread_id))

    def _rpc_turn_id(self, params: dict[str, Any]) -> str | None:
        for key in ("turn_id", "task_id"):
            value = params.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        value = params.get("id")
        return value.strip() if isinstance(value, str) and value.strip() else None

    def _rpc_turn_read(self, params: dict[str, Any]) -> dict[str, Any]:
        thread = None
        if params.get("thread_id") or params.get("thread"):
            thread = self._rpc_thread_for_params(params)
        task_id = self._rpc_turn_id(params)
        if task_id is None:
            if thread is None:
                raise ValueError("turn_id 不能为空")
            tasks = self._rpc_thread_tasks(thread)
            if not tasks:
                raise KeyError(thread["thread_id"])
            snapshot = tasks[-1]
        else:
            snapshot = self.tasks.get(task_id)
        return self._rpc_turn_payload(snapshot, thread_id=thread["thread_id"] if thread else None)

    def _rpc_turn_start(self, params: dict[str, Any]) -> dict[str, Any]:
        if params.get("thread_id") or params.get("thread"):
            thread = self._rpc_thread_for_params(params)
        else:
            thread = self._rpc_thread_start(params)
        raw_message = params.get("message")
        if raw_message is None:
            raw_message = params.get("input")
        if isinstance(raw_message, list):
            parts = [
                str(item.get("text"))
                for item in raw_message
                if isinstance(item, dict) and isinstance(item.get("text"), str)
            ]
            raw_message = "\n".join(parts)
        if not isinstance(raw_message, str) or not raw_message.strip():
            raise ValueError("message 不能为空")
        task = self.tasks.submit({
            "message": raw_message,
            "session_id": thread["session_id"],
            "workspace_path": thread["workspace_path"],
            "allow_changes": bool(params.get("allow_changes")),
            "allow_network": bool(params.get("allow_network")),
            "reasoning_effort": params.get("reasoning_effort"),
            "attachments": params.get("attachments") or [],
        })
        return self._rpc_turn_payload(task, thread_id=thread["thread_id"])

    def _rpc_turn_interrupt(self, params: dict[str, Any]) -> dict[str, Any]:
        task_id = self._rpc_turn_id(params)
        if task_id is None:
            raise ValueError("turn_id 不能为空")
        snapshot = self.tasks.cancel(task_id)
        return self._rpc_turn_payload(snapshot)

    # ------------------------------------------------------------------
    # M4-3: read-only RPC surface.
    #
    # The dispatcher only exposed thread/turn *lifecycle* methods, so a client
    # could start and poll work but could not read anything about the workspace
    # it was driving — every inspection had to go through a separate HTTP route
    # with a different response shape. These five methods close that gap and
    # reuse the same workspace-boundary check (`_rpc_workspace_path`, which
    # enforces ``workspace_roots``) as the lifecycle methods. All five are
    # strictly read-only: none of them mutates task, session or workspace state.
    # ------------------------------------------------------------------

    def _rpc_workspace_read(self, params: dict[str, Any]) -> dict[str, Any]:
        """Describe the resolved workspace without switching the service to it."""
        workspace = self._rpc_workspace_path(params)
        return {
            "name": workspace.name,
            "path": workspace.as_posix(),
            "exists": workspace.is_dir(),
            "is_git": (workspace / ".git").exists(),
            "current": _path_key(workspace) == _path_key(self.workspace),
            "model": self.config.model,
            "endpoint": self.config.base_url,
            "sandbox": self.sandbox.status(),
            "context_window_tokens": int(getattr(self.config, "context_window_tokens", 300_000)),
            "recent_workspaces": self.workspace_catalog.list(),
        }

    def _rpc_models_list(self, params: dict[str, Any]) -> dict[str, Any]:
        """Gateway model catalog for the resolved workspace (never raises)."""
        self._rpc_workspace_path(params)
        return self.list_models()

    def _rpc_changes_read(self, params: dict[str, Any]) -> dict[str, Any]:
        """Workspace change summary, or one file's diff when ``path`` is given."""
        workspace = self._rpc_workspace_path(params)
        raw_path = params.get("path")
        if raw_path is not None and (not isinstance(raw_path, str) or not raw_path.strip()):
            raise ValueError("path 不能为空")
        try:
            inspector = ChangeInspector(workspace)
            if raw_path:
                return inspector.diff(str(raw_path).strip())
            return inspector.summary()
        except ChangeError as exc:
            raise ValueError(str(exc)) from exc

    def _rpc_sessions_list(self, params: dict[str, Any]) -> dict[str, Any]:
        """Stored conversations in the resolved workspace (forks are files too)."""
        workspace = self._rpc_workspace_path(params)
        sessions = list_sessions(workspace)
        return {
            "workspace_path": str(workspace),
            "count": len(sessions),
            "sessions": sessions,
        }

    def _rpc_permissions_read(self, params: dict[str, Any]) -> dict[str, Any]:
        """Effective declarative permission rules for the resolved workspace."""
        workspace = self._rpc_workspace_path(params)
        rules, error = load_permission_rules(workspace)
        return {
            "path": (workspace / ".minicc" / "permissions.json").as_posix(),
            "allow": rules["allow"],
            "deny": rules["deny"],
            "error": error,
        }

    def switch_workspace(self, raw_path: str) -> dict[str, Any]:
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError("工作区路径不能为空")
        candidate = resolve_workspace_path(
            raw_path, roots=tuple(getattr(self.config, "workspace_roots", ()) or ())
        )
        current = self.workspace.resolve()
        if candidate == current:
            self.workspace_catalog.remember(candidate)
            return self.workspace_info()
        with self._workspace_guard:
            self.workspace = candidate
            self.system_prompt = build_system_prompt(candidate)
            self.worktrees = WorktreeManager(candidate)
            self._set_current_mcp(candidate)
            self.workspace_catalog.remember(candidate)
        return self.workspace_info()

    def file_tree(self, rel_path: str = "", depth: int = 3) -> dict[str, Any]:
        """Structured workspace listing backing /api/files (frontend file tree)."""
        from .tools.fs import SKIP_DIRS, _escapes_workspace

        root = self.workspace.resolve()
        raw = str(rel_path or "").strip()
        target = root if not raw else (root / raw).resolve()
        if not (target == root or target.is_relative_to(root)):
            raise ValueError(f"路径越界: {raw}")
        if not target.is_dir():
            raise ValueError(f"不是目录: {raw}")
        try:
            depth = max(1, min(int(depth), 6))
        except (TypeError, ValueError):
            depth = 3
        max_entries = 2000
        entries: list[dict[str, Any]] = []
        truncated = False

        def walk(directory: Path, level: int) -> None:
            nonlocal truncated
            if truncated or level > depth:
                return
            try:
                children = sorted(directory.iterdir(), key=lambda item: (item.is_file(), item.name.lower()))
            except OSError:
                return
            for child in children:
                if child.name in SKIP_DIRS or _escapes_workspace(child, root):
                    continue
                if len(entries) >= max_entries:
                    truncated = True
                    return
                rel = child.relative_to(root).as_posix()
                if child.is_dir():
                    entries.append({"name": child.name, "path": rel, "type": "dir", "size": 0})
                    walk(child, level + 1)
                else:
                    try:
                        size = child.stat().st_size
                    except OSError:
                        size = 0
                    entries.append({"name": child.name, "path": rel, "type": "file", "size": size})

        walk(target, 1)
        return {
            "root": root.as_posix(),
            "path": target.relative_to(root).as_posix() if target != root else "",
            "depth": depth,
            "truncated": truncated,
            "entries": entries,
        }

    def search_history(self, query: str, limit: int = 50, workspace_path: str | None = None) -> dict[str, Any]:
        """Global task-history search backing /api/history/search."""
        results = self.tasks.search(
            query,
            limit=limit,
            workspace_path=workspace_path,
        )
        return {"query": str(query or "").strip(), "results": results}

    def rewind_session(
        self,
        session_id: str,
        keep_messages: int | None = None,
        user_index: int | None = None,
    ) -> dict[str, Any]:
        """Rewind a stored conversation to a message or user-turn index."""
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id 不能为空")
        store = SessionStore(self.workspace, session_id.strip())
        if user_index is not None:
            return store.rewind_to_user_index(user_index)
        if keep_messages is None:
            raise ValueError("keep_messages 或 user_index 必须提供")
        return store.rewind(keep_messages)

    def fork_session(
        self,
        session_id: str,
        from_message_id: int | str,
        new_session_id: str | None = None,
    ) -> dict[str, Any]:
        """M8-T2: branch a stored conversation at one message into a new session."""
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id 不能为空")
        store = SessionStore(self.workspace, session_id.strip())
        raw_new = str(new_session_id).strip() if new_session_id else ""
        target = store.fork(from_message_id, new_session_id=raw_new or None)
        return {
            "session_id": target.session_id,
            "forked_from": store.session_id,
            "from_message_id": from_message_id,
        }

    def list_stored_sessions(self) -> dict[str, Any]:
        """M8-T2: the session forest backing /api/sessions (forks are files)."""
        sessions = list_sessions(self.workspace)
        return {
            "workspace_path": str(self.workspace),
            "count": len(sessions),
            "sessions": sessions,
        }

    def get_allowlist(self, session_id: str) -> dict[str, Any]:
        sid = str(session_id or "").strip()
        if not sid:
            raise ValueError("session_id 不能为空")
        rules = session_rules(self.workspace, sid)
        return {"session_id": sid, **rules}

    def set_allowlist(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        sid = str(session_id or "").strip()
        if not sid:
            raise ValueError("session_id 不能为空")
        rules = replace_session_rules(
            self.workspace,
            sid,
            commands=payload.get("commands"),
            paths=payload.get("paths"),
            tools=payload.get("tools"),
        )
        return {"session_id": sid, **rules}

    def permissions_status(self) -> dict[str, Any]:
        """Effective declarative permission rules + any load error (M7-T3)."""
        rules, error = load_permission_rules(self.workspace)
        return {
            "path": (self.workspace / ".minicc" / "permissions.json").as_posix(),
            "allow": rules["allow"],
            "deny": rules["deny"],
            "error": error,
            "approval_timeout_seconds": APPROVAL_TIMEOUT_SECONDS,
        }

    def restore_task_snapshot(self, task_id: str) -> dict[str, Any]:
        tid = str(task_id or "").strip()
        if not tid:
            raise ValueError("task_id 不能为空")
        snapshot = self.tasks.get(tid)
        workspace = resolve_workspace_path(
            str((snapshot or {}).get("workspace_path") or self.workspace),
            roots=tuple(getattr(getattr(self, "config", None), "workspace_roots", ()) or ()),
        )
        with self.tasks.lock:
            if self.tasks.has_active(str(workspace)):
                raise SnapshotError("工作区仍有任务运行，请等待结束后再恢复文件")
            return restore_workspace_snapshot(workspace, tid)

    def list_models(self) -> dict[str, Any]:
        """Catalog for the settings panel: gateway models with local fallback.

        Never raises and never echoes credentials; failures degrade to the
        configured default + fallback models with a user-facing ``error``.
        """
        cfg = self.config
        default_model = str(getattr(cfg, "model", "") or "")
        fallbacks = [str(m) for m in (getattr(cfg, "fallback_models", ()) or ()) if str(m)]

        def _local(error: str = "") -> dict[str, Any]:
            ids: list[str] = []
            for model in (default_model, *fallbacks):
                if model and model not in ids:
                    ids.append(model)
            payload: dict[str, Any] = {
                "models": [{"id": model} for model in ids],
                "default_model": default_model,
            }
            if error:
                payload["error"] = error
            return payload

        base = str(getattr(cfg, "base_url", "") or "").rstrip("/")
        api_key = str(getattr(cfg, "api_key", "") or "")
        if httpx is None or not base or not api_key:
            return _local("未配置可用的模型网关，仅显示本地模型列表")
        provider = str(getattr(cfg, "provider_type", "openai") or "openai")
        if provider == "anthropic":
            headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
        else:
            headers = {"Authorization": f"Bearer {api_key}"}
        roots = [base] if base.endswith("/v1") else [base, f"{base}/v1"]
        last_error = "网关未返回模型列表"
        for root in roots:
            try:
                response = httpx.get(f"{root}/models", headers=headers, timeout=5.0)
            except Exception as exc:
                last_error = f"模型列表获取失败: {type(exc).__name__}"
                continue
            if response.status_code != 200:
                last_error = f"模型列表请求失败 (HTTP {response.status_code})"
                continue
            try:
                data = response.json()
            except ValueError:
                last_error = "模型列表响应不是合法 JSON"
                continue
            items = data.get("data") or data.get("models") or []
            models: list[dict[str, Any]] = []
            for item in items if isinstance(items, list) else []:
                if isinstance(item, str) and item:
                    models.append({"id": item})
                elif isinstance(item, dict) and item.get("id"):
                    entry: dict[str, Any] = {"id": str(item["id"])}
                    for key in ("context_length", "context_window", "max_model_len"):
                        value = item.get(key)
                        if isinstance(value, (int, float)) and value > 0:
                            entry["context_length"] = int(value)
                            break
                    models.append(entry)
            if models:
                return {"models": models, "default_model": default_model or models[0]["id"]}
            last_error = "网关返回空模型列表"
        return _local(last_error)

    def list_commands(self) -> dict[str, Any]:
        return {"commands": [c.to_public_dict() for c in discover_commands(self.workspace)]}

    def workspace_info(self) -> dict[str, Any]:
        try:
            worktrees = self.worktrees.list()
            worktree_error = ""
        except WorktreeError as exc:
            worktrees = []
            worktree_error = str(exc)
        return {
            "name": self.workspace.name,
            "path": self.workspace.as_posix(),
            "recent_workspaces": self.workspace_catalog.list(),
            "model": self.config.model,
            "endpoint": self.config.base_url,
            "sandbox": self.sandbox.status(),
            "mcp": self.mcp.status() if self.mcp else {"configured": 0, "error": self.mcp_error},
            "permissions": {
                "default": "full" if self.config.yolo else "per_task",
                "host_commands": self.sandbox.status().get("backend") == "host",
            },
            "context_window_tokens": int(getattr(self.config, "context_window_tokens", 300_000)),
            "reasoning_effort": str(getattr(self.config, "reasoning_effort", "high")),
            "max_repair_attempts": int(getattr(self.config, "max_repair_attempts", 2)),
            "worktrees": worktrees,
            "worktree_error": worktree_error,
            "tools": [
                "read_file",
                "glob",
                "grep",
                "tree",
                "git_status",
                "git_diff",
                "write_file",
                "edit_file",
                "bash",
                "worktree_list",
                "worktree_create",
                "worktree_remove",
                "web_search",
                "webfetch",
                "todo_write",
                "todo_read",
            ],
        }

    def chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._run_chat(payload)

    def _make_provider(
        self,
        *,
        timeout: float,
        status_callback: Any | None = None,
        protocol_override: str | None = None,
        model_override: str | None = None,
        reasoning_effort: str | None = None,
    ) -> Any:
        """Build the provider client one call should use.

        The single place that maps config onto a provider, so a call outside
        the agent loop cannot quietly pick a different wire protocol, ignore
        the per-task model, or bypass the offline test provider.
        """
        if os.getenv("MINICC_FAKE_PROVIDER", "").strip().lower() in TRUTHY:
            return FakeProvider(on_status=status_callback)
        if str(getattr(self.config, "provider_type", "openai")) == "anthropic":
            return AnthropicProvider(
                api_key=self.config.api_key,
                model=str(model_override or self.config.model),
                base_url=str(getattr(self.config, "anthropic_base_url", "") or self.config.base_url),
                timeout=timeout,
                max_retries=int(getattr(self.config, "provider_retries", 4)),
                on_status=status_callback,
            )
        return OpenAICompatibleProvider(
            base_url=self.config.base_url,
            api_key=self.config.api_key,
            model=str(model_override or self.config.model),
            timeout=timeout,
            max_retries=int(getattr(self.config, "provider_retries", 4)),
            tool_mode=self.config.tool_mode,
            protocol=str(protocol_override or getattr(self.config, "llm_protocol", "auto")),
            reasoning_effort=str(
                reasoning_effort or getattr(self.config, "reasoning_effort", "high")
            ),
            on_status=status_callback,
        )

    def merge_batch(
        self,
        children: list[dict[str, Any]],
        *,
        on_stream: Any | None = None,
        on_usage: Any | None = None,
        reasoning_effort: str | None = None,
        model: str | None = None,
        workspace_path: str | None = None,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        """Ask the model to merge parallel child results into one answer."""
        reports = []
        for index, child in enumerate(children, start=1):
            reports.append(
                f"子任务 {index} ({child.get('status')}):\n"
                f"{str(child.get('answer') or child.get('error') or child.get('stream_text') or '')[:6000]}"
            )
        prompt = (
            "请把以下并行 coding agent 子任务结果合并成一份简洁、可执行的最终答复。"
            "保留关键文件、命令、风险和未完成事项，不要声称没有验证过的内容。\n\n"
            + "\n\n".join(reports)
        )

        async def execute() -> dict[str, Any]:
            quiet_loop_teardown()
            provider = self._make_provider(
                timeout=float(self.config.timeout),
                model_override=model,
                reasoning_effort=str(reasoning_effort or ""),
            )
            try:
                response = await chat_with_cancellation(
                    provider,
                    messages=[
                        system_msg("你是并行 coding agent 的结果合并器，只负责总结已完成的子任务。"),
                        user_msg(prompt),
                    ],
                    tools=None,
                    on_delta=on_stream,
                    cancel_event=cancel_event,
                )
                if on_usage is not None and response.usage:
                    on_usage(dict(response.usage))
                return {
                    "answer": response.text or "并行子任务已完成，但合并器没有返回文字。",
                    "cancelled": False,
                    "tokens_used": dict(response.usage),
                }
            except AgentCancelled:
                return {"answer": "批量任务已取消。", "cancelled": True}
            finally:
                await provider.close()

        return asyncio.run(execute())

    def _run_chat(
        self,
        payload: dict[str, Any],
        *,
        on_event: Any | None = None,
        on_stream: Any | None = None,
        on_usage: Any | None = None,
        on_context: Any | None = None,
        on_compaction: Any | None = None,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        message = payload.get("message")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("message 不能为空")
        session_id = str(payload.get("session_id") or "web-latest")
        allow_changes, allow_network, _mode = _resolve_task_permissions(
            payload, yolo=self.config.yolo
        )
        workspace = resolve_workspace_path(
            payload.get("workspace_path") or self.workspace,
            roots=tuple(getattr(self.config, "workspace_roots", ()) or ()),
        )
        session_lock = self._session_lock(workspace, session_id)
        while not session_lock.acquire(timeout=0.25):
            if cancel_event is not None and cancel_event.is_set():
                return {"answer": "任务已取消。", "cancelled": True, "session_id": session_id, "events": []}
        try:
            return self._chat_locked(
                payload,
                workspace=workspace,
                on_event=on_event,
                on_stream=on_stream,
                on_usage=on_usage,
                on_context=on_context,
                on_compaction=on_compaction,
                cancel_event=cancel_event,
            )
        finally:
            session_lock.release()

    def _chat_locked(
        self,
        payload: dict[str, Any],
        *,
        workspace: Path,
        on_event: Any | None = None,
        on_stream: Any | None = None,
        on_usage: Any | None = None,
        on_context: Any | None = None,
        on_compaction: Any | None = None,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        message = str(payload["message"])
        # M7-T2: custom slash commands expand server-side, so CLI and Web
        # share one template engine and the model receives the full prompt.
        message = expand_slash_command(message, workspace) or message
        session_id = str(payload.get("session_id") or "web-latest")
        if on_event is None:
            # M8-T5's event funnel lives in TaskManager._run, so the
            # synchronous /api/chat path logged HTTP access lines and nothing
            # about the run itself. The same vocabulary has to be greppable
            # from every entry point, not only the one the workbench UI uses.
            def on_event(event: dict[str, Any], *, _session_id: str = session_id) -> None:
                log_task_event(event, task_id=_session_id)
        allow_changes, allow_network, permission_mode = _resolve_task_permissions(
            payload, yolo=self.config.yolo
        )
        attachments = _normalize_attachments(payload.get("attachments"))
        vision_context = _attachment_content_parts(attachments)
        # M7-T5: @-mentions inject bounded heads of referenced workspace
        # files (junction-safe; oversized files carry a [truncated] marker).
        model_message, mention_records = apply_mentions(message.strip(), workspace)
        hook_runner = HookRunner(workspace)
        store = SessionStore(workspace, session_id)
        messages = store.load(build_system_prompt(workspace))
        resume_from_checkpoint = bool(payload.get("resume_from_checkpoint")) and store.exists
        messages.append(
            user_msg(
                model_message
                if resume_from_checkpoint
                else _multimodal_content(model_message, attachments)
            )
        )
        store.save(messages)
        if permission_mode == "plan":
            network_note = "联网搜索可用" if allow_network else "联网也不可用"
            messages.append(system_msg(
                "[计划模式] 本任务是只读规划模式：文件写入与命令执行已被禁用，"
                f"{network_note}。请完成调研后输出一份实施计划（目标、步骤、涉及文件、验证方式、风险），"
                "不要尝试调用写入类工具。"
            ))
        evidence_hits = get_evidence_index(workspace).search(message, limit=8)
        if evidence_hits:
            evidence_summary = "\n".join(
                f"- {hit.path} ({hit.reason}; symbols: {', '.join(hit.symbols[:4]) or 'none'})"
                for hit in evidence_hits
            )
            messages.append(system_msg(
                "[本地检索索引] 以下为与任务可能相关的路径和符号；它们只是定位提示，"
                "使用前必须通过工具重新检查。\n" + evidence_summary
            ))
        snapshot_task_id = str(payload.get("task_id") or "")
        journal = SnapshotJournal(workspace, snapshot_task_id) if snapshot_task_id and workspace_snapshot_exists(workspace, snapshot_task_id) else None
        editor = Editor(
            workspace, audit_path=workspace / ".minicc" / "audit.jsonl",
            before_write=journal.before_write if journal else None,
            after_write=journal.after_write if journal else None,
        )
        registry = build_registry(
            editor,
            yolo=allow_changes,
            sandbox=self.sandbox,
            mcp_manager=self._mcp_for_workspace(workspace),
            worktree_manager=WorktreeManager(workspace),
        )
        events: list[dict[str, Any]] = []
        workflow = build_coding_workflow()
        workflow.validate()
        runtime_state = AgentState(
            task_id=f"{session_id}-{uuid.uuid4().hex[:8]}",
            prompt=message.strip(),
            workspace_path=str(workspace),
            workflow=workflow.name,
            budget=Budget(
                max_turns=getattr(self.config, "max_turns", None),
                max_tool_calls=None,
                max_duration_seconds=None,
                # Retry/recovery policy is tracked separately below. It is
                # not a task budget and must not raise BudgetExceeded during
                # a long-running coding session.
                max_retries=None,
                soft_max_tokens=getattr(self.config, "soft_max_tokens", None),
                soft_max_duration_seconds=getattr(self.config, "soft_max_duration_seconds", None),
            ),
        )
        runtime_state.transition("intake", phase="intake")
        runtime_state.transition("plan", phase="planning")
        stage_router = StageRouter(
            str(self.config.model),
            float(self.config.timeout),
            fallback_models=tuple(getattr(self.config, "fallback_models", ()) or ()),
        )
        initial_route = stage_router.route("planning")
        verifier = Verifier()
        verification_results: list[dict[str, Any]] = []
        repair_attempts = 0
        provider_recoveries = 0
        agent_recoveries = 0
        planner_result: Any | None = None
        planner_usage: dict[str, Any] = {}
        planner_policy: PlannerPolicy | None = None
        planner_execution: dict[str, Any] | None = None
        complexity = assess_complexity(message, attachment_count=len(attachments))
        task_kind = str(payload.get("task_kind") or "task")
        planner_requested = (
            bool(payload.get("planner_requested"))
            or task_kind == "batch"
            or (task_kind != "subtask" and complexity.should_fan_out)
        )

        def enter_runtime_node(node: str, phase: str) -> None:
            event = runtime_state.transition(node, phase=phase).copy()
            events.append(event)
            if on_event is not None:
                on_event(event)

        if attachments:
            image_event = {
                "kind": "trace",
                "name": "agent",
                "status": "ok",
                "phase": "planning",
                "code": "image_attached",
                "summary": f"已接收 {len(attachments)} 张图片，作为视觉上下文发送给模型",
                "detail": {"count": len(attachments), "names": [item["name"] for item in attachments]},
            }
            events.append(image_event)
            if on_event is not None:
                on_event(image_event)

        if mention_records:
            injected = [item for item in mention_records if item["status"] == "injected"]
            rejected = [item for item in mention_records if item["status"] == "rejected"]
            mention_summary = f"已按 @-提及注入 {len(injected)} 个文件内容"
            if rejected:
                mention_summary += f"，拒绝 {len(rejected)} 个越界引用"
            mention_event = {
                "kind": "trace",
                "name": "agent",
                "status": "ok",
                "phase": "planning",
                "code": "mentions_resolved",
                "summary": mention_summary,
                "detail": {"records": mention_records},
            }
            events.append(mention_event)
            if on_event is not None:
                on_event(mention_event)

        route_event = {
            "kind": "trace", "name": "router", "status": "ok", "phase": "planning",
            "code": "stage_route",
            "summary": "已应用规划阶段的模型与请求策略",
            "detail": initial_route.to_dict(),
        }
        events.append(route_event)
        if on_event is not None:
            on_event(route_event)
        if evidence_hits:
            retrieval_event = {
                "kind": "trace", "name": "retrieval", "status": "ok", "phase": "planning",
                "code": "local_evidence_index",
                "summary": f"本地索引提供 {len(evidence_hits)} 个候选文件，Agent 会逐项复核",
                "detail": {"hits": [hit.to_dict() for hit in evidence_hits]},
            }
            events.append(retrieval_event)
            if on_event is not None:
                on_event(retrieval_event)

        def on_tool(call: ToolCall, result: ToolResult) -> None:
            feedback = build_tool_feedback(call, result, risk=registry.risk_of(call.tool))
            events.append(
                {
                    "name": call.tool,
                    "status": result.status,
                    "summary": result.summary,
                    "output": redact_text(result.render()[:8000])[0],
                    "data": feedback.get("structured_data") or {},
                    "path": feedback.get("path"),
                    "command": feedback.get("command"),
                    "risk": registry.risk_of(call.tool),
                    "write": call.tool in COMPLETION_WRITE_TOOLS and result.status == "ok",
                    "observation": feedback.get("observation"),
                    "exit_code": result.exit_code,
                    "duration_ms": feedback.get("duration_ms"),
                    "truncated": bool(result.truncated),
                    "security_tags": list(result.security_tags),
                    "kind": "tool",
                }
            )
            if on_event is not None:
                on_event(events[-1])

        def on_trace(event: dict[str, Any]) -> None:
            events.append(dict(event))
            if on_event is not None:
                on_event(events[-1])
            if event.get("code") in {
                "tool_round_finished",
                "verification_required_before_finish",
                "provider_stream_error",
                "budget_exceeded",
                "stagnation_guard",
                "run_finished",
            }:
                store.save(messages)

        def emit_decision(name: str, decision: AuthorizationDecision) -> bool:
            event = decision.to_event(name)
            events.append(event)
            if on_event is not None:
                on_event(event)
            return decision.allowed

        def should_allow(name: str, call: ToolCall) -> bool:
            risk = registry.risk_of(name)
            # M7-T3: a declarative deny rule is an absolute veto checked before
            # authorize_tool (and it also covers read-only tools, so denying a
            # path like `.env` blocks reads too).
            rule = match_permission_rule(workspace, name, call.arguments)
            if rule == "deny":
                return emit_decision(name, AuthorizationDecision(
                    False, risk or "unknown",
                    "permissions.json deny 规则拒绝", "permission_rule_deny",
                ))
            decision = authorize_tool(
                name,
                risk,
                call.arguments,
                allow_changes=allow_changes,
                allow_network=allow_network,
                permission_mode=permission_mode,
                session_id=session_id,
                workspace=workspace,
                capabilities=registry.capabilities_of(name),
            )
            if (
                not decision.allowed
                and decision.authorization in {"missing_task_write", "missing_task_exec"}
            ):
                # An allow rule only skips the interactive prompt; it can never
                # change plan/yolo/network semantics.
                if rule == "allow":
                    return emit_decision(name, AuthorizationDecision(
                        True, decision.risk,
                        "permissions.json allow 规则放行", "permission_rule_allow",
                    ))
                # No static rule covers the call → ask the user over the event
                # stream, auto-deny on timeout/cancel (M7-T3).
                verdict = self.request_approval(
                    session_id=session_id,
                    task_id=snapshot_task_id or session_id,
                    tool=name,
                    arguments=call.arguments,
                    risk=decision.risk,
                    reason=decision.reason,
                    on_event=on_event,
                    cancel_event=cancel_event,
                )
                if verdict["decision"] in {"allow", "always"}:
                    always = verdict["decision"] == "always"
                    if always:
                        try:
                            kwargs: dict[str, str] = {"tool": name}
                            if name == "bash":
                                kwargs["command"] = str(
                                    (call.arguments or {}).get("command") or ""
                                ).strip()
                            path_arg = (call.arguments or {}).get("path")
                            if isinstance(path_arg, str) and path_arg.strip():
                                kwargs["path"] = path_arg.strip()
                            if session_id:
                                add_session_rule(workspace, session_id, **kwargs)
                        except AllowlistError:
                            pass
                    return emit_decision(name, AuthorizationDecision(
                        True, decision.risk,
                        "用户已批准" + ("（本会话记住）" if always else ""),
                        "user_approved",
                    ))
                if verdict.get("cancelled"):
                    why = "任务已取消，审批自动拒绝"
                elif verdict.get("timed_out"):
                    why = "审批超时，自动拒绝"
                else:
                    why = "用户已拒绝"
                return emit_decision(name, AuthorizationDecision(
                    False, decision.risk, why, "user_denied",
                ))
            return emit_decision(name, decision)

        async def execute() -> Any:
            quiet_loop_teardown()
            nonlocal planner_result, planner_usage, planner_policy, planner_execution
            nonlocal repair_attempts, provider_recoveries, agent_recoveries

            def make_provider(
                *,
                timeout: float,
                status_callback: Any | None,
                protocol_override: str | None = None,
                model_override: str | None = None,
            ) -> Any:
                return self._make_provider(
                    timeout=timeout,
                    status_callback=status_callback,
                    protocol_override=protocol_override,
                    model_override=model_override,
                    reasoning_effort=str(payload.get("reasoning_effort") or ""),
                )

            provider = make_provider(timeout=initial_route.timeout, status_callback=on_event)
            # Bounded Task subagent: registered per task so the model can
            # spawn readonly research sub-runs; restricted registry keeps it
            # non-recursive. Sub-tool calls inherit parent permission gating
            # only through the restricted readonly toolset.
            try:
                registry.register(build_task_tool_spec(
                    provider_factory=lambda: make_provider(
                        timeout=float(self.config.timeout), status_callback=None
                    ),
                    workspace=workspace,
                    system_prompt=build_system_prompt(workspace),
                    base_registry=registry,
                    cancel_event=cancel_event,
                ))
            except ValueError:
                pass
            try:
                aggregate: TurnResult | None = None
                max_repairs = max(0, int(getattr(self.config, "max_repair_attempts", 2)))
                max_provider_recoveries = max(0, int(getattr(self.config, "task_recovery_retries", 2)))
                max_agent_recoveries = max_provider_recoveries
                completion_review_failures = 0
                completion_review_attempt = 0
                # Bound completion-judge "continue" loops so a reviewer that keeps
                # requesting more work cannot re-run the agent until the shared
                # turn budget is exhausted with nothing new to show.
                max_completion_continues = max(1, int(getattr(self.config, "max_completion_continues", 3)))
                completion_continues = 0
                verification_guard_error = "Agent 在修改工作区后没有完成验证"

                fallback_cursor = {"index": 0}

                async def recreate_provider_after_failure() -> str:
                    """Refresh a poisoned pool; rotate to the next fallback model
                    after the first recovery attempt has already been used."""
                    nonlocal provider
                    current_protocol = provider.protocol()
                    protocol_status = provider.protocol_status()
                    next_protocol = current_protocol
                    if protocol_status.get("requested") == "auto" and current_protocol == "responses":
                        # A transport failure after the response body starts is
                        # usually gateway-specific. Keep the retry atomic and
                        # use the older, broadly supported endpoint next.
                        next_protocol = "chat_completions"
                    await provider.close()
                    fallback_models = tuple(initial_route.fallback_models or ())
                    model_override: str | None = None
                    attempt = fallback_cursor["index"]
                    fallback_cursor["index"] += 1
                    if fallback_models and attempt >= 1:
                        # First recovery keeps the primary model and only downgrades
                        # the protocol; from the second recreation onward rotate
                        # through the configured fallback models.
                        index = min(attempt - 1, len(fallback_models) - 1)
                        model_override = fallback_models[index]
                        events.append({
                            "kind": "trace", "name": "provider", "status": "ok",
                            "phase": "planning", "code": "task_model_fallback",
                            "summary": f"多次恢复失败，切换到备用模型 {model_override}",
                            "detail": {"model": model_override, "index": index,
                                       "fallback_models": list(fallback_models)},
                        })
                        if on_event is not None:
                            on_event(events[-1])
                    provider = make_provider(
                        timeout=initial_route.timeout,
                        status_callback=on_event,
                        protocol_override=next_protocol,
                        model_override=model_override,
                    )
                    return next_protocol

                async def execute_dynamic_plan(plan: DAGPlan, policy: PlannerPolicy) -> dict[str, Any]:
                    """Run a validated, non-writing plan before the main agent."""

                    if not _is_bounded_readonly_plan(plan):
                        skipped = {
                            "status": "skipped",
                            "reason": "dynamic_plan_contains_write_or_unbounded_tools",
                            "plan_name": plan.name,
                            "completed": [],
                            "failed": [],
                            "skipped": [task.id for task in plan.tasks],
                            "outputs": {},
                        }
                        event = {
                            "kind": "trace",
                            "name": "planner",
                            "status": "ok",
                            "phase": "planning",
                            "code": "planner_execution_skipped",
                            "summary": "动态计划包含非只读节点，未直接执行，交由主 Agent 按原有权限路径处理",
                            "detail": skipped,
                        }
                        events.append(event)
                        if on_event is not None:
                            on_event(event)
                        return skipped

                    started = {
                        "kind": "trace",
                        "name": "planner",
                        "status": "ok",
                        "phase": "planning",
                        "code": "planner_execution_started",
                        "summary": f"已将验证后的只读计划接入 DAG 执行，共 {len(plan.tasks)} 个节点",
                        "detail": {
                            "plan_name": plan.name,
                            "node_count": len(plan.tasks),
                            "max_concurrency": policy.max_concurrency,
                            "execution_mode": "bounded_readonly_dag",
                        },
                    }
                    events.append(started)
                    if on_event is not None:
                        on_event(started)

                    def emit_node_event(
                        task: PlanTask,
                        node_events: list[dict[str, Any]],
                        event: dict[str, Any],
                    ) -> None:
                        annotated = {
                            **dict(event),
                            "plan": plan.name,
                            "plan_node": task.id,
                        }
                        node_events.append(annotated)
                        if on_event is not None:
                            on_event(annotated)

                    async def run_node(
                        task: PlanTask,
                        dependency_outputs: dict[str, dict[str, Any]],
                    ) -> dict[str, Any]:
                        node_events: list[dict[str, Any]] = []
                        node_summaries: list[str] = []

                        def emit(event: dict[str, Any]) -> None:
                            emit_node_event(task, node_events, event)
                            summary = str(event.get("summary") or "").strip()
                            if summary:
                                node_summaries.append(summary)

                        started_event = {
                            "kind": "trace",
                            "name": "planner",
                            "status": "ok",
                            "phase": "planning",
                            "code": "planner_node_started",
                            "summary": f"DAG 节点 {task.id} 开始执行",
                            "detail": {
                                "kind": task.kind,
                                "depends_on": list(task.depends_on),
                                "allowed_tools": sorted(task.allowed_tools),
                            },
                        }
                        emit(started_event)

                        dependency_json = json.dumps(
                            dependency_outputs,
                            ensure_ascii=False,
                            default=str,
                            separators=(",", ":"),
                        )
                        dependency_json, _ = redact_text(dependency_json)
                        if len(dependency_json) > 6000:
                            dependency_json = dependency_json[:5999].rstrip() + "…"
                        goal_json = json.dumps(task.payload, ensure_ascii=False, default=str)
                        goal_json, _ = redact_text(goal_json)
                        task_message, _ = redact_text(message[:9000])
                        instruction = (
                            "你是主 Agent 的只读计划节点。只完成当前节点目标，不修改工作区，不执行联网或危险操作。\n"
                            "只能使用计划白名单中的工具；关键结论必须来自工具结果。完成后给出简短证据摘要。\n\n"
                            f"原始用户任务：\n{task_message}\n\n"
                            f"当前节点：{task.id}（{task.kind}）\n"
                            f"节点目标与验收提示：{goal_json or '{}'}\n"
                            f"依赖节点的已完成摘要：\n{dependency_json or '{}'}\n"
                            f"计划白名单工具：{', '.join(sorted(task.allowed_tools)) or '无'}"
                        )
                        node_messages = [
                            system_msg(build_system_prompt(workspace)),
                            user_msg(instruction),
                        ]
                        node_registry = registry.restrict(task.allowed_tools)

                        def node_status(status: dict[str, Any]) -> None:
                            emit({
                                "kind": "trace",
                                "name": "provider",
                                "status": "ok",
                                "phase": "planning",
                                "code": "planner_node_provider_status",
                                "summary": "计划节点模型连接状态已更新",
                                "detail": status,
                            })

                        def node_trace(event: dict[str, Any]) -> None:
                            emit(dict(event))

                        def node_tool(call: ToolCall, tool_result: ToolResult) -> None:
                            feedback = build_tool_feedback(
                                call,
                                tool_result,
                                risk=node_registry.risk_of(call.tool),
                            )
                            emit({
                                "kind": "tool",
                                "name": call.tool,
                                "status": tool_result.status,
                                "summary": tool_result.summary,
                                "output": redact_text(tool_result.render()[:8000])[0],
                                "data": feedback.get("structured_data") or {},
                                "path": feedback.get("path"),
                                "command": feedback.get("command"),
                                "risk": node_registry.risk_of(call.tool),
                                "write": False,
                                "observation": feedback.get("observation"),
                                "exit_code": tool_result.exit_code,
                                "duration_ms": feedback.get("duration_ms"),
                                "truncated": bool(tool_result.truncated),
                                "security_tags": list(tool_result.security_tags),
                            })

                        def node_allow(name: str, call: ToolCall) -> bool:
                            if name not in task.allowed_tools:
                                emit({
                                    "kind": "authorization",
                                    "name": name,
                                    "status": "denied",
                                    "phase": "permission",
                                    "code": "planner_tool_out_of_scope",
                                    "summary": f"计划节点 {task.id} 未将工具 {name} 列入白名单",
                                    "risk": node_registry.risk_of(name) or "unknown",
                                    "authorization": "planner_whitelist",
                                })
                                return False
                            decision = authorize_tool(
                                name,
                                node_registry.risk_of(name),
                                call.arguments,
                                allow_changes=False,
                                allow_network=allow_network,
                                session_id=session_id,
                                workspace=workspace,
                                capabilities=node_registry.capabilities_of(name),
                            )
                            event = decision.to_event(name)
                            emit(event)
                            return decision.allowed

                        node_provider: OpenAICompatibleProvider | None = None
                        try:
                            node_provider = make_provider(
                                timeout=stage_router.route("inspect").timeout,
                                status_callback=node_status,
                            )
                            node_result = await run_agent(
                                node_provider,
                                node_registry,
                                node_messages,
                                max_turns=None,
                                compact_threshold=int(getattr(self.config, "compact_threshold", 300_000)),
                                on_tool=node_tool,
                                on_trace=node_trace,
                                should_allow=node_allow,
                                should_cancel=(cancel_event.is_set if cancel_event is not None else None),
                                cancel_event=cancel_event,
                                context_limit_tokens=int(getattr(self.config, "context_window_tokens", 300_000)),
                                budget=Budget(
                                    max_turns=None,
                                    max_tool_calls=None,
                                    max_duration_seconds=None,
                                    max_retries=None,
                                ),
                                vision_context=vision_context,
                                hooks=hook_runner,
                            )
                            answer, _ = redact_text(str(node_result.answer or "").strip())
                            if len(answer) > 1800:
                                answer = answer[:1799].rstrip() + "…"
                            output = {
                                "status": "failed" if node_result.error else "completed",
                                "answer": answer,
                                "error": node_result.error,
                                "turns": node_result.turns,
                                "tool_calls": node_result.tool_calls_total,
                                "tokens_used": dict(node_result.tokens_used),
                                "evidence": node_summaries[-8:],
                            }
                        except Exception as exc:  # noqa: BLE001 - node failure is a DAG result
                            output = {
                                "status": "failed",
                                "error": f"{type(exc).__name__}: {exc}",
                                "evidence": node_summaries[-8:],
                            }
                        finally:
                            if node_provider is not None:
                                await node_provider.close()

                        emit({
                            "kind": "trace",
                            "name": "planner",
                            "status": "error" if output.get("status") == "failed" else "ok",
                            "phase": "planning",
                            "code": "planner_node_finished",
                            "summary": (
                                f"DAG 节点 {task.id} 执行失败"
                                if output.get("status") == "failed"
                                else f"DAG 节点 {task.id} 已完成并产出只读证据"
                            ),
                            "detail": {
                                "status": output.get("status"),
                                "turns": output.get("turns", 0),
                                "tool_calls": output.get("tool_calls", 0),
                                "error": output.get("error"),
                            },
                        })
                        return output

                    dag_result = await execute_dag(
                        plan,
                        run_node,
                        max_concurrency=policy.max_concurrency,
                        include_dependency_outputs=True,
                    )
                    output_summaries: dict[str, dict[str, Any]] = {}
                    token_totals: dict[str, int] = {}
                    for task_id, output in dag_result.outputs.items():
                        bounded = {
                            key: output.get(key)
                            for key in ("status", "answer", "error", "turns", "tool_calls", "evidence")
                            if key in output
                        }
                        output_summaries[task_id] = bounded
                        for key, value in (output.get("tokens_used") or {}).items():
                            if isinstance(value, (int, float)):
                                token_totals[key] = token_totals.get(key, 0) + int(value)
                    execution = {
                        "status": dag_result.status,
                        "plan_name": plan.name,
                        "completed": list(dag_result.completed),
                        "failed": list(dag_result.failed),
                        "skipped": list(dag_result.skipped),
                        "attempts": dict(dag_result.attempts),
                        "outputs": output_summaries,
                        "tokens_used": token_totals,
                        "max_concurrency": policy.max_concurrency,
                    }
                    finished = {
                        "kind": "trace",
                        "name": "planner",
                        "status": "error" if dag_result.status == "failed" else "ok",
                        "phase": "planning",
                        "code": "planner_execution_finished",
                        "summary": (
                            f"只读 DAG 执行结束：完成 {len(dag_result.completed)} 个节点"
                            + (f"，失败 {len(dag_result.failed)} 个" if dag_result.failed else "")
                            + (f"，跳过 {len(dag_result.skipped)} 个" if dag_result.skipped else "")
                        ),
                        "detail": execution,
                    }
                    events.append(finished)
                    if on_event is not None:
                        on_event(finished)
                    evidence_json = json.dumps(
                        execution,
                        ensure_ascii=False,
                        default=str,
                        separators=(",", ":"),
                    )
                    if len(evidence_json) > 14_000:
                        evidence_json = evidence_json[:13_999].rstrip() + "…"
                    messages.append(system_msg(
                        "[计划执行证据]\n"
                        "下面是受白名单、依赖和并发约束的只读 DAG 结果。它是辅助证据，关键结论仍需结合原始任务和当前工具结果复核。\n"
                        + evidence_json
                    ))
                    return execution

                async def prepare_planner() -> None:
                    """Ask for a bounded plan only when the task merits a preflight."""

                    nonlocal planner_result, planner_usage, planner_policy, planner_execution
                    if not planner_requested:
                        return
                    fallback_name = "inspect_summarize" if not allow_changes else "inspect_implement_verify"
                    allowed_tools = set(DEFAULT_ALLOWED_TOOLS)
                    if not allow_network:
                        allowed_tools.discard("web_search")
                        allowed_tools.discard("webfetch")
                    policy = PlannerPolicy(
                        max_nodes=8,
                        max_depth=6,
                        max_concurrency=min(4, max(1, int(getattr(self.config, "max_concurrent_tasks", 4)))),
                        allowed_tools=frozenset(allowed_tools),
                    )
                    planner_policy = policy
                    planner_prompt = build_planner_prompt(
                        message,
                        workspace=str(workspace),
                        evidence="\n".join(
                            f"- {hit.path}: {hit.reason}"
                            for hit in evidence_hits[:8]
                        ),
                    )
                    planner_messages = [
                        system_msg(PLANNER_SYSTEM_PROMPT),
                        user_msg(_multimodal_content(planner_prompt, attachments)),
                    ]
                    planner_started = {
                        "kind": "trace",
                        "name": "planner",
                        "status": "ok",
                        "phase": "planning",
                        "code": "planner_started",
                        "summary": "复杂任务已进入结构化规划预检，运行时仍保留最终控制权",
                        "detail": {
                            "trigger": "explicit" if payload.get("planner_requested") else "complexity_or_batch",
                            "complexity": complexity.snapshot(),
                            "fallback": fallback_name,
                            "policy": {
                                "max_nodes": policy.max_nodes,
                                "max_depth": policy.max_depth,
                                "max_concurrency": policy.max_concurrency,
                                "allowed_tools": sorted(policy.allowed_tools),
                            },
                        },
                    }
                    events.append(planner_started)
                    if on_event is not None:
                        on_event(planner_started)
                    try:
                        response = await chat_with_cancellation(
                            provider,
                            messages=planner_messages,
                            tools=None,
                            on_delta=None,
                            cancel_event=cancel_event,
                            timeout_seconds=runtime_state.budget.remaining_seconds(),
                        )
                        usage = dict(getattr(response, "usage", {}) or {})
                        if not usage.get("total_tokens"):
                            prompt_tokens = max(
                                sum(len(str(item.get("content") or "")) for item in planner_messages) // 4,
                                1,
                            )
                            completion_tokens = max(len(str(getattr(response, "text", "") or "")) // 4, 1)
                            usage = {
                                "prompt_tokens": prompt_tokens,
                                "completion_tokens": completion_tokens,
                                "total_tokens": prompt_tokens + completion_tokens,
                                "estimated": True,
                            }
                        runtime_state.budget.record_usage(usage)
                        planner_usage = usage
                        if on_usage is not None:
                            on_usage({"stage": "planner", **usage})
                        planner_result = parse_planner_response(
                            str(getattr(response, "text", "") or ""),
                            fallback_name=fallback_name,
                            policy=policy,
                        )
                    except (BudgetExceeded, AgentCancelled):
                        raise
                    except Exception as exc:  # noqa: BLE001 - planning failure is a safe fallback
                        planner_result = build_plan(
                            None,
                            fallback_name=fallback_name,
                            policy=policy,
                        )
                        planner_result = PlanBuildResult(
                            planner_result.plan,
                            "fixed_fallback",
                            f"规划器调用失败: {type(exc).__name__}",
                        )
                    detail = planner_result.to_dict() if planner_result is not None else {}
                    if planner_result is not None and planner_result.source == "dynamic_model":
                        event = {
                            "kind": "trace",
                            "name": "planner",
                            "status": "ok",
                            "phase": "planning",
                            "code": "planner_dynamic_ready",
                            "summary": f"模型已生成受约束执行计划，共 {len(planner_result.plan.tasks)} 个节点",
                            "detail": detail,
                        }
                        messages.append(system_msg(
                            "[运行时结构化执行计划]\n"
                            "以下计划已经过服务端 schema、依赖、深度、并发和工具白名单校验。"
                            "它只是公开执行提示；如果新证据改变目标，主 Agent 必须重新规划。\n"
                            + json.dumps(planner_result.plan.to_dict(), ensure_ascii=False, separators=(",", ":"))
                        ))
                        events.append(event)
                        if on_event is not None:
                            on_event(event)
                        if not allow_changes:
                            planner_execution = await execute_dynamic_plan(planner_result.plan, policy)
                    else:
                        event = {
                            "kind": "trace",
                            "name": "planner",
                            "status": "error",
                            "phase": "planning",
                            "code": "planner_preflight_fallback",
                            "summary": "模型计划未通过安全校验，已回退到固定执行模板",
                            "detail": detail,
                        }
                        events.append(event)
                        if on_event is not None:
                            on_event(event)

                await prepare_planner()

                def record_review_usage(decision: CompletionDecision, target: TurnResult) -> bool:
                    usage = dict(decision.usage or {})
                    if not usage:
                        return True
                    try:
                        runtime_state.budget.record_usage(usage)
                    except BudgetExceeded as exc:
                        target.error = f"Agent 预算超限: {exc}"
                        target.answer = f"任务未完成：{target.error}"
                        return False
                    usage_event = {"kind": "completion_judge", **usage}
                    target.usage_by_turn.append(usage_event)
                    add_usage_totals(target.tokens_used, usage)
                    if on_usage is not None:
                        on_usage(usage_event)
                    return True

                while True:
                    enter_runtime_node("inspect" if repair_attempts == 0 else "repair", "inspect" if repair_attempts == 0 else "repair")
                    current = await run_agent(
                        provider,
                        registry,
                        messages,
                        max_turns=self.config.max_turns,
                        compact_threshold=self.config.compact_threshold,
                        # A recovery attempt is deliberately non-streaming: an
                        # interrupted stream may have already reached the UI,
                        # so an atomic retry avoids duplicated visible text.
                        on_stream=on_stream if provider_recoveries == 0 else None,
                        on_tool=on_tool,
                        on_usage=on_usage,
                        on_context=on_context,
                        on_compaction=on_compaction,
                        on_trace=on_trace,
                        context_limit_tokens=int(getattr(self.config, "context_window_tokens", 300_000)),
                        should_allow=should_allow,
                        should_cancel=(cancel_event.is_set if cancel_event is not None else None),
                        cancel_event=cancel_event,
                        budget=runtime_state.budget,
                        runtime_state=runtime_state,
                        require_recovery_inspection=(agent_recoveries > 0 or repair_attempts > 0),
                        vision_context=vision_context,
                        hooks=hook_runner,
                    )
                    aggregate = _merge_turn_results(aggregate, current)
                    writes = any(event.get("write") for event in events if isinstance(event, dict))
                    if current.cancelled:
                        break

                    is_transient = getattr(OpenAICompatibleProvider, "is_transient_failure", None)
                    if current.error and callable(is_transient) and is_transient(current.error):
                        if provider_recoveries >= max_provider_recoveries:
                            break
                        try:
                            runtime_state.budget.record_retry()
                        except BudgetExceeded as exc:
                            aggregate.error = f"Agent 预算超限: {exc}"
                            aggregate.answer = f"任务未完成：{aggregate.error}"
                            break
                        provider_recoveries += 1
                        recovery_protocol = await recreate_provider_after_failure()
                        recovery_event = {
                            "kind": "trace",
                            "name": "provider",
                            "status": "error",
                            "phase": "planning",
                            "code": "task_provider_recovery",
                            "summary": f"模型网关暂时不可用，已开始第 {provider_recoveries} 次安全恢复",
                            "detail": {
                                "retry": provider_recoveries,
                                "retry_limit": max_provider_recoveries,
                                "next_mode": "non_streaming",
                                "protocol": recovery_protocol,
                            },
                        }
                        events.append(recovery_event)
                        if on_event is not None:
                            on_event(recovery_event)
                        continue

                    stagnation_error = bool(
                        current.error
                        and (
                            "停滞保护触发" in str(current.error)
                            or "错误路径恢复阶段" in str(current.error)
                        )
                    )
                    if stagnation_error and agent_recoveries < max_agent_recoveries:
                        try:
                            runtime_state.budget.record_retry()
                        except BudgetExceeded as exc:
                            aggregate.error = f"Agent 预算超限: {exc}"
                            aggregate.answer = f"任务未完成：{aggregate.error}"
                            break
                        agent_recoveries += 1
                        recovery_event = {
                            "kind": "trace",
                            "name": "repair",
                            "status": "error",
                            "phase": "repair",
                            "code": "task_stagnation_recovery",
                            "summary": (
                                f"检测到重复工具路径，已进入第 {agent_recoveries} 次错误恢复"
                            ),
                            "detail": {
                                "attempt": agent_recoveries,
                                "retry_limit": max_agent_recoveries,
                                "writes_seen": writes,
                                "strategy": "保留当前证据，先重新检查状态和 diff，再选择不同路径",
                            },
                        }
                        events.append(recovery_event)
                        if on_event is not None:
                            on_event(recovery_event)
                        messages.append(user_msg(
                            "[任务级错误恢复] 上一轮 Agent 因重复或无效工具路径暂停，任务还没有完成。"
                            "不要直接总结或重复相同调用。请回到最近一次有证据的状态，先检查当前工作区、"
                            "git diff 和相关文件；如果已有修改与目标不符，只修复本任务产生的偏差，"
                            "不要覆盖用户已有改动。取得新证据后换用不同工具或参数继续，并完成验证。"
                        ))
                        continue

                    # Provider, budget and permission errors remain hard
                    # failures.  A stagnation error after a write still gets a
                    # deterministic verification pass so the next repair step
                    # can work from objective evidence instead of stopping with
                    # an unverified partial edit.
                    if current.error and (
                        not writes
                        or current.error != verification_guard_error
                    ) and not (stagnation_error and writes):
                        break

                    verification = None
                    if writes:
                        enter_runtime_node("verify", "verify")
                        try:
                            verification_plan = await asyncio.to_thread(
                                build_verification_plan, workspace, changed_paths_from_events(events)
                            )
                            verification = await asyncio.to_thread(
                                verifier.run, workspace, plan=verification_plan,
                                allow_project_scripts=allow_changes and permission_mode != "plan",
                                cancel_event=cancel_event,
                            )
                        except (ValueError, OSError) as exc:
                            verification = VerificationResult(status="blocked", actionable_hint=f"验证配置不可用：{exc}")
                        verification_data = verification.to_dict()
                        verification_results.append(verification_data)
                        runtime_state.add_evidence({"type": "verification", **verification_data})
                        verification_event = verification.to_event()
                        events.append(verification_event)
                        if on_event is not None:
                            on_event(verification_event)
                        if verification.status == "cancelled":
                            aggregate.cancelled = True
                            aggregate.error = None
                            aggregate.answer = "任务已取消，自动验证已停止。"
                            break
                        if verification.status == "blocked":
                            aggregate.error = f"验证器被阻止：{verification.actionable_hint}"
                            aggregate.answer = f"任务未完成：{aggregate.error}"
                            break
                        if verification.status == "failed":
                            if repair_attempts >= max_repairs:
                                aggregate.error = f"验证失败，已达到 repair 上限 {max_repairs}"
                                aggregate.answer = (
                                    f"任务未完成：{aggregate.error}。\n\n"
                                    f"验证命令：{verification.command}\n{verification.output[-6000:]}"
                                )
                                break
                            try:
                                runtime_state.budget.record_retry()
                            except BudgetExceeded as exc:
                                aggregate.error = f"Agent 预算超限: {exc}"
                                aggregate.answer = f"任务未完成：{aggregate.error}"
                                break
                            repair_attempts += 1
                            scope = repair_scope(events, verification_data)
                            scope_event = {
                                "kind": "trace", "name": "repair", "status": "ok", "phase": "repair",
                                "code": "dependency_aware_repair_scope",
                                "summary": f"已将修复范围收敛到 {len(scope['repair_targets'])} 个有证据关联的文件",
                                "detail": scope,
                            }
                            events.append(scope_event)
                            if on_event is not None:
                                on_event(scope_event)
                            messages.append(user_msg(
                                "[验证器反馈] 自动验证没有通过。请只修复验证输出指出的问题，"
                                "优先重新检查下列有证据关联的文件；不要重做独立分支。完成后再次检查 diff 并运行验证。\n\n"
                                f"命令：{verification.command}\n"
                                f"失败测试：{', '.join(verification.failed_tests) or '未解析到测试名称'}\n"
                                f"关联文件：{', '.join(scope['repair_targets']) or '未记录到写入路径，先定位失败测试'}\n"
                                f"建议：{verification.actionable_hint}\n"
                                f"输出：{verification.output[-6000:]}"
                            ))
                            continue

                        # The verifier can recover the loop's provisional
                        # "verification required" error.  Do not let that
                        # implementation detail leak into a successful answer.
                        if aggregate.error == verification_guard_error:
                            aggregate.error = None
                            marker = "模型最后输出："
                            if marker in aggregate.answer:
                                aggregate.answer = aggregate.answer.rsplit(marker, 1)[-1].strip()
                        elif stagnation_error and verification.status in {"passed", "skipped"}:
                            aggregate.error = None
                        elif aggregate.error:
                            break

                    completion_review_attempt += 1
                    enter_runtime_node("review", "review")
                    decision = await judge_completion(
                        provider,
                        task=message,
                        answer=aggregate.answer if aggregate is not None else "",
                        events=events,
                        verification_results=verification_results,
                        allow_changes=allow_changes,
                        workspace=str(workspace),
                        cancel_event=cancel_event,
                        vision_context=vision_context,
                        messages=messages,
                    )
                    if cancel_event is not None and cancel_event.is_set():
                        if aggregate is None:
                            aggregate = TurnResult(answer="任务已取消。")
                        aggregate.cancelled = True
                        aggregate.error = "任务已取消"
                        aggregate.answer = "任务已取消。"
                        break
                    if aggregate is None:
                        aggregate = TurnResult(answer="模型没有返回结果")
                    aggregate.completion = decision.to_dict(include_usage=True)
                    runtime_state.add_evidence({"type": "completion_review", **aggregate.completion})
                    if not record_review_usage(decision, aggregate):
                        break
                    review_event = _completion_review_event(decision, completion_review_attempt)
                    events.append(review_event)
                    if on_event is not None:
                        on_event(review_event)

                    if decision.status == "complete":
                        break
                    if decision.status == "continue":
                        completion_continues += 1
                        if completion_continues > max_completion_continues:
                            aggregate.error = (
                                f"完成评估连续 {completion_continues} 轮要求继续但未收敛，已按上限停止；"
                                "请根据缺失项检查后重新提交任务"
                            )
                            aggregate.answer = f"任务未完成：{aggregate.error}"
                            capped_event = {
                                "kind": "trace",
                                "name": "completion_judge",
                                "status": "error",
                                "phase": "review",
                                "code": "completion_continue_capped",
                                "summary": "完成评估多轮要求继续但未收敛，已停止以避免无限重跑",
                                "detail": {
                                    "rounds": completion_continues,
                                    "limit": max_completion_continues,
                                    "missing": list(decision.missing),
                                    "next_action": decision.next_action,
                                },
                            }
                            events.append(capped_event)
                            if on_event is not None:
                                on_event(capped_event)
                            break
                        messages.append(user_msg(_completion_followup(decision)))
                        continue
                    if decision.status == "blocked":
                        reason = decision.rationale or "完成评估器无法确认任务可以继续"
                        aggregate.error = f"完成评估判定受阻：{reason}"
                        aggregate.answer = f"任务未完成：{aggregate.error}"
                        break

                    if decision.review_transient is False:
                        # The reviewer request was rejected on purpose (content
                        # policy, credentials, unsupported parameter), so the
                        # identical retry returns the identical answer. Asking
                        # the agent to redo all its work just to be reviewed
                        # again only burns a full run; stop and report the
                        # real cause instead.
                        detail = decision.error or "评审请求被模型端拒绝"
                        aggregate.error = f"完成评估请求被模型端拒绝：{detail}"
                        aggregate.answer = f"任务未完成：{aggregate.error}"
                        rejected_event = {
                            "kind": "trace",
                            "name": "completion_judge",
                            "status": "error",
                            "phase": "review",
                            "code": "completion_judge_rejected",
                            "summary": "完成评估请求被确定性拒绝，重跑 agent 不会改变结论，已停止",
                            "detail": {"error": detail},
                        }
                        events.append(rejected_event)
                        if on_event is not None:
                            on_event(rejected_event)
                        break

                    if completion_review_failures < 1:
                        completion_review_failures += 1
                        retry_event = {
                            "kind": "trace",
                            "name": "completion_judge",
                            "status": "error",
                            "phase": "review",
                            "code": "completion_judge_retry",
                            "summary": "完成评估暂时不可用，已要求 agent 再次自检",
                            "detail": {"error": decision.error or "invalid response"},
                        }
                        events.append(retry_event)
                        if on_event is not None:
                            on_event(retry_event)
                        messages.append(user_msg(
                            "[完成评估反馈] 完成评估服务暂时没有返回可解析结论。"
                            "请重新检查原始需求、相关文件和验证结果；如果还缺少工作，继续使用工具，"
                            "不要直接宣称完成；如果确实完成，请给出基于证据的简短总结。"
                        ))
                        continue

                    aggregate.error = "完成评估不可用，无法确认任务是否达到最终目标"
                    aggregate.answer = f"任务未完成：{aggregate.error}"
                    break
                final = aggregate or TurnResult(answer="模型没有返回结果", error="Agent 没有返回结果")
                if planner_result is not None:
                    planner_snapshot = planner_result.to_dict()
                    if planner_execution is not None:
                        planner_snapshot["execution"] = planner_execution
                    final.context = {**final.context, "planner": planner_snapshot}
                    final.metrics = {**final.metrics, "planner": planner_snapshot}
                    if planner_usage:
                        final.usage_by_turn.insert(0, {"stage": "planner", **planner_usage})
                        add_usage_totals(final.tokens_used, planner_usage)
                    if planner_execution and planner_execution.get("tokens_used"):
                        final.usage_by_turn.insert(1 if planner_usage else 0, {
                            "stage": "planner_dag",
                            **dict(planner_execution["tokens_used"]),
                        })
                        add_usage_totals(final.tokens_used, planner_execution["tokens_used"])
                final.metrics.update(cache_summary(final.tokens_used))
                return final
            finally:
                await provider.close()

        result = asyncio.run(execute())
        completion_status = str((result.completion or {}).get("status") or "")
        judge_unavailable = (
            completion_status == "unknown"
            and bool(result.error)
            and str(result.error).startswith("完成评估")
        )
        completion_guard = None
        if str(payload.get("task_kind") or "") != "subtask" and completion_status != "complete":
            completion_guard = _completion_guard_message(
                message,
                result,
                events,
                allow_changes,
                ignore_result_error=judge_unavailable,
            )
        if completion_guard:
            original_answer = str(result.answer or "").strip()
            result.error = completion_guard
            result.answer = (
                f"任务未完成：{completion_guard}。"
                + (f"\n\n模型最后输出：{original_answer}" if original_answer else "")
            )
        runtime_status = "cancelled" if result.cancelled else "failed" if result.error else "completed"
        runtime_state.finish(runtime_status, result.error)
        result.metrics = {
            **runtime_state.metrics(),
            "repair_attempts": repair_attempts,
            "provider_recoveries": provider_recoveries,
            "agent_recoveries": agent_recoveries,
            "verification_runs": len(verification_results),
            "verification_status": verification_results[-1].get("status") if verification_results else "none",
            "verifications": verification_results,
        }
        if planner_result is not None:
            planner_snapshot = planner_result.to_dict()
            if planner_execution is not None:
                planner_snapshot["execution"] = planner_execution
            result.metrics["planner"] = planner_snapshot
        store.save(messages)
        return {
            "answer": result.answer,
            "error": result.error,
            "turns": result.turns,
            "tool_calls_total": result.tool_calls_total,
            "denied_tools": result.denied_tools,
            "tokens_used": result.tokens_used,
            "context": result.context,
            "usage_by_turn": result.usage_by_turn,
            "compaction_events": result.compaction_events,
            "metrics": result.metrics,
            "completion": dict(result.completion),
            "events": events,
            "session_id": session_id,
            "cancelled": result.cancelled,
            "completion_guard": completion_guard,
        }

    def file_preview(self, raw_path: str) -> dict[str, Any]:
        editor = Editor(self.workspace)
        result = build_registry(editor).execute(ToolCall("read_file", {"path": raw_path, "limit": 500}))
        return {"status": result.status, "summary": result.summary, "content": result.render(), "path": raw_path}

    def changes(self, raw_path: str | None = None) -> dict[str, Any]:
        inspector = ChangeInspector(self.workspace)
        if raw_path:
            return inspector.diff(raw_path)
        return inspector.summary()

    def audit_export(
        self,
        *,
        limit: int = 500,
        levels: list[str] | None = None,
        min_level: str | None = None,
    ) -> dict[str, Any]:
        """Export redacted local editor audit entries for the active workspace.

        M8-T5 filtering: ``levels`` is an explicit allow-list, ``min_level`` a
        severity floor (``info`` < ``notice`` < ``warning``). Filtering runs
        before the ``limit`` slice so a filtered query still returns up to
        ``limit`` matches instead of a filtered remainder of the last lines.
        """
        keep = _audit_level_filter(levels=levels, min_level=min_level)
        audit_path = self.workspace / ".minicc" / "audit.jsonl"
        empty = {
            "workspace_path": str(self.workspace),
            "entries": [],
            "count": 0,
            "total": 0,
        }
        if not audit_path.is_file():
            return empty
        try:
            lines = audit_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise ValueError(f"无法读取审计记录: {exc}") from exc
        matches: list[dict[str, Any]] = []
        for line in lines:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(item, dict):
                continue
            level = str(item.get("level") or "") or audit_level(
                str(item.get("action") or ""), str(item.get("detail") or "")
            )
            if keep is not None and level not in keep:
                continue
            safe = {
                key: redact_text(str(item.get(key) or ""))[0]
                for key in ("timestamp", "action", "path", "detail", "before_digest", "after_digest")
            }
            safe["level"] = level
            matches.append(safe)
        capped = matches[-max(1, min(limit, 2000)):]
        return {
            "workspace_path": str(self.workspace),
            "entries": capped,
            "count": len(capped),
            "total": len(matches),
        }

    def metrics(self, *, limit: int = 500, workspace_path: str | None = None) -> dict[str, Any]:
        """Aggregate token/cost metrics over the task index (M8-T5).

        The totals are summed from each task's own ``tokens_used`` /
        ``cost_usd`` snapshot fields, so ``/api/metrics`` can never disagree
        with ``GET /api/tasks/<id>`` — a re-derivation from raw usage would be
        free to drift the moment pricing or usage shapes change. Unpriced
        models contribute tokens but are counted separately instead of being
        silently billed at zero.

        Only root tasks are summed: a batch or auto-orchestration parent rolls
        its subtasks' usage into its own snapshot, so adding the subtask rows
        on top would bill the same model calls twice. ``subtask_rows`` keeps
        the excluded rows countable instead of invisible. The fold runs on
        every path that finishes a parent — merged, failed, cancelled or
        crashed — and exactly once per parent, which is what makes "summed from
        each task's own snapshot fields" above a fact rather than a hope.
        """
        rows = self.tasks.list(limit=max(1, min(limit, 2000)), workspace_path=workspace_path)
        roots = [row for row in rows if not row.get("parent_id")]
        subtask_rows = len(rows) - len(roots)
        usage: dict[str, int] = {}
        by_model: dict[str, dict[str, Any]] = {}
        by_status: dict[str, int] = {}
        cost_total = 0.0
        unpriced_tasks = 0
        priced_tasks = 0
        durations: list[float] = []
        for row in roots:
            add_usage_totals(usage, row.get("tokens_used") or {})
            model = str(row.get("model") or "unknown")
            bucket = by_model.setdefault(
                model,
                {"tokens": {}, "cost_usd": 0.0, "tasks": 0, "priced": True},
            )
            add_usage_totals(bucket["tokens"], row.get("tokens_used") or {})
            bucket["tasks"] += 1
            status = str(row.get("status") or "unknown")
            by_status[status] = by_status.get(status, 0) + 1
            cost = row.get("cost_usd")
            if cost is None:
                bucket["priced"] = False
                unpriced_tasks += 1
            else:
                value = float(cost)
                bucket["cost_usd"] += value
                cost_total += value
                priced_tasks += 1
            duration = row.get("duration_seconds")
            if isinstance(duration, (int, float)) and not isinstance(duration, bool):
                durations.append(float(duration))
        for bucket in by_model.values():
            if not bucket["priced"]:
                bucket["cost_usd"] = None
            del bucket["priced"]
        return {
            "schema_version": "minicc.metrics.v1",
            "workspace_path": str(workspace_path) if workspace_path else None,
            # Without an explicit filter the index spans every workspace in
            # the shared task store, so the payload must not name one of them
            # as if the totals belonged to it.
            "scope": str(workspace_path) if workspace_path else "all_workspaces",
            "generated_at": _iso(time.time()),
            "task_count": len(roots),
            "subtask_rows": subtask_rows,
            "tasks_by_status": by_status,
            "priced_tasks": priced_tasks,
            "unpriced_tasks": unpriced_tasks,
            "usage": usage,
            "cost_usd": round(cost_total, 6),
            "by_model": by_model,
            "duration_seconds": {
                "total": round(sum(durations), 3),
                "average": round(sum(durations) / len(durations), 3) if durations else 0.0,
                "max": round(max(durations), 3) if durations else 0.0,
            },
        }

    def shutdown(self) -> None:
        # Unblock any agent threads parked on an approval prompt first, so
        # task workers can drain instead of hitting the 60s auto-deny.
        self._deny_all_approvals()
        self.tasks.shutdown()
        with self._mcp_guard:
            for manager in {item for item in self._mcp_by_workspace.values() if item is not None}:
                manager.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="minicc-web", description="启动 minicc 本地 Web 工作台")
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--token",
        default=None,
        help="Web API 访问 token；默认读取 MINICC_WEB_TOKEN 或工作区 .minicc/web_token.json",
    )
    parser.add_argument(
        "--no-auth",
        action="store_true",
        help="即使绑定非回环地址也关闭 token 认证（不推荐，仅限隔离网络）",
    )
    args = parser.parse_args(argv)
    configure_logging()
    workspace = args.workspace.expanduser().resolve()
    if not workspace.is_dir():
        parser.error(f"工作区不是目录: {workspace}")
    try:
        config = load_config(workspace=workspace)
    except ConfigError as exc:
        parser.error(str(exc))
    explicit_token = args.token
    try:
        token, created = load_or_create_token(workspace, explicit_token)
    except WebAuthError as exc:
        parser.error(str(exc))
    required = not is_loopback_host(args.host) and not args.no_auth
    auth = WebAuth(token, required=required)
    # M8-T5: the web token must not be able to appear in a log line either.
    register_secret(token)
    service = AgentService(workspace, config)
    server = MiniccHTTPServer((args.host, args.port), service, auth=auth)
    cli_out(f"minicc web: http://{args.host}:{args.port}/")
    cli_out(f"workspace: {workspace}")
    if required:
        cli_out("auth: required (non-loopback bind)")
        cli_out(f"token: {token}")
        if not explicit_token and created:
            cli_out(f"token saved to: {token_store_path(workspace)}")
    else:
        cli_out("auth: open (loopback bind, token accepted but not required)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        cli_out("\nminicc web stopped")
    finally:
        service.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
