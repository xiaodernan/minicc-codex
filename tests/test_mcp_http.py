"""MCP streamable-HTTP transport tests: config validation and live client."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from minicc.mcp import McpError, McpHttpClient, McpManager, load_mcp_config


@pytest.fixture(autouse=True)
def _allow_loopback_mcp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINICC_ALLOW_PRIVATE_MCP", "1")


class _FakeMcpHandler(BaseHTTPRequestHandler):
    """Minimal MCP streamable-HTTP server: initialize/tools list/call."""

    def _reply(self, payload: dict, *, status: int = 200, content_type: str = "application/json", session: str = "") -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if session:
            self.send_header("Mcp-Session-Id", session)
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802 - http.server naming
        size = int(self.headers.get("Content-Length", "0"))
        message = json.loads(self.rfile.read(size).decode("utf-8"))
        method = message.get("method")
        session = self.headers.get("Mcp-Session-Id") or ""
        if method == "initialize":
            self._reply(
                {"jsonrpc": "2.0", "id": message.get("id"), "result": {"protocolVersion": "2025-03-26", "capabilities": {}}},
                session="sess-123",
            )
        elif method == "notifications/initialized":
            self._reply({}, status=202)
        elif method == "tools/list":
            if session != "sess-123":
                self._reply({"jsonrpc": "2.0", "id": message.get("id"), "error": {"code": -32001, "message": "missing session"}}, status=400)
                return
            self._reply({"jsonrpc": "2.0", "id": message.get("id"), "result": {"tools": [
                {"name": "echo", "description": "回显文本", "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}}},
            ]}})
        elif method == "tools/call":
            self._reply({"jsonrpc": "2.0", "id": message.get("id"), "result": {
                "content": [{"type": "text", "text": f"echo: {message['params']['arguments'].get('text', '')}"}],
                "isError": False,
            }})
        else:
            self._reply({"jsonrpc": "2.0", "id": message.get("id"), "error": {"code": -32601, "message": "unknown"}})

    def log_message(self, format: str, *args: object) -> None:
        return


def _start_serving(server: ThreadingHTTPServer) -> tuple[str, threading.Thread]:
    """Start the accept loop and hand back the url only once it has answered.

    M8-T68: the fake MCP handler speaks POST-only JSON-RPC, so the readiness
    request is an initialize — any reply below 500 proves the thread accepted.
    """
    served: list[BaseException] = []

    def _serve() -> None:
        try:
            server.serve_forever(poll_interval=0.05)
        except BaseException as exc:
            served.append(exc)

    thread = threading.Thread(target=_serve, daemon=True, name="minicc-test-server")
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/mcp"
    deadline = time.monotonic() + 10.0
    while True:
        if served or not thread.is_alive():
            raise AssertionError(
                f"the test HTTP server thread {thread.name!r} died before answering "
                f"POST /mcp at {url}: {served!r}"
            )
        request = urllib.request.Request(
            url,
            data=json.dumps({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as probe:
                answered = probe.status < 500
        except urllib.error.HTTPError as exc:
            answered = exc.code < 500
        except OSError:
            answered = False
        if answered:
            return url, thread
        if time.monotonic() >= deadline:
            raise AssertionError(
                f"the test HTTP server thread {thread.name!r} never answered POST /mcp "
                f"within 10s at {url}"
            )
        time.sleep(0.02)


@pytest.fixture()
def mcp_url():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeMcpHandler)
    url, thread = _start_serving(server)
    yield url
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def test_config_requires_command_or_url(tmp_path: Path) -> None:
    config_dir = tmp_path / ".minicc"
    config_dir.mkdir()
    (config_dir / "mcp.json").write_text('{"servers": {"broken": {"args": []}}}', encoding="utf-8")
    with pytest.raises(McpError, match="command 或 url"):
        load_mcp_config(tmp_path)


def test_config_url_must_be_http(tmp_path: Path) -> None:
    config_dir = tmp_path / ".minicc"
    config_dir.mkdir()
    (config_dir / "mcp.json").write_text('{"servers": {"x": {"url": "ftp://host/mcp"}}}', encoding="utf-8")
    with pytest.raises(McpError, match="http/https"):
        load_mcp_config(tmp_path)


def test_http_mcp_rejects_loopback_without_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MINICC_ALLOW_PRIVATE_MCP", raising=False)
    config_dir = tmp_path / ".minicc"
    config_dir.mkdir()
    (config_dir / "mcp.json").write_text(
        '{"servers": {"remote": {"url": "http://127.0.0.1:3117/mcp"}}}',
        encoding="utf-8",
    )
    with pytest.raises(McpError, match="SSRF"):
        load_mcp_config(tmp_path)


def test_config_loads_http_server(tmp_path: Path) -> None:
    config_dir = tmp_path / ".minicc"
    config_dir.mkdir()
    (config_dir / "mcp.json").write_text(json.dumps({
        "servers": {
            "remote": {
                "url": "http://127.0.0.1:3117/mcp",
                "headers": {"Authorization": "Bearer test-token"},
                "read_only": True,
            }
        }
    }), encoding="utf-8")
    configs = load_mcp_config(tmp_path)
    assert len(configs) == 1
    assert configs[0].transport == "http"
    assert configs[0].url == "http://127.0.0.1:3117/mcp"
    assert configs[0].headers["Authorization"] == "Bearer test-token"
    assert configs[0].read_only is True


def test_http_client_handshake_tools_and_call(mcp_url: str) -> None:
    from minicc.mcp import McpServerConfig

    http_config = McpServerConfig(name="local", url=mcp_url, read_only=True)
    client = McpHttpClient(http_config, Path("."))
    assert client.session_id == "sess-123"
    tools = client.list_tools()
    assert [tool["name"] for tool in tools] == ["echo"]
    result = client.call_tool("echo", {"text": "你好"})
    assert result.status == "ok"
    # M5-T1: MCP output now flows through split_output into head/tail (the
    # model-facing render()), so a 500k-char server reply can't flood the
    # prompt. Assert on render(), not the now-empty raw .output.
    assert "echo: 你好" in result.render()
    assert "untrusted" in result.security_tags
    client.close()


def test_http_client_sends_auth_header(mcp_url: str, tmp_path: Path) -> None:
    from minicc.mcp import McpServerConfig

    seen_headers: dict[str, str] = {}

    class _RecordingHandler(_FakeMcpHandler):
        def do_POST(self) -> None:  # noqa: N802
            seen_headers.update({k: v for k, v in self.headers.items() if k.lower() in {"authorization", "mcp-session-id"}})
            super().do_POST()

    server = ThreadingHTTPServer(("127.0.0.1", 0), _RecordingHandler)
    url, thread = _start_serving(server)
    try:
        http_config = McpServerConfig(name="authed", url=url, headers={"Authorization": "Bearer tok-1"})
        client = McpHttpClient(http_config, tmp_path)
        client.list_tools()
        assert seen_headers.get("Authorization") == "Bearer tok-1"
        # Session id is replayed after initialize.
        assert seen_headers.get("Mcp-Session-Id") == "sess-123"
        client.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_manager_registers_http_tools(tmp_path: Path, mcp_url: str) -> None:
    config_dir = tmp_path / ".minicc"
    config_dir.mkdir()
    (config_dir / "mcp.json").write_text(json.dumps({
        "servers": {"remote": {"url": mcp_url, "read_only": True}}
    }), encoding="utf-8")
    manager = McpManager(tmp_path)
    try:
        specs = manager.tool_specs()
        assert [spec.name for spec in specs] == ["mcp__remote__echo"]
        assert manager.status()["servers"][0]["transport"] == "http"
        # read_only server maps tools to readonly risk.
        assert specs[0].risk == "readonly"
    finally:
        manager.close()


def test_manager_unreachable_http_server_raises(tmp_path: Path) -> None:
    config_dir = tmp_path / ".minicc"
    config_dir.mkdir()
    (config_dir / "mcp.json").write_text(json.dumps({
        "servers": {"ghost": {"url": "http://127.0.0.1:9/mcp"}}
    }), encoding="utf-8")
    manager = McpManager(tmp_path)
    try:
        with pytest.raises(McpError):
            manager.tool_specs()
    finally:
        manager.close()
