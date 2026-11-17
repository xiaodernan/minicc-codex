"""HTTP server layer for the minicc web workbench.

Extracted from ``minicc/web.py`` (stage 0.3 modularization): the request
handler, SSE streaming, and static file serving live here, while the agent
service stays in ``web.py``. This module must not import ``web.py`` at module
level — the dependency points one way only (web -> webserver) to keep the
import graph acyclic.
"""

from __future__ import annotations

import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from .allowlist import AllowlistError
from .changes import ChangeError
from .input_guard import require_text
from .logging_setup import get_logger, redact
from .mcp import McpError, mcp_absent_status
from .session import SessionError
from .snapshots import SnapshotError
from .task_store import TERMINAL_TASK_STATUSES
from .static_assets import asset_response, web_root
from .webauth import WebAuth, cors_origin, origin_allowed

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # typing-only; keeps web -> webserver a one-way runtime edge
    from .web import AgentService
from .worktree import WorktreeError

LOG = get_logger("web")
STATIC_ROOT = web_root()
TASK_STREAM_TIMEOUT = 15 * 60
MAX_SSE_CONNECTIONS = 32
SSE_WRITE_TIMEOUT = 20.0
MAX_BODY_BYTES = 18_000_000

#: M8-T508: the task API route prefix. Four routes (the events stream, the
#: task read, resume and cancel) each matched it with ``startswith`` and
#: stripped it with ``removeprefix`` - eight hand-spelled copies of one
#: fact. Change the prefix in the matcher but not the stripper and half of
#: each route's traffic 404s with nothing turning red. One definition, and
#: every matcher and stripper asks it.
TASKS_API_PREFIX = "/api/tasks/"

#: M8-T5: every API failure carries a machine-readable ``code`` so a client can
#: branch on it instead of pattern-matching a human-readable message (or
#: reading a bare 500). Looked up over the exception's MRO.
#:
#: The vocabulary lives here as named constants, and every emitter reads it
#: from here.  ``ERROR_CODES`` below held ten of these spellings while six
#: ``_fail`` call sites wrote four of them out again by hand - so renaming a
#: code in the table left the routes that pass it explicitly on the old
#: spelling.  A client that learned the new name then failed on exactly the
#: routes it was told were safe, which is the quietest way for a contract to
#: break: half the surface keeps answering.
CODE_TASK_NOT_FOUND = "task_not_found"
CODE_NOT_FOUND = "not_found"
CODE_INVALID_REQUEST = "invalid_request"
CODE_SESSION_ERROR = "session_error"
CODE_WORKTREE_ERROR = "worktree_error"
CODE_SNAPSHOT_ERROR = "snapshot_error"
CODE_ALLOWLIST_ERROR = "allowlist_error"
CODE_MCP_ERROR = "mcp_error"
CODE_CHANGE_ERROR = "change_error"
CODE_FORBIDDEN = "forbidden"
CODE_UNAUTHORIZED = "unauthorized"
CODE_CROSS_ORIGIN_DENIED = "cross_origin_denied"
CODE_TOO_MANY_EVENT_STREAMS = "too_many_event_streams"
CODE_REQUEST_FAILED = "request_failed"
CODE_INTERNAL_ERROR = "internal_error"

#: M8-T512: the human-readable half of the same refusal.  ``CODE_TASK_NOT_FOUND``
#: above had one home, but the sentence that travels with it was spelled by
#: hand at all three readers - the task read, the event stream, and the POST
#: catch-all - so the code and the sentence could drift apart, and a client
#: matching on the message would see one route answer the old sentence and
#: another answer something newer.  One sentence; every reader asks it.
TASK_NOT_FOUND_MESSAGE = "task not found"

ERROR_CODES: dict[type[BaseException], str] = {
    KeyError: CODE_TASK_NOT_FOUND,
    PermissionError: CODE_FORBIDDEN,
    FileNotFoundError: CODE_NOT_FOUND,
    ValueError: CODE_INVALID_REQUEST,
    SessionError: CODE_SESSION_ERROR,
    WorktreeError: CODE_WORKTREE_ERROR,
    SnapshotError: CODE_SNAPSHOT_ERROR,
    AllowlistError: CODE_ALLOWLIST_ERROR,
    McpError: CODE_MCP_ERROR,
    ChangeError: CODE_CHANGE_ERROR,
}


