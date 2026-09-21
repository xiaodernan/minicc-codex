"""A small stdio + streamable-HTTP MCP client and tool bridge.

Servers are opt-in through ``workspace/.minicc/mcp.json``. The bridge keeps
MCP output untrusted and marks configured tools as read-only only when the
server declares ``read_only: true``.

Two transports are supported per server entry:

- stdio (default): ``{"command": "node", "args": [...], "env": {...}}``
- streamable HTTP: ``{"url": "http://127.0.0.1:3000/mcp", "headers": {...}}``

HTTP responses may be plain JSON or an SSE stream; both are parsed. The
``Mcp-Session-Id`` response header is persisted and replayed on subsequent
requests, per the MCP streamable HTTP transport spec.
"""

from __future__ import annotations

import hashlib
import json
import os
import queue
import subprocess
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import __version__
from .logging_setup import get_logger
from .netguard import BlockedAddressError, assert_public_http_url
from .tools.registry import ToolSpec, split_output
from .tools.schemas import ToolResult

LOG = get_logger("mcp")


class McpError(RuntimeError):
    """MCP configuration or transport failure."""


#: Sentinel cached by ``McpManager`` for a server whose client could not be
#: built. Distinct from ``None`` so a negative cache hit never re-spawns the
#: child process on every task (M5-T3).
_DEAD_CLIENT = object()


def _content_to_tool_result(server: str, tool: str, result: dict[str, Any]) -> ToolResult:
    """Flatten MCP ``content`` into a bounded, untrusted ToolResult (M5-T1).

    Mirrors the built-in tools' 6000-char head/tail budget: a malicious or
    chatty server returning 500k characters must not flood the prompt and the
    persisted session JSON. ``truncated`` is set honestly whenever bytes drop.
    """
    content = result.get("content", [])
    chunks: list[str] = []
    for item in content if isinstance(content, list) else []:
        if isinstance(item, dict) and item.get("type") == "text":
            chunks.append(str(item.get("text", "")))
        else:
            chunks.append(json.dumps(item, ensure_ascii=False))
    head, tail, truncated = split_output("\n".join(chunks))
    return ToolResult(
        status="error" if result.get("isError") else "ok",
        summary=f"MCP {server}/{tool}",
        head=head,
        tail=tail,
        truncated=truncated,
        security_tags=["untrusted", "mcp"],
    )


def _emit_spawn_audit(
    workspace: Path,
    *,
    name: str,
    transport: str,
    command: str,
    env_keys: list[str] | None = None,
) -> None:
    """Append a redacted spawn record to `.minicc/mcp_audit.jsonl` (M2-T7).

    Never stores command args, env values, or credentials — only the shape
    of what was spawned, so the audit file itself stays safe to inspect.
    """
    entry = {
        "kind": "mcp_spawn",
        "timestamp": time.time(),
        "name": str(name or ""),
        "transport": str(transport or ""),
        "command": str(command or ""),
        "env_keys": [str(k) for k in (env_keys or [])],
    }
    path = workspace / ".minicc" / "mcp_audit.jsonl"
    # Same record, two destinations (M8-T5): the file is the workspace-local
    # audit trail, the log line is what an operator tailing the log sees. The
    # redaction filter strips any credential shaped like a token from it.
    LOG.info(
        "mcp_spawn name=%s transport=%s command=%s env_keys=%s",
        entry["name"] or "-",
        entry["transport"] or "-",
        entry["command"][:200] or "-",
        ",".join(entry["env_keys"]) or "-",
    )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        # Spawn must never fail because the audit file is unwritable; the
        # runtime surfaces MCP problems through tool errors instead.
        pass


@dataclass(frozen=True)
class McpServerConfig:
    name: str
    command: str = ""
    args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    read_only: bool = False
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def transport(self) -> str:
        return "http" if self.url else "stdio"


