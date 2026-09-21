"""HTTP server layer for the minicc web workbench.

Extracted from ``minicc/web.py`` (stage 0.3 modularization): the request
handler, SSE streaming, and static file serving live here, while the agent
service stays in ``web.py``. This module must not import ``web.py`` at module
level — the dependency points one way only (web -> webserver) to keep the
import graph acyclic.
"""

from __future__ import annotations

import json
import mimetypes
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from .allowlist import AllowlistError
from .changes import ChangeError
from .mcp import McpError
from .session import SessionError
from .snapshots import SnapshotError
from .task_store import TERMINAL_TASK_STATUSES
from .static_assets import asset_response
from .webauth import WebAuth, cors_origin, origin_allowed

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # typing-only; keeps web -> webserver a one-way runtime edge
    from .web import AgentService
from .worktree import WorktreeError

STATIC_ROOT = Path(__file__).resolve().parent.parent / "web"
TASK_STREAM_TIMEOUT = 15 * 60
MAX_SSE_CONNECTIONS = 32
SSE_WRITE_TIMEOUT = 20.0
MAX_BODY_BYTES = 18_000_000

class MiniccHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        service: AgentService,
        auth: WebAuth | None = None,
    ) -> None:
        super().__init__(address, MiniccRequestHandler)
        self.service = service
        self.auth = auth
        worker_count = max(1, int(getattr(service.config, "max_concurrent_tasks", 8)))
        # A slow browser connection must not consume an unbounded number of
        # request threads. The task event log remains the recovery source.
        self.sse_slots = threading.BoundedSemaphore(
            max(4, min(MAX_SSE_CONNECTIONS, worker_count * 4))
        )


