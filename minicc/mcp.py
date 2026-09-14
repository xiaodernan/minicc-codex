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

import json
import os
import queue
import subprocess
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .tools.registry import ToolSpec
from .tools.schemas import ToolResult


class McpError(RuntimeError):
    """MCP configuration or transport failure."""


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

    def __init__(self, config: McpServerConfig, workspace: Path) -> None:
        self.config = config
        self.workspace = workspace
        self.process: subprocess.Popen[str] | None = None
        self._reader: threading.Thread | None = None
        self._responses: queue.Queue[dict[str, Any]] = queue.Queue()
        self._write_lock = threading.Lock()
        self._counter = 0
        self._start()

    def _start(self) -> None:
        env = os.environ.copy()
        env.update(self.config.env)
        try:
            self.process = subprocess.Popen(
                [self.config.command, *self.config.args],
                cwd=self.workspace,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                env=env,
                bufsize=1,
            )
        except OSError as exc:
            raise McpError(f"无法启动 MCP server {self.config.name}: {exc}") from exc
        self._reader = threading.Thread(target=self._read_loop, name=f"mcp-{self.config.name}", daemon=True)
        self._reader.start()
        self._request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "minicc", "version": "0.2.0"},
        })
        self._notify("notifications/initialized", {})

    def _read_loop(self) -> None:
        assert self.process and self.process.stdout
        for line in self.process.stdout:
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(message, dict) and "id" in message:
                self._responses.put(message)

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        if not self.process or not self.process.stdin:
            return
        self.process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method, "params": params}) + "\n")
        self.process.stdin.flush()

    def _request(self, method: str, params: dict[str, Any], timeout: float = 30) -> dict[str, Any]:
        if not self.process or self.process.poll() is not None or not self.process.stdin:
            raise McpError(f"MCP server {self.config.name} 已退出")
        with self._write_lock:
            self._counter += 1
            request_id = self._counter
            self.process.stdin.write(json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}) + "\n")
            self.process.stdin.flush()
            while True:
                try:
                    response = self._responses.get(timeout=timeout)
                except queue.Empty as exc:
                    raise McpError(f"MCP server {self.config.name} 请求超时: {method}") from exc
                if response.get("id") == request_id:
                    if "error" in response:
                        raise McpError(str(response["error"]))
                    return response.get("result") or {}

    def list_tools(self) -> list[dict[str, Any]]:
        result = self._request("tools/list", {})
        tools = result.get("tools", [])
        return tools if isinstance(tools, list) else []

    def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        result = self._request("tools/call", {"name": name, "arguments": arguments})
        content = result.get("content", [])
        chunks: list[str] = []
        for item in content if isinstance(content, list) else []:
            if isinstance(item, dict) and item.get("type") == "text":
                chunks.append(str(item.get("text", "")))
            else:
                chunks.append(json.dumps(item, ensure_ascii=False))
        return ToolResult(
            status="error" if result.get("isError") else "ok",
            summary=f"MCP {self.config.name}/{name}",
            output="\n".join(chunks),
            security_tags=["untrusted", "mcp"],
        )

    def close(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()


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
                "clientInfo": {"name": "minicc", "version": "0.2.0"},
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
                if expect_id is None or int(event.get("id") or -1) == expect_id:
                    if "error" in event:
                        raise McpError(str(event["error"]))
                    return event.get("result") or {}
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
        return message.get("result") or {}

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

    def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        result = self._request("tools/call", {"name": name, "arguments": arguments})
        content = result.get("content", [])
        chunks: list[str] = []
        for item in content if isinstance(content, list) else []:
            if isinstance(item, dict) and item.get("type") == "text":
                chunks.append(str(item.get("text", "")))
            else:
                chunks.append(json.dumps(item, ensure_ascii=False))
        return ToolResult(
            status="error" if result.get("isError") else "ok",
            summary=f"MCP {self.config.name}/{name}",
            output="\n".join(chunks),
            security_tags=["untrusted", "mcp"],
        )

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

    def _client(self, config: McpServerConfig) -> Any:
        if config.name not in self.clients:
            if config.transport == "http":
                self.clients[config.name] = McpHttpClient(config, self.workspace)
            else:
                self.clients[config.name] = McpStdioClient(config, self.workspace)
        return self.clients[config.name]

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

    def tool_specs(self) -> list[ToolSpec]:
        specs: list[ToolSpec] = []
        for config in self.configs:
            client = self._client(config)
            for item in client.list_tools():
                name = str(item.get("name", ""))
                if not name:
                    continue
                safe_name = f"mcp__{config.name}__{name}"[:128]
                schema = item.get("inputSchema") if isinstance(item.get("inputSchema"), dict) else {"type": "object", "properties": {}}
                specs.append(ToolSpec(
                    safe_name,
                    f"MCP {config.name}: {item.get('description', name)}",
                    "readonly" if config.read_only else "exec",
                    (),
                    lambda args, c=client, n=name: c.call_tool(n, args),
                    input_schema=schema,
                ))
        return specs

    def close(self) -> None:
        for client in self.clients.values():
            client.close()