def load_mcp_config(workspace: Path) -> list[McpServerConfig]:
    path = workspace / ".minicc" / "mcp.json"
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise McpError(f"无法读取 MCP 配置: {exc}") from exc
    entries = raw.get("servers", raw) if isinstance(raw, dict) else raw
    if not isinstance(entries, dict):
        raise McpError("MCP 配置需要 servers 对象")
    configs: list[McpServerConfig] = []
    for name, value in entries.items():
        if not isinstance(value, dict):
            raise McpError(f"MCP server {name!r} 配置必须是对象")
        has_command = isinstance(value.get("command"), str) and value["command"].strip()
        has_url = isinstance(value.get("url"), str) and value["url"].strip()
        if not has_command and not has_url:
            raise McpError(f"MCP server {name!r} 缺少 command 或 url")
        if has_url:
            url = str(value["url"]).strip()
            if not url.startswith(("http://", "https://")):
                raise McpError(f"MCP server {name!r} 的 url 必须是 http/https 地址")
            try:
                assert_public_http_url(url, allow_env="MINICC_ALLOW_PRIVATE_MCP")
            except (BlockedAddressError, ValueError) as exc:
                raise McpError(f"MCP server {name!r} 的 url 被 SSRF 防护拒绝: {exc}") from exc
        args = value.get("args", [])
        env = value.get("env", {})
        headers = value.get("headers", {})
        if not isinstance(args, list) or not all(isinstance(item, str) for item in args):
            raise McpError(f"MCP server {name!r} 的 args 非法")
        if not isinstance(env, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
            raise McpError(f"MCP server {name!r} 的 env 非法")
        if not isinstance(headers, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in headers.items()):
            raise McpError(f"MCP server {name!r} 的 headers 非法")
        configs.append(McpServerConfig(
            str(name),
            str(value.get("command") or ""),
            tuple(args),
            dict(env),
            bool(value.get("read_only", False)),
            str(value.get("url") or ""),
            dict(headers),
        ))
    return configs


class McpStdioClient:
    """Persistent JSON-RPC-over-stdio client with a reader queue."""

    #: Environment variables MCP server children are allowed to inherit.
    #: Everything else (LLM api_key, web bearer token, etc.) is scrubbed so
    #: a malicious `.minicc/mcp.json` cannot become key-bearing RCE.
    INHERITED_ENV_KEYS = (
        "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "COMSPEC",
        "TEMP", "TMP", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
        "PROGRAMFILES", "PROGRAMFILES(X86)", "WINDIR", "LANG", "LC_ALL",
        "SYSTEMDRIVE", "WINDIR", "COMPUTERNAME", "USERNAME", "USERPROFILE",
        "WINDIR", "TMPDIR", "LANGUANGE", "LC_ALL", "LC_ALL",
        "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "ALL_PROXY",
        "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE",
    )

    def __init__(self, config: McpServerConfig, workspace: Path) -> None:
        self.config = config
        self.workspace = workspace
        self.process: subprocess.Popen[str] | None = None
        self._reader: threading.Thread | None = None
        self._responses: queue.Queue[dict[str, Any]] = queue.Queue()
        self._write_lock = threading.Lock()
        self._counter = 0
        self._dead = False
        self._dead_reason = ""
        self._start()

    @property
    def dead(self) -> bool:
        return self._dead or (self.process is not None and self.process.poll() is not None)

    def _mark_dead(self, reason: str) -> None:
        if not self._dead:
            self._dead = True
            self._dead_reason = reason

    @staticmethod
    def scrubbed_env(config_env: dict[str, str] | None) -> dict[str, str]:
        """Build a minimal child environment (M2-T7).

        Only a small PATH/OS allowlist survives; everything else — notably
        ``MINICC_API_KEY`` and the web bearer token — must come through the
        server entry's explicit ``env`` mapping, never by ambient inheritance.
        """
        allowed = {key.strip().upper() for key in McpStdioClient.INHERITED_ENV_KEYS if key.strip()}
        env: dict[str, str] = {}
        for key in os.environ:
            if key.upper() in allowed:
                env[key] = os.environ[key]
        for key, value in (config_env or {}).items():
            env[str(key)] = str(value)
        return env

    def _start(self) -> None:
        # M2-T7: scrubbed env + spawn audit trail (no ambient LLM api_key /
        # web bearer token inheritance from the parent environment).
        env = self.scrubbed_env(self.config.env)
        _emit_spawn_audit(
            self.workspace,
            name=self.config.name,
            transport="stdio",
            command=self.config.command,
            env_keys=sorted(self.config.env.keys()),
        )
        try:
            self.process = subprocess.Popen(
                [self.config.command, *self.config.args],
                cwd=self.workspace,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                # M5-T3: an undecodable byte on stdout must not kill the reader
                # thread (which would strand every later call for the full 30s
                # timeout). Replace, keep reading, let JSON parsing reject it.
                errors="replace",
                env=env,
                bufsize=1,
            )
        except OSError as exc:
            raise McpError(f"无法启动 MCP server {self.config.name}: {exc}") from exc
        self._reader = threading.Thread(target=self._read_loop, name=f"mcp-{self.config.name}", daemon=True)
        self._reader.start()
        try:
            self._request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "minicc", "version": __version__},
            })
            self._notify("notifications/initialized", {})
        except McpError:
            # Do not leave a half-initialized child behind on a failed start.
            self.close()
            raise

    def _read_loop(self) -> None:
        # M5-T3: supervise the reader. Whatever ends the loop — clean EOF, a
        # closed pipe, an unexpected exception — marks the client dead so the
        # next _request fails in <1s instead of blocking on the 30s timeout.
        try:
            assert self.process and self.process.stdout
            for line in self.process.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(message, dict):
                    continue
                if "method" in message:
                    # Server-initiated request/notification (M5-T2): answer the
                    # read-only probes servers legitimately send, ignore the rest.
                    self._handle_server_message(message)
                elif "id" in message:
                    self._responses.put(message)
        except (OSError, ValueError):
            self._mark_dead("reader error")
        finally:
            self._mark_dead("reader exited")

    def _handle_server_message(self, message: dict[str, Any]) -> None:
        method = str(message.get("method") or "")
        msg_id = message.get("id")
        if msg_id is None:
            return  # notification: nothing to answer
        if method == "ping":
            self._respond(msg_id, result={})
        elif method == "roots/list":
            self._respond(msg_id, result={"roots": []})
        else:
            self._respond(msg_id, error={"code": -32601, "message": f"Method not found: {method}"})

    def _respond(self, msg_id: Any, *, result: Any = None, error: Any = None) -> None:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "id": msg_id}
        if error is not None:
            payload["error"] = error
        else:
            payload["result"] = result if result is not None else {}
        self._write(payload)

    def _write_locked(self, payload: dict[str, Any]) -> bool:
        """Frame and flush one message; caller must hold ``_write_lock``."""
        if not self.process or not self.process.stdin:
            return False
        try:
            self.process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self.process.stdin.flush()
            return True
        except (OSError, ValueError):
            self._mark_dead("write failed")
            return False

    def _write(self, payload: dict[str, Any]) -> bool:
        """Write one framed message under the lock; False if the pipe is gone."""
        with self._write_lock:
            return self._write_locked(payload)

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        self._write({"jsonrpc": "2.0", "method": method, "params": params})

    def _ensure_alive(self) -> None:
        if self._dead:
            raise McpError(f"MCP server {self.config.name} 已终止: {self._dead_reason or 'unknown'}")
        if self.process is None or self.process.poll() is not None or not self.process.stdin:
            self._mark_dead("process exited")
            raise McpError(f"MCP server {self.config.name} 已退出")

    def _request(self, method: str, params: dict[str, Any], timeout: float = 30) -> dict[str, Any]:
        self._ensure_alive()
        # Stamp the id and frame the request under one lock so concurrent
        # callers can't interleave counter increments; release before waiting
        # so the reader thread can still answer server-initiated requests.
        with self._write_lock:
            self._counter += 1
            request_id = self._counter
            sent = self._write_locked({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        if not sent:
            self._mark_dead("write failed")
            raise McpError(f"MCP server {self.config.name} 写入失败: {method}")
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise McpError(f"MCP server {self.config.name} 请求超时: {method}")
            try:
                # Poll in short slices so a reader that dies mid-wait surfaces
                # as a fast McpError instead of burning the whole timeout.
                response = self._responses.get(timeout=min(remaining, 0.25))
            except queue.Empty:
                self._ensure_alive()
                continue
            # M5-T2: servers may echo the id as a string; compare canonically.
            if str(response.get("id")) == str(request_id):
                if "error" in response:
                    raise McpError(str(response["error"]))
                result = response.get("result")
                return result if isinstance(result, dict) else {}
            # Foreign/stale response (e.g. a server-initiated id collision):
            # drop it and keep waiting for ours.

    def list_tools(self) -> list[dict[str, Any]]:
        result = self._request("tools/list", {})
        tools = result.get("tools", [])
        return tools if isinstance(tools, list) else []

    def list_resources(self) -> list[dict[str, Any]]:
        try:
            result = self._request("resources/list", {})
        except McpError:
            return []
        items = result.get("resources", [])
        return items if isinstance(items, list) else []

    def list_prompts(self) -> list[dict[str, Any]]:
        try:
            result = self._request("prompts/list", {})
        except McpError:
            return []
        items = result.get("prompts", [])
        return items if isinstance(items, list) else []

    def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        result = self._request("tools/call", {"name": name, "arguments": arguments})
        return _content_to_tool_result(self.config.name, name, result)

    def close(self) -> None:
        # M5-T5: reap the child instead of leaking a zombie / SIGTERM-ignoring
        # process. terminate → wait → kill → wait, then close the pipes.
        process = self.process
        if process is None:
            return
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        pass
        finally:
            for stream in (process.stdin, process.stdout):
                try:
                    if stream is not None:
                        stream.close()
                except (OSError, ValueError):
                    pass
            self._mark_dead("closed")


class McpHttpClient:
    """MCP streamable-HTTP client: JSON-RPC over POST, JSON or SSE responses."""

    def __init__(self, config: McpServerConfig, workspace: Path, timeout: float = 30.0) -> None:
        self.config = config
        self.workspace = workspace
        self.timeout = timeout
        self.session_id = ""
        self._counter = 0
        self._lock = threading.Lock()
        self._initialize()

    def _post(self, payload: dict[str, Any]) -> tuple[int, str, str, str]:
        """POST one JSON-RPC message; returns (status, content_type, body, session_id)."""
        request = urllib.request.Request(
            self.config.url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
        )
        request.add_header("Content-Type", "application/json")
        request.add_header("Accept", "application/json, text/event-stream")
        if self.session_id:
            request.add_header("Mcp-Session-Id", self.session_id)
        for key, value in self.config.headers.items():
            request.add_header(key, value)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
                session_id = response.headers.get("Mcp-Session-Id") or ""
                return int(response.status), response.headers.get("Content-Type", ""), body, session_id
        except urllib.error.HTTPError as exc:
            raise McpError(f"MCP HTTP server {self.config.name} 返回 HTTP {exc.code}") from None
        except (urllib.error.URLError, OSError) as exc:
            raise McpError(f"MCP HTTP server {self.config.name} 不可达: {exc}") from None

    def _initialize(self) -> None:
        status, content_type, body, session_id = self._post({
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "minicc", "version": __version__},
            },
        })
        if status >= 400:
            raise McpError(f"MCP HTTP server {self.config.name} 初始化失败: HTTP {status}")
        self.session_id = session_id
        result = self._parse_body(content_type, body, expect_id=0)
        if result is None:
            raise McpError(f"MCP HTTP server {self.config.name} 初始化响应无效")
        # notifications/initialized: servers typically answer 202 with no body.
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    def _parse_body(self, content_type: str, body: str, expect_id: int | None = None) -> dict[str, Any] | None:
        """Parse a JSON or SSE body into one JSON-RPC result object."""
        if "text/event-stream" in (content_type or ""):
            for event in _iter_sse_messages(body):
                if "id" not in event:
                    continue
                # M5-T2: a server may echo the id as a string; compare canonically
                # instead of int()-coercing (which raised a bare ValueError).
                if expect_id is None or str(event.get("id")) == str(expect_id):
                    if "error" in event:
                        raise McpError(str(event["error"]))
                    result = event.get("result")
                    return result if isinstance(result, dict) else {}
            return None
        if not body.strip():
            return None
        try:
            message = json.loads(body)
        except json.JSONDecodeError:
            return None
        if not isinstance(message, dict):
            return None
        if "error" in message:
            raise McpError(str(message["error"]))
        result = message.get("result")
        return result if isinstance(result, dict) else {}

    def _request(self, method: str, params: dict[str, Any], timeout: float = 30) -> dict[str, Any]:
        with self._lock:
            self._counter += 1
            request_id = self._counter
        _status, content_type, body, _session = self._post({
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        })
        result = self._parse_body(content_type, body, expect_id=request_id)
        if result is None:
            raise McpError(f"MCP HTTP server {self.config.name} 请求无响应: {method}")
        return result

    def list_tools(self) -> list[dict[str, Any]]:
        result = self._request("tools/list", {})
        tools = result.get("tools", [])
        return tools if isinstance(tools, list) else []

    def list_resources(self) -> list[dict[str, Any]]:
        try:
            result = self._request("resources/list", {})
        except McpError:
            return []
        items = result.get("resources", [])
        return items if isinstance(items, list) else []

    def list_prompts(self) -> list[dict[str, Any]]:
        try:
            result = self._request("prompts/list", {})
        except McpError:
            return []
        items = result.get("prompts", [])
        return items if isinstance(items, list) else []

    def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        result = self._request("tools/call", {"name": name, "arguments": arguments})
        return _content_to_tool_result(self.config.name, name, result)

    def close(self) -> None:
        return None