class MiniccRequestHandler(BaseHTTPRequestHandler):
    server: MiniccHTTPServer
    server_version = "minicc-web/0.2"
    protocol_version = "HTTP/1.1"

    def handle(self) -> None:
        # A browser can close an SSE or in-flight request while switching
        # sessions. Treat that as normal cancellation instead of logging a
        # traceback from the socket read loop.
        try:
            super().handle()
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            self.close_connection = True

    #: M3-T2: EventSource cannot send headers, so the SSE routes carry the
    #: bearer token in the query string. It must never reach the log file.
    _SECRET_QUERY_RE = re.compile(
        r"(?i)([?&](?:token|access_token|api_key|key)=)[^&\s\"']+"
    )

    def log_message(self, format: str, *args: object) -> None:
        # Keep the terminal useful without logging request bodies or secrets.
        rendered = f"{self.command} {self.path} - {format % args}"
        redacted = self._SECRET_QUERY_RE.sub(r"\1***", rendered)
        print(f"[web] {redacted}")

    def _request_origin(self) -> str | None:
        return self.headers.get("Origin") or None

    def _cors_headers(self) -> list[tuple[str, str]]:
        # Only loopback origins may read the API cross-origin; same-origin
        # pages never send Origin on normal fetches and need nothing here.
        origin = cors_origin(self._request_origin())
        if not origin:
            return []
        return [
            ("Access-Control-Allow-Origin", origin),
            ("Vary", "Origin"),
        ]

    def _origin_allowed_for_state_change(self) -> bool:
        """M3-T1: state-changing methods require a loopback/same-origin Origin.

        `WebAuth` alone cannot stop a cross-site POST: with the default
        loopback binding `required=False`, `check()` returns True for any
        caller, so an attacker page could drive `/api/tasks` with
        `permission_mode: "yolo"`. Browsers always attach Origin on cross-site
        POSTs; curl/scripts that omit it entirely are still allowed.
        """
        origin = self._request_origin()
        if not origin:
            return True  # non-browser client (curl, SDK, tests)
        return origin_allowed(origin)

    def _deny_cross_origin(self) -> None:
        body = json.dumps(
            {"error": "forbidden", "detail": "跨站状态变更请求已拒绝"}, ensure_ascii=False
        ).encode("utf-8")
        try:
            self.send_response(403)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except (OSError, BrokenPipeError, ConnectionAbortedError):
            self.close_connection = True

    def _authorized(self, query: dict[str, list[str]] | None = None) -> bool:
        auth = self.server.auth
        if auth is None:
            return True
        query_token = ""
        if query:
            query_token = (query.get("token") or [""])[0]
        return auth.check_headers(self.headers, query_token or None)

    def _deny_auth(self) -> None:
        body = json.dumps(
            {"error": "unauthorized", "auth_required": True}, ensure_ascii=False
        ).encode("utf-8")
        try:
            self.send_response(401)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("WWW-Authenticate", "Bearer")
            self.send_header("Cache-Control", "no-store")
            for name, value in self._cors_headers():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError):
            return

    def _json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for name, value in self._cors_headers():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError):
            # The browser may cancel a stale synchronous request after the UI
            # has moved to the task-polling API. It must not create a second
            # traceback while trying to report the first failure.
            return

    def do_OPTIONS(self) -> None:
        headers = self._cors_headers()
        if not headers:
            # Same-origin pages never trigger preflight; anything else must
            # not learn that the service exists.
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        headers.extend(
            [
                ("Access-Control-Allow-Headers", "Content-Type, Authorization"),
                ("Access-Control-Allow-Methods", "GET, POST, OPTIONS"),
            ]
        )
        self.send_response(204)
        for name, value in headers:
            self.send_header(name, value)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        path = parsed.path
        if path == "/api/health":
            self._json({"ok": True, "service": "minicc"})
            return
        if path.startswith("/api/"):
            # Health stays open; every other API route requires the token when
            # auth is enabled. EventSource passes its token via query.
            if not self._authorized(parse_qs(parsed.query)):
                self._deny_auth()
                return
        if path == "/api/workspace":
            self._json(self.server.service.workspace_info())
            return
        if path == "/api/models":
            self._json(self.server.service.list_models())
            return
        if path == "/api/commands":
            self._json(self.server.service.list_commands())
            return
        if path == "/api/history/search":
            query = parse_qs(parsed.query)
            raw_query = (query.get("q") or [""])[0].strip()
            if not raw_query:
                self._json({"error": "缺少搜索关键词 q"}, 400)
                return
            try:
                limit = max(1, min(100, int((query.get("limit") or ["50"])[0])))
            except ValueError:
                limit = 50
            workspace_filter = (query.get("workspace") or [""])[0] or None
            self._json(self.server.service.search_history(raw_query, limit=limit, workspace_path=workspace_filter))
            return
        if path == "/api/audit":
            query = parse_qs(parsed.query)
            try:
                limit = int((query.get("limit") or ["500"])[0])
            except ValueError:
                limit = 500
            self._json(self.server.service.audit_export(limit=limit))
            return
        if path == "/api/tasks":
            query = parse_qs(parsed.query)
            raw_limit = (query.get("limit") or ["100"])[0]
            try:
                limit = max(1, min(200, int(raw_limit)))
            except ValueError:
                limit = 100
            workspace_filter = (query.get("workspace") or [""])[0] or None
            include_details = (query.get("detail") or [""])[0].lower() in {"1", "true", "full"}
            self._json({
                "tasks": self.server.service.tasks.list(
                    limit=limit,
                    workspace_path=workspace_filter,
                    include_details=include_details,
                ),
                "summary_only": not include_details,
            })
            return
        if path.startswith("/api/tasks/") and path.endswith("/events"):
            task_id = unquote(path.removeprefix("/api/tasks/").removesuffix("/events")).strip("/")
            query = parse_qs(parsed.query)
            raw_after = (query.get("after") or [self.headers.get("Last-Event-ID", "0")])[0]
            try:
                after = max(0, int(raw_after))
            except ValueError:
                after = 0
            self._stream_task(task_id, after=after)
            return
        if path.startswith("/api/tasks/"):
            task_id = unquote(path.removeprefix("/api/tasks/")).strip("/")
            try:
                self._json(self.server.service.tasks.get(task_id))
            except KeyError:
                self._json({"error": "task not found"}, 404)
            return
        if path == "/api/file":
            raw_path = (parse_qs(parsed.query).get("path") or [""])[0]
            try:
                self._json(self.server.service.file_preview(raw_path))
            except Exception as exc:  # noqa: BLE001 - stable read-only API error
                self._json({"error": str(exc)}, 400)
            return
        if path == "/api/files":
            query = parse_qs(parsed.query)
            raw_path = (query.get("path") or [""])[0]
            raw_depth = (query.get("depth") or ["3"])[0]
            try:
                self._json(self.server.service.file_tree(raw_path, depth=int(raw_depth)))
            except (ValueError, OSError) as exc:
                self._json({"error": str(exc)}, 400)
            return
        if path == "/api/changes":
            try:
                self._json(self.server.service.changes())
            except ChangeError as exc:
                self._json({"error": str(exc)}, 400)
            return
        if path == "/api/diff":
            raw_path = (parse_qs(parsed.query).get("path") or [""])[0]
            try:
                self._json(self.server.service.changes(raw_path))
            except ChangeError as exc:
                self._json({"error": str(exc)}, 400)
            return
        if path == "/api/worktrees":
            try:
                self._json({"worktrees": self.server.service.worktrees.list()})
            except WorktreeError as exc:
                self._json({"error": str(exc)}, 400)
            return
        if path == "/api/mcp":
            self._json(self.server.service.mcp.status() if self.server.service.mcp else {"configured": 0, "error": self.server.service.mcp_error})
            return
        if path == "/api/allowlist":
            query = parse_qs(parsed.query)
            session_id = (query.get("session_id") or [""])[0].strip()
            try:
                self._json(self.server.service.get_allowlist(session_id))
            except (ValueError, AllowlistError) as exc:
                self._json({"error": str(exc)}, 400)
            return
        if path == "/api/permissions":
            self._json(self.server.service.permissions_status())
            return
        if path == "/favicon.ico":
            self._serve_static("/favicon.svg")
            return
        self._serve_static(path)

    def _stream_task(self, task_id: str, *, after: int = 0) -> None:
        """Send one initial snapshot, then replayable incremental task events."""
        try:
            self.server.service.tasks.get(task_id)
        except KeyError:
            self._json({"error": "task not found"}, 404)
            return

        if not self.server.sse_slots.acquire(blocking=False):
            self._json(
                {
                    "error": "实时任务连接过多，请稍后重试或使用任务查询接口。",
                    "retryable": True,
                },
                429,
            )
            return

        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-transform")
            self.send_header("Connection", "keep-alive")
            for name, value in self._cors_headers():
                self.send_header(name, value)
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            # Like Codex's bounded outbound queue, disconnect a client that
            # cannot accept data instead of blocking the handler indefinitely.
            self.connection.settimeout(SSE_WRITE_TIMEOUT)

            last_heartbeat = time.monotonic()
            deadline = time.monotonic() + TASK_STREAM_TIMEOUT
            cursor = max(0, int(after or 0))

            # Keep the original default SSE message for clients that only
            # understand ``onmessage``. New clients consume named events
            # below and can reconnect with the returned event cursor.
            if cursor == 0:
                snapshot = self.server.service.tasks.get(task_id)
                payload = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
                self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                self.wfile.flush()
                cursor = int(snapshot.get("event_cursor") or 0)
                if snapshot.get("status") in TERMINAL_TASK_STATUSES:
                    return
            while time.monotonic() < deadline:
                events, replay_gap = self.server.service.tasks.events(task_id, after=cursor, timeout=10.0)
                if replay_gap:
                    snapshot = self.server.service.tasks.get(task_id)
                    payload = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
                    self.wfile.write(
                        f"event: resync\ndata: {payload}\n\n".encode("utf-8")
                    )
                    self.wfile.flush()
                    cursor = int(snapshot.get("event_cursor") or cursor)
                    last_heartbeat = time.monotonic()
                    if snapshot.get("status") in TERMINAL_TASK_STATUSES:
                        break
                    continue
                terminal = False
                for event in events:
                    payload = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
                    self.wfile.write(
                        f"event: task_event\nid: {event.get('sequence', cursor)}\ndata: {payload}\n\n".encode("utf-8")
                    )
                    cursor = max(cursor, int(event.get("sequence") or cursor))
                    terminal = terminal or (
                        event.get("kind") == "status"
                        and str((event.get("payload") or {}).get("status") or "") in TERMINAL_TASK_STATUSES
                    )
                if events:
                    self.wfile.flush()
                    last_heartbeat = time.monotonic()
                elif time.monotonic() - last_heartbeat >= 10:
                    self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
                    last_heartbeat = time.monotonic()
                if not events:
                    # A reconnect can start after the terminal status event.
                    # Do not hold the HTTP socket open until the stream
                    # deadline in that case.
                    latest = self.server.service.tasks.get(task_id)
                    if latest.get("status") in TERMINAL_TASK_STATUSES:
                        break
                if terminal:
                    break
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, KeyError, OSError):
            # The browser may close the stream after a task is complete or when
            # it falls back to polling; neither case should create a traceback.
            return
        finally:
            self.server.sse_slots.release()
            # HTTP/1.1 otherwise keeps the connection alive after the terminal
            # snapshot, leaving simple clients waiting for a content length.
            self.close_connection = True

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        try:
            size = int(self.headers.get("Content-Length", "0"))
            # Drain the request body before any early return so HTTP/1.1
            # keep-alive framing stays consistent. Otherwise the server closes
            # with unread request bytes in flight and Windows clients see a
            # reset (ConnectionAbortedError) instead of the 403 body.
            raw = self.rfile.read(size) if 0 < size <= MAX_BODY_BYTES else b""
            # M3-T1: reject cross-site state changes before doing any work.
            if not self._origin_allowed_for_state_change():
                self._deny_cross_origin()
                return
            if size <= 0 or size > MAX_BODY_BYTES:
                raise ValueError("请求体大小非法")
            if not self._authorized():
                # The body is already drained above, so rejecting here keeps the
                # connection framing intact.
                self._deny_auth()
                return
            payload = json.loads(raw.decode("utf-8"))
            if path == "/api/rpc":
                if not isinstance(payload, (dict, list)):
                    raise ValueError("RPC 请求体必须是 JSON 对象或数组")
                response = self.server.service.rpc_dispatcher.dispatch(payload)
                if response is None:
                    self.send_response(204)
                    self.send_header("Content-Length", "0")
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                else:
                    self._json(response)
                return
            if not isinstance(payload, dict):
                raise ValueError("请求体必须是 JSON 对象")
            if path == "/api/chat":
                self._json(self.server.service.chat(payload))
                return
            if path == "/api/tasks":
                self._json(self.server.service.tasks.submit(payload), 202)
                return
            if path == "/api/tasks/batch":
                self._json(self.server.service.tasks.submit_batch(payload), 202)
                return
            if path.endswith("/resume") and path.startswith("/api/tasks/"):
                task_id = unquote(path.removeprefix("/api/tasks/").removesuffix("/resume")).strip("/")
                self._json(self.server.service.tasks.resume(task_id), 202)
                return
            if path.endswith("/cancel") and path.startswith("/api/tasks/"):
                task_id = unquote(path.removeprefix("/api/tasks/").removesuffix("/cancel")).strip("/")
                self._json(self.server.service.tasks.cancel(task_id))
                return
            if path == "/api/workspace/select":
                raw_path = payload.get("path")
                if not isinstance(raw_path, str):
                    raise ValueError("path 不能为空")
                self._json(self.server.service.switch_workspace(raw_path))
                return
            if path == "/api/sessions/rewind":
                session_id = payload.get("session_id")
                if not isinstance(session_id, str):
                    raise ValueError("session_id 不能为空")
                raw_user = payload.get("user_index")
                if raw_user is not None:
                    try:
                        user_index = int(raw_user)
                    except (TypeError, ValueError) as exc:
                        raise ValueError("user_index 必须是整数") from exc
                    self._json(self.server.service.rewind_session(session_id, user_index=user_index))
                    return
                raw_keep = payload.get("keep_messages")
                try:
                    keep_messages = int(raw_keep)
                except (TypeError, ValueError) as exc:
                    raise ValueError("keep_messages 必须是整数") from exc
                self._json(self.server.service.rewind_session(session_id, keep_messages))
                return
            if path == "/api/workspace/restore":
                task_id = payload.get("task_id")
                if not isinstance(task_id, str) or not task_id.strip():
                    raise ValueError("task_id 不能为空")
                self._json(self.server.service.restore_task_snapshot(task_id.strip()))
                return
            if path == "/api/allowlist":
                session_id = payload.get("session_id")
                if not isinstance(session_id, str):
                    raise ValueError("session_id 不能为空")
                self._json(self.server.service.set_allowlist(session_id, payload))
                return
            if path == "/api/approval":
                # M7-T3: the user answered a pending approval_request frame.
                request_id = payload.get("request_id")
                decision = payload.get("decision")
                if not isinstance(request_id, str) or not request_id.strip():
                    raise ValueError("request_id 不能为空")
                if not isinstance(decision, str):
                    raise ValueError("decision 不能为空")
                self._json(self.server.service.resolve_approval(request_id.strip(), decision))
                return
            if path == "/api/worktrees":
                name = payload.get("name")
                if not isinstance(name, str):
                    raise ValueError("name 不能为空")
                self._json(self.server.service.worktrees.create(name, payload.get("branch")), 201)
                return
            if path == "/api/worktrees/remove":
                name = payload.get("name")
                if not isinstance(name, str):
                    raise ValueError("name 不能为空")
                self._json(self.server.service.worktrees.remove(name, bool(payload.get("force"))))
                return
            self._json({"error": "not found"}, 404)
        except KeyError:
            self._json({"error": "task not found"}, 404)
        except (ValueError, json.JSONDecodeError, SessionError, WorktreeError, SnapshotError, AllowlistError, McpError) as exc:
            self._json({"error": str(exc)}, 400)
        except Exception as exc:  # noqa: BLE001 - return a stable API error
            self._json({"error": f"agent failed: {type(exc).__name__}: {exc}"}, 500)

    def _serve_static(self, path: str) -> None:
        relative = unquote(path.lstrip("/")) or "index.html"
        try:
            accepts_gzip = False
            for part in self.headers.get("Accept-Encoding", "").split(","):
                encoding, *parameters = part.strip().lower().split(";")
                if encoding != "gzip":
                    continue
                quality = 1.0
                for parameter in parameters:
                    if parameter.strip().startswith("q="):
                        try:
                            quality = float(parameter.strip()[2:])
                        except ValueError:
                            quality = 0.0
                accepts_gzip = 0 < quality <= 1
            content, headers = asset_response(STATIC_ROOT, relative, accept_gzip=accepts_gzip)
        except (OSError, ValueError):
            self._json({"error": "not found"}, 404)
            return
        unchanged = self.headers.get("If-None-Match") == headers["ETag"]
        self.send_response(304 if unchanged else 200)
        for name, value in headers.items():
            self.send_header(name, value)
        if not unchanged:
            self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        if not unchanged:
            self.wfile.write(content)