def error_code_for(exc: BaseException | None) -> str:
    if exc is None:
        return CODE_REQUEST_FAILED
    for kind in type(exc).__mro__:
        code = ERROR_CODES.get(kind)
        if code:
            return code
    return CODE_INTERNAL_ERROR

class MiniccHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True
    # socketserver.TCPServer's default is 5. Under a 20-client burst the
    # listen backlog fills before the next accept() lands and the kernel
    # refuses the SYN — the client gets a zero-status connection reset
    # instead of a queued reply, and the load test records it as an
    # error with no status. Slow-request coalescing already lives one
    # layer below (stats/digest/roadmap are per-PID memoized); the
    # backlog is the one queue nothing else covers — raise it so bursts
    # wait in line instead of dying at the door.
    request_queue_size = 128

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
        # Keep the request log useful without logging request bodies or secrets.
        rendered = f"{self.command} {self.path} - {format % args}"
        LOG.info("%s", self._SECRET_QUERY_RE.sub(r"\1***", rendered))

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
            {
                "error": CODE_FORBIDDEN,
                "code": CODE_CROSS_ORIGIN_DENIED,
                "detail": "跨站状态变更请求已拒绝",
            },
            ensure_ascii=False,
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
            {
                "error": CODE_UNAUTHORIZED,
                "code": CODE_UNAUTHORIZED,
                "auth_required": True,
            },
            ensure_ascii=False,
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

    def _fail(
        self,
        status: int,
        detail: str,
        *,
        code: str | None = None,
        exc: BaseException | None = None,
        **extra: Any,
    ) -> None:
        """Return a structured error body: ``error`` for humans, ``code`` for clients."""
        resolved = code or error_code_for(exc)
        # An exception message can carry a URL or header value, so the client
        # never sees more than a redacted summary.
        safe_detail = redact(detail)
        payload: dict[str, Any] = {"error": safe_detail, "code": resolved}
        if status >= 500 and exc is not None:
            payload["error_type"] = type(exc).__name__
            payload["retryable"] = True
        payload.update(extra)
        self._log_request_failed(status, resolved, safe_detail, exc)
        self._json(payload, status)

    def _log_request_failed(
        self, status: int, code: str, detail: str, exc: BaseException | None
    ) -> None:
        """The one request-failed log line.

        A 4xx is expected client traffic and logs at INFO; a 5xx is a
        server-side failure and logs at ERROR with the traceback.  The
        line itself - and the four facts it carries (status, code,
        path, the first 200 chars of the redacted detail) - is one
        statement about one failed request; writing it twice invites
        the two spellings to drift until the log greps that find one
        miss the other.
        """
        line = "request_failed status=%s code=%s path=%s detail=%s"
        args = (status, code, urlsplit(self.path).path, detail[:200])
        if status >= 500:
            LOG.error(line, *args, exc_info=exc)
        else:
            LOG.info(line, *args)

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
        if path == "/api/worldpulse":
            # M8-T993: live public-world glance — the repo's real GitHub
            # facts, cached through the shared Redis/LRU cache with a
            # 5-minute TTL. Fail-open: live data when reachable, a careful
            # honest payload when not.
            try:
                from .worldpulse import fetch_worldpulse

                self._json(fetch_worldpulse())
            except Exception as exc:  # noqa: BLE001
                self._json({"live": False, "github": None, "error": f"{type(exc).__name__}: {exc}"})
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
        if path == "/api/doctor":
            from .doctor import format_report, run_doctor
            try:
                report = run_doctor(self.server.service.workspace)
                payload: Any = json.loads(format_report(report, json_out=True))
            except Exception as exc:  # noqa: BLE001 — the doctor endpoint must not crash the dispatcher
                payload = {
                    "ok": 0,
                    "warn": 0,
                    "fatal": 1,
                    "checks": [
                        {
                            "name": "doctor_runner",
                            "severity": "fatal",
                            "detail": f"{type(exc).__name__}: {exc}",
                            "fix_hint": "rerun `minicc --doctor`",
                        }
                    ],
                }
            self._json(payload)
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
                self._fail(400, "缺少搜索关键词 q", code=CODE_INVALID_REQUEST)
                return
            try:
                limit = max(1, min(100, int((query.get("limit") or ["50"])[0])))
            except ValueError:
                limit = 50
            workspace_filter = (query.get("workspace") or [""])[0] or None
            self._json(self.server.service.search_history(raw_query, limit=limit, workspace_path=workspace_filter))
            return
        if path == "/api/sessions":
            self._json(self.server.service.list_stored_sessions())
            return
        if path == "/api/audit":
            query = parse_qs(parsed.query)
            try:
                limit = int((query.get("limit") or ["500"])[0])
            except ValueError:
                limit = 500
            raw_levels = (query.get("level") or [""])[0]
            try:
                self._json(
                    self.server.service.audit_export(
                        limit=limit,
                        levels=[item.strip() for item in raw_levels.split(",") if item.strip()],
                        min_level=(query.get("min_level") or [""])[0].strip() or None,
                    )
                )
            except ValueError as exc:
                self._fail(400, str(exc), exc=exc)
            return
        if path == "/api/metrics":
            query = parse_qs(parsed.query)
            try:
                limit = max(1, min(2000, int((query.get("limit") or ["500"])[0])))
            except ValueError:
                limit = 500
            self._json(
                self.server.service.metrics(
                    limit=limit,
                    workspace_path=(query.get("workspace") or [""])[0] or None,
                )
            )
            return
        if path == "/api/digest":
            # M8-T905: the read-only workspace fact pack. Never fails the
            # gate - a non-git workspace answers 200 with is_git: false.
            self._json(self.server.service.digest())
            return
        if path == "/api/rag/search":
            # M8-T971: lexical BM25 retrieval over our own docs + README.
            # Answers "which document explains this" without leaving the repo
            # or reaching the network; never raises on an odd query.
            try:
                query = parse_qs(parsed.query)
                q = (query.get("q") or [""])[0].strip()
                try:
                    limit = int((query.get("k") or ["5"])[0])
                except ValueError:
                    limit = 5
                limit = max(1, min(20, limit))
                from .rag import search as _rag_search

                body = {"q": q, "results": _rag_search(q, limit=limit)}
                self._json(body)
            except Exception as exc:  # noqa: BLE001 - read-only path, never 500s
                self._json({"q": "", "results": [], "error": f"{type(exc).__name__}: {exc}"})
            return
        if path == "/api/rag/query":
            # M8-T973: full RAG — retrieve top-k docs BM25, then ask the configured
            # chat model with the retrieved chunks as evidence. Pure lexical→chat;
            # never runs an unknown model; reports usage when the gateway gives it.
            # M8-T987: each question spawns a real gateway call that spends
            # real tokens, so a sliding-window token bucket guards the door
            # (Resilience4j-shaped; Redis when configured, local LRU otherwise;
            # never raises - fails open honestly and counts the degradation).
            try:
                client_addr = getattr(self, "client_address", None) or ("local", 0)
                client_key = client_addr[0] if client_addr else "local"
                from .ratelimit import consume as _rl_consume

                allowed, _meta = _rl_consume("rag-query", client_key)
                query = parse_qs(parsed.query)
                q = (query.get("q") or [""])[0].strip()
                if not allowed:
                    self._json({
                        "query": q,
                        "answer": "",
                        "sources": [],
                        "model": None,
                        "usage": None,
                        "rate_limited": True,
                        "retry_after_seconds": _meta.get("window_seconds", 60),
                        "error": "RAG rate limit exceeded; retry shortly.",
                    })
                    return
                try:
                    limit = int((query.get("k") or ["4"])[0])
                except ValueError:
                    limit = 4
                limit = max(1, min(8, limit))
                from .rag import answer as _rag_answer

                body = _rag_answer(q, limit=limit)
                self._json(body)
            except Exception as exc:  # noqa: BLE001
                self._json({"q": "", "answer": "", "error": f"{type(exc).__name__}: {exc}"})
            return
        if path == "/api/roadmap":
            # M8-T940: the ledger, parsed - every batch heading, verbatim,
            # bounded titles, grouped into hundred-epoch eras.
            self._json(self.server.service.roadmap())
            return
        if path == "/api/provider-ping":
            # M8-T997: authenticated upstream echo for the doctor panel.
            # Never returns the key; only gateway host, model name, status,
            # round-trip ms. ?fresh=1 bypasses the 10s shared cache.
            try:
                from .provider_ping import fetch_provider_ping

                query = parse_qs(parsed.query)
                force = (query.get("fresh") or [""])[0].lower() in {"1", "true", "yes"}
                self._json(fetch_provider_ping(force_refresh=force))
            except Exception as exc:  # noqa: BLE001 - the route itself must not 500
                self._json({
                    "configured": True,
                    "live": False,
                    "gateway": None,
                    "model": None,
                    "status": None,
                    "elapsed_ms": 0.0,
                    "error": f"{type(exc).__name__}",
                    "probe": "GET /models",
                })
            return
        if path == "/api/stats":
            # M8-T922: the pulse panel's stats channel, finally real.
            self._json(self.server.service.stats())
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
        if path.startswith(TASKS_API_PREFIX) and path.endswith("/events"):
            task_id = unquote(path.removeprefix(TASKS_API_PREFIX).removesuffix("/events")).strip("/")
            query = parse_qs(parsed.query)
            raw_after = (query.get("after") or [self.headers.get("Last-Event-ID", "0")])[0]
            try:
                after = max(0, int(raw_after))
            except ValueError:
                after = 0
            self._stream_task(task_id, after=after)
            return
        if path.startswith(TASKS_API_PREFIX):
            task_id = unquote(path.removeprefix(TASKS_API_PREFIX)).strip("/")
            try:
                self._json(self.server.service.tasks.get(task_id))
            except KeyError:
                self._fail(404, TASK_NOT_FOUND_MESSAGE, code=CODE_TASK_NOT_FOUND)
            return
        if path == "/api/file":
            raw_path = (parse_qs(parsed.query).get("path") or [""])[0]
            try:
                self._json(self.server.service.file_preview(raw_path))
            except Exception as exc:  # noqa: BLE001 - stable read-only API error
                self._fail(400, str(exc), exc=exc)
            return
        if path == "/api/files":
            query = parse_qs(parsed.query)
            raw_path = (query.get("path") or [""])[0]
            raw_depth = (query.get("depth") or ["3"])[0]
            try:
                self._json(self.server.service.file_tree(raw_path, depth=int(raw_depth)))
            except (ValueError, OSError) as exc:
                self._fail(400, str(exc), exc=exc)
            return
        if path == "/api/changes":
            try:
                self._json(self.server.service.changes())
            except ChangeError as exc:
                self._fail(400, str(exc), exc=exc)
            return
        if path == "/api/diff":
            raw_path = (parse_qs(parsed.query).get("path") or [""])[0]
            try:
                self._json(self.server.service.changes(raw_path))
            except ChangeError as exc:
                self._fail(400, str(exc), exc=exc)
            return
        if path == "/api/stategraph":
            # Live StateGraph + stage-routing read for the panel. Never raises;
            # a broken read is a 200 with an error field so the panel can fall
            # back to its embedded replica instead of crashing.
            try:
                from .stategraph_payload import stategraph_payload

                self._json(stategraph_payload(self.server.service.config))
            except Exception as exc:  # noqa: BLE001 - the panel must never 500
                self._json({"error": f"{type(exc).__name__}: {exc}"}, 200)
            return
        if path == "/api/ci_status":
            # M8-T1062: live mainline health for THIS repository — GitHub REST
            # honest wire (never raises; failure reports live=False).
            try:
                from .ci_health import fetch_ci_health

                self._json(fetch_ci_health())
            except Exception as exc:  # noqa: BLE001 - the admin tile must never 500
                self._json({"live": False, "error": f"{type(exc).__name__}: {exc}"}, 200)
            return
        if path == "/api/oracle-ci-diagnosis":
            # M8-T1166: the model reads the real GitHub wire (same data the
            # /api/ci_status tile shows) and attributes the latest mainline
            # red, or honestly says there is none (no model call). Never raises.
            try:
                from .oracle_ci_diagnosis import build_ci_diagnosis

                query = parse_qs(parsed.query)
                fresh = (query.get("fresh") or [""])[0].strip() in ("1", "true", "yes")
                self._json(build_ci_diagnosis(workspace=self.server.service.workspace, force_refresh=fresh))
            except Exception as exc:  # noqa: BLE001 - the panel must never 500
                self._json({"live": False, "zh": "", "en": "",
                            "error": f"{type(exc).__name__}: {exc}"}, 200)
            return
        if path == "/api/oracle-retrospective":
            # The model as completion-assurance: reads the audit record of the
            # most recent "completed" task and judges its plausibility.
            # Never raises; the panel shows the outage when the wire is down.
            try:
                from .oracle_retrospective import build_workspace_retrospective

                query = parse_qs(parsed.query)
                fresh = (query.get("fresh") or [""])[0].strip() in ("1", "true", "yes")
                self._json(build_workspace_retrospective(workspace=self.server.service.workspace, force_refresh=fresh))
            except Exception as exc:  # noqa: BLE001 - the panel must never 500
                self._json({"live": False, "zh": "", "en": "",
                            "error": f"{type(exc).__name__}: {exc}"}, 200)
            return
        if path == "/api/oracle-review":
            # The model as reviewer of this repo's own latest diff — real facts in,
            # bilingual review out; ?fresh=1 bypasses the memo; wire death honest.
            try:
                from .oracle_review import build_workspace_review

                query = parse_qs(parsed.query)
                fresh = (query.get("fresh") or [""])[0].strip() in ("1", "true", "yes")
                self._json(build_workspace_review(workspace=self.server.service.workspace, force_refresh=fresh))
            except Exception as exc:  # noqa: BLE001 - the panel must never 500
                self._json({"live": False, "zh": "", "en": "",
                            "error": f"{type(exc).__name__}: {exc}"}, 200)
            return
        if path == "/api/oracle-plan":
            # The model as forward planner: three moves this workspace should
            # make next, ordered by urgency, each with an acceptance test.
            # Never raises; the panel shows the outage when the wire is down.
            try:
                from .oracle_plan import build_workspace_plan

                query = parse_qs(parsed.query)
                fresh = (query.get("fresh") or [""])[0].strip() in ("1", "true", "yes")
                self._json(build_workspace_plan(workspace=self.server.service.workspace, force_refresh=fresh))
            except Exception as exc:  # noqa: BLE001 - the panel must never 500
                self._json({"live": False, "zh": [], "en": [],
                            "error": f"{type(exc).__name__}: {exc}"}, 200)
            return
        if path == "/api/oracle-diagnosis":
            # The model on duty for triage: reads the interruption/streak/trend
            # evidence, writes a bilingual diagnosis. ?fresh=1 bypasses the memo.
            # Never raises; the panel shows the outage when the wire is down.
            try:
                from .oracle_diagnosis import build_workspace_diagnosis

                query = parse_qs(parsed.query)
                fresh = (query.get("fresh") or [""])[0].strip() in ("1", "true", "yes")
                self._json(build_workspace_diagnosis(workspace=self.server.service.workspace, force_refresh=fresh))
            except Exception as exc:  # noqa: BLE001 - the panel must never 500
                self._json({"live": False, "zh": "", "en": "",
                            "error": f"{type(exc).__name__}: {exc}"}, 200)
            return
        if path == "/api/oracle-brief":
            # The model on duty for this workspace: reads the measured fact pack,
            # writes a two-part zh+en brief. ?fresh=1 bypasses the 10-minute memo.
            # Never raises; the panel shows the outage when the wire is down.
            try:
                from .oracle_brief import build_workspace_brief

                query = parse_qs(parsed.query)
                fresh = (query.get("fresh") or [""])[0].strip() in ("1", "true", "yes")
                self._json(build_workspace_brief(workspace=self.server.service.workspace, force_refresh=fresh))
            except Exception as exc:  # noqa: BLE001 - the panel must never 500
                self._json({"live": False, "zh": "", "en": "",
                            "error": f"{type(exc).__name__}: {exc}"}, 200)
            return
        if path == "/api/admin/summary":
            # M8-T1014: the admin panel's single read — built from real
            # workspace data, never raises; returns honest empty dict on breakage.
            # M8-T1065: the payload is memoized 15s by AgentService.admin_summary
            # so a fat unlock burst never re-walks the audit log per read.
            try:
                self._json(self.server.service.admin_summary())
            except Exception as exc:  # noqa: BLE001 - the admin route must never 500
                self._json({"error": f"{type(exc).__name__}: {exc}"}, 200)
            return
        if path == "/api/worktrees":
            try:
                self._json({"worktrees": self.server.service.worktrees.list()})
            except WorktreeError as exc:
                self._fail(400, str(exc), exc=exc)
            return
        if path == "/api/mcp":
            self._json(self.server.service.mcp.status() if self.server.service.mcp else mcp_absent_status(self.server.service.mcp_error))
            return
        if path == "/api/allowlist":
            query = parse_qs(parsed.query)
            session_id = (query.get("session_id") or [""])[0].strip()
            try:
                self._json(self.server.service.get_allowlist(session_id))
            except (ValueError, AllowlistError) as exc:
                self._fail(400, str(exc), exc=exc)
            return
        if path == "/api/permissions":
            self._json(self.server.service.permissions_status())
            return
        if path == "/api/admin/drift":
            # M8-T1160: the drift sentinel — a model-free oracle for repo
            # self-consistency (HEAD vs fact pack, CRLF pins, doc_pointers --check).
            # ?fresh=1 bypasses the 10-minute memo. Never raises.
            try:
                from .admin_drift import build_workspace_drift

                query = parse_qs(parsed.query)
                fresh = (query.get("fresh") or [""])[0].strip() in ("1", "true", "yes")
                self._json(build_workspace_drift(workspace=self.server.service.workspace, force_refresh=fresh))
            except Exception as exc:  # noqa: BLE001 - the tile must never 500
                self._json({
                    "live": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }, 200)
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
            self._fail(404, TASK_NOT_FOUND_MESSAGE, code=CODE_TASK_NOT_FOUND)
            return

        if not self.server.sse_slots.acquire(blocking=False):
            self._fail(
                429,
                "实时任务连接过多，请稍后重试或使用任务查询接口。",
                code=CODE_TOO_MANY_EVENT_STREAMS,
                retryable=True,
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
            try:
                size = int(self.headers.get("Content-Length", "0"))
            except (TypeError, ValueError):
                # M8-T292: a malformed Content-Length used to raise here -
                # *before* the drain block - so the connection was left open
                # with the body still in it, and the next request on it was
                # parsed out of the leftover bytes.  The connection is closed
                # instead: its framing is no longer trustworthy.
                self.close_connection = True
                size = -1
            # Drain the request body before any early return so HTTP/1.1
            # keep-alive framing stays consistent. Otherwise the server closes
            # with unread request bytes in flight and Windows clients see a
            # reset (ConnectionAbortedError) instead of the 403 body.
            #
            # M8-T287: the drain used to be conditional on the body being an
            # *acceptable* size, so the two rejection paths - too large, and
            # chunked (no Content-Length at all) - left the whole body in the
            # socket.  The 400 went out, the connection stayed open, and the
            # next request on it was parsed out of the leftover bytes: a
            # malformed request line and a dropped connection.  A rejected
            # body still has to be drained - up to a bound, beyond which the
            # connection is simply closed.
            chunked = "chunked" in str(self.headers.get("Transfer-Encoding", "")).lower()
            if chunked:
                # This server does not speak chunked.  The body is unread and
                # cannot be framed, so the connection cannot be reused.
                self.close_connection = True
                raw = b""
            elif 0 < size <= MAX_BODY_BYTES:
                raw = self.rfile.read(size)
            elif size > MAX_BODY_BYTES:
                # Too large to hold.  Draining it would block on a body that
                # may never arrive in full, so the connection is closed
                # instead: the 400 goes out and the leftover bytes never
                # reach a parser.
                self.close_connection = True
                raw = b""
            else:
                # M8-T292: no usable length (``0``, negative, or malformed).
                # The body may still be sitting in the socket, and its
                # framing cannot be trusted - so the connection is closed
                # rather than left to be mis-parsed as the next request.
                self.close_connection = True
                raw = b""
            # M3-T1: reject cross-site state changes before doing any work.
            if not self._origin_allowed_for_state_change():
                self._deny_cross_origin()
                return
            if chunked:
                raise ValueError("不支持 chunked 请求体")
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
            if path.endswith("/resume") and path.startswith(TASKS_API_PREFIX):
                task_id = unquote(path.removeprefix(TASKS_API_PREFIX).removesuffix("/resume")).strip("/")
                self._json(self.server.service.tasks.resume(task_id), 202)
                return
            if path.endswith("/cancel") and path.startswith(TASKS_API_PREFIX):
                task_id = unquote(path.removeprefix(TASKS_API_PREFIX).removesuffix("/cancel")).strip("/")
                self._json(self.server.service.tasks.cancel(task_id))
                return
            if path == "/api/workspace/select":
                raw_path = require_text(payload.get("path"), "path")
                self._json(self.server.service.switch_workspace(raw_path))
                return
            if path == "/api/sessions/rewind":
                session_id = require_text(payload.get("session_id"), "session_id")
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
            if path == "/api/sessions/fork":
                session_id = require_text(payload.get("session_id"), "session_id")
                point = payload.get("from_message_id")
                if isinstance(point, str):
                    point = require_text(point, "from_message_id")
                elif not isinstance(point, int):
                    raise ValueError("from_message_id 必须是消息序号（整数）或消息 id（字符串）")
                raw_new = payload.get("new_session_id")
                self._json(
                    self.server.service.fork_session(
                        session_id, point, raw_new if isinstance(raw_new, str) else None
                    )
                )
                return
            if path == "/api/workspace/restore":
                task_id = require_text(payload.get("task_id"), "task_id")
                self._json(self.server.service.restore_task_snapshot(task_id))
                return
            if path == "/api/allowlist":
                session_id = require_text(payload.get("session_id"), "session_id")
                self._json(self.server.service.set_allowlist(session_id, payload))
                return
            if path == "/api/approval":
                # M7-T3: the user answered a pending approval_request frame.
                request_id = require_text(payload.get("request_id"), "request_id")
                decision = require_text(payload.get("decision"), "decision")
                self._json(self.server.service.resolve_approval(request_id, decision))
                return
            if path == "/api/worktrees":
                name = require_text(payload.get("name"), "name")
                self._json(self.server.service.worktrees.create(name, payload.get("branch")), 201)
                return
            if path == "/api/worktrees/remove":
                name = require_text(payload.get("name"), "name")
                self._json(self.server.service.worktrees.remove(name, bool(payload.get("force"))))
                return
            self._fail(404, "not found", code=CODE_NOT_FOUND)
        except KeyError:
            self._fail(404, TASK_NOT_FOUND_MESSAGE, code=CODE_TASK_NOT_FOUND)
        except (ValueError, json.JSONDecodeError, SessionError, WorktreeError, SnapshotError, AllowlistError, McpError) as exc:
            self._fail(400, str(exc), exc=exc)
        except Exception as exc:  # noqa: BLE001 - return a stable API error
            # 500 because nothing here was expected, but the code still names
            # what the service raised: a client can distinguish ``forbidden``
            # from ``internal_error`` without parsing prose.
            self._fail(500, f"agent failed: {type(exc).__name__}: {exc}", exc=exc)

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
            self._fail(404, "not found", code=CODE_NOT_FOUND)
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