def _iter_sse_messages(body: str) -> list[dict[str, Any]]:
    """Parse SSE frames into JSON-RPC message dicts (event: message / data: ...)."""
    messages: list[dict[str, Any]] = []
    data_lines: list[str] = []
    for line in body.splitlines():
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
        elif not line.strip() and data_lines:
            try:
                message = json.loads("\n".join(data_lines))
            except json.JSONDecodeError:
                message = None
            if isinstance(message, dict):
                messages.append(message)
            data_lines = []
    if data_lines:
        try:
            message = json.loads("\n".join(data_lines))
            if isinstance(message, dict):
                messages.append(message)
        except json.JSONDecodeError:
            pass
    return messages


class McpManager:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.configs = load_mcp_config(workspace)
        self.clients: dict[str, Any] = {}
        self._client_lock = threading.RLock()

    def _client(self, config: McpServerConfig) -> Any:
        with self._client_lock:
            if config.name in self.clients:
                cached = self.clients[config.name]
                if cached is _DEAD_CLIENT:
                    # M5-T3 negative cache: a server that already failed to
                    # start must not be re-spawned on every task.
                    raise McpError(f"MCP server {config.name} 此前启动失败，已负缓存")
                return cached
            try:
                if config.transport == "http":
                    client: Any = McpHttpClient(config, self.workspace)
                else:
                    client = McpStdioClient(config, self.workspace)
            except McpError:
                self.clients[config.name] = _DEAD_CLIENT
                raise
            self.clients[config.name] = client
            return client

    def _mark_dead(self, name: str, *, reap: bool) -> None:
        cached = self.clients.get(name)
        if reap and cached is not None and cached is not _DEAD_CLIENT:
            cached.close()
        self.clients[name] = _DEAD_CLIENT

    @staticmethod
    def _unique_tool_name(server: str, tool: str, taken: set[str]) -> str:
        """Build a registry-safe ``mcp__server__tool`` name (M5-T4).

        Two long tool names that only differ past char 128 would otherwise
        truncate to the same string and make ``ToolRegistry.register`` raise an
        uncaught ``ValueError``. Disambiguate with a short hash of the full
        name so both tools stay callable instead of poisoning the workspace.
        """
        base = f"mcp__{server}__{tool}"
        candidate = base[:128]
        if candidate == base and candidate not in taken:
            taken.add(candidate)
            return candidate
        digest = hashlib.sha256(base.encode("utf-8")).hexdigest()[:8]
        prefix = base[: 128 - len(digest) - 1]
        candidate = f"{prefix}~{digest}"
        while candidate in taken:
            digest = hashlib.sha256(candidate.encode("utf-8")).hexdigest()[:8]
            candidate = f"{prefix}~{digest}"
        taken.add(candidate)
        return candidate

    def status(self) -> dict[str, Any]:
        return {
            "configured": len(self.configs),
            "servers": [
                {
                    "name": item.name,
                    "command": item.command,
                    "url": item.url,
                    "transport": item.transport,
                    "read_only": item.read_only,
                }
                for item in self.configs
            ],
        }

    def health(self) -> list[dict[str, Any]]:
        """Per-server liveness without spawning anything new (M5-T7)."""
        report: list[dict[str, Any]] = []
        for config in self.configs:
            cached = self.clients.get(config.name)
            if cached is None:
                state = "unspawned"
            elif cached is _DEAD_CLIENT or getattr(cached, "dead", False):
                state = "dead"
            else:
                state = "ok"
            report.append({"name": config.name, "transport": config.transport, "state": state})
        return report

    def tool_specs(self) -> list[ToolSpec]:
        specs: list[ToolSpec] = []
        taken: set[str] = set()
        spawned_now: list[str] = []
        try:
            for config in self.configs:
                existed = config.name in self.clients
                try:
                    client = self._client(config)
                    if not existed:
                        spawned_now.append(config.name)
                    if getattr(client, "dead", False):
                        raise McpError(f"MCP server {config.name} 不可用（已标记 dead）")
                    tools = client.list_tools()
                except McpError:
                    # M5-T5: a server that fails mid-discovery is marked dead and,
                    # if we just spawned it, reaped — so the first server's child
                    # is never orphaned by the second server's failure.
                    self._mark_dead(config.name, reap=config.name in spawned_now)
                    raise
                for item in tools:
                    name = str(item.get("name", ""))
                    if not name:
                        continue
                    safe_name = self._unique_tool_name(config.name, name, taken)
                    schema = item.get("inputSchema") if isinstance(item.get("inputSchema"), dict) else {"type": "object", "properties": {}}
                    specs.append(ToolSpec(
                        safe_name,
                        f"MCP {config.name}: {item.get('description', name)}",
                        "readonly" if config.read_only else "exec",
                        (),
                        lambda args, c=client, n=name: c.call_tool(n, args),
                        input_schema=schema,
                    ))
        except McpError:
            # Reap anything else spawned during this failed discovery pass.
            for other in spawned_now:
                if self.clients.get(other) is not _DEAD_CLIENT:
                    self._mark_dead(other, reap=True)
            raise
        return specs

    def resources_context(self, *, max_chars: int = 6000, max_items: int = 20) -> str:
        """Bounded read-only context from resources/list + prompts/list (M5-T7).

        Each line is clamped to ``max_chars``; dead or unspawnable servers are
        skipped rather than allowed to stall discovery.
        """
        lines: list[str] = []
        for config in self.configs:
            if len(lines) >= max_items:
                break
            try:
                client = self._client(config)
            except McpError:
                continue
            if getattr(client, "dead", False):
                self._mark_dead(config.name, reap=False)
                continue
            for kind, items, key in (
                ("resource", client.list_resources(), "uri"),
                ("prompt", client.list_prompts(), "name"),
            ):
                for item in items:
                    if len(lines) >= max_items:
                        break
                    if not isinstance(item, dict):
                        continue
                    ident = str(item.get(key) or item.get("name") or "")
                    if not ident:
                        continue
                    desc = str(item.get("description") or "")
                    line = f"- [mcp:{config.name}] {kind} {ident}"
                    if desc:
                        line += f" — {desc}"
                    lines.append(line[:max_chars])
        return "\n".join(lines)

    def close(self) -> None:
        for client in self.clients.values():
            if client is _DEAD_CLIENT:
                continue
            client.close()
