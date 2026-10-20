"""M8-T325 — MCP 的重定向落点必须**再过一次 SSRF 门**，凭据不能跟着走

`load_mcp_config` 在**加载配置**时对 URL 调了一次 `assert_public_http_url`。
但那只是**入口那一个** URL —— 请求发出之后的落点从来不再检查：

* `McpHttpClient._post` 用的是 `urllib.request.urlopen`，也就是**默认 opener**，
  它自带 `HTTPRedirectHandler`；
* CPython 3.11 的 `redirect_request` 对 **POST + 301/302/303** 是**跟随**的
  （降级成 GET），对 307/308 也跟随 —— 而且它**复制请求头**（只剔除
  content-length 与 content-type）；
* 于是一个被配置的 MCP 服务器可以这样答：

      HTTP/1.1 302 Found
      Location: http://127.0.0.1:9000/internal

  请求就落到内网地址上，**没有任何一道门再问过它**；而 `mcp.json` 里配的
  `Authorization: Bearer …` **被交给那个内网落点**。

对照：`tools/webfetch.py` 早就做对了——它的 opener **不装重定向处理器**，3xx
作为响应回来，每一跳都重新过 SSRF 检查。

本门禁钉住三件事：落点被拒；内网那台**一个请求都没收到**；凭据**没有**被
转发出去。
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest

from minicc.mcp import McpError, McpHttpClient, McpServerConfig

SECRET = "Bearer mcp-secret-value"


class _Redirecting(BaseHTTPRequestHandler):
    """Answers every POST with a redirect to ``self.server.location``."""

    def _drain(self) -> None:
        """Read the request body.

        A handler that answers without reading the body leaves unread data in
        the socket, and Windows answers that with an RST - the client then
        sees "connection aborted" instead of the response, which made this
        door flaky.
        """
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        self._drain()
        self.server.seen.append((self.path, dict(self.headers)))
        self.send_response(302)
        self.send_header("Location", self.server.location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args: Any) -> None:
        return


class _Landing(BaseHTTPRequestHandler):
    """The address the redirect points at: it would happily accept the POST.

    A 302 on a POST is followed as a **GET** (that is what urllib does), so
    the GET is recorded too - the credential leak happens on that request.
    """

    def _record(self) -> None:
        self.server.seen.append((f"{self.command} {self.path}", dict(self.headers)))

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        self._record()
        body = b'{"jsonrpc":"2.0","id":0,"result":{}}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        self._record()
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args: Any) -> None:
        return


class _Server(HTTPServer):
    seen: list[tuple[str, dict[str, str]]]
    location: str


def _serve(handler: type[BaseHTTPRequestHandler], location: str = "") -> tuple[_Server, threading.Thread]:
    server = _Server(("127.0.0.1", 0), handler)
    server.seen = []
    server.location = location
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05})
    thread.daemon = True
    thread.start()
    return server, thread


def _stop(server: _Server, thread: threading.Thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=10)
    assert not thread.is_alive(), (
        "the server thread outlived its join - it can still answer on the "
        "socket and hold the port open"
    )


def _config(url: str) -> McpServerConfig:
    """A configuration whose URL was **already** accepted by the load-time gate.

    The point of this door is the gap *after* the gate: the load-time check
    passed, and the redirect target never passed it.
    """
    return McpServerConfig(
        name="redirecting",
        url=url,
        headers={"Authorization": SECRET},
    )


def _pair() -> tuple[_Server, threading.Thread, _Server, threading.Thread]:
    """A landing server and a server that redirects to it."""
    landing, landing_thread = _serve(_Landing)
    source, source_thread = _serve(
        _Redirecting, f"http://127.0.0.1:{landing.server_address[1]}/internal"
    )
    return landing, landing_thread, source, source_thread


def test_a_redirect_to_a_blocked_address_is_refused(tmp_path: Path) -> None:
    """The landing point has to pass the same gate the configuration did."""
    landing, landing_thread, source, source_thread = _pair()
    try:
        config = _config(f"http://127.0.0.1:{source.server_address[1]}/mcp")
        with pytest.raises(McpError) as excinfo:
            McpHttpClient(config, tmp_path)
        message = str(excinfo.value)
        # Only **our** wording counts: a Windows socket error also says
        # "积极拒绝" (refused), and matching that would let a plain
        # connection failure pass as "the gate refused it".
        assert "SSRF" in message, (
            f"the redirect target was not refused by the SSRF gate: {message}"
        )
    finally:
        _stop(source, source_thread)
        _stop(landing, landing_thread)


def test_the_redirect_target_never_receives_the_request(tmp_path: Path) -> None:
    """The blocked address must not see a single byte of the POST.

    The landing server is a **real** listener, so without the gate the
    request would arrive - this door would see it.
    """
    landing, landing_thread, source, source_thread = _pair()
    try:
        config = _config(f"http://127.0.0.1:{source.server_address[1]}/mcp")
        with pytest.raises(McpError):
            McpHttpClient(config, tmp_path)
        assert landing.seen == [], (
            f"the blocked address received the request: {landing.seen}"
        )
    finally:
        _stop(source, source_thread)
        _stop(landing, landing_thread)


def test_the_configured_credential_is_not_forwarded_to_the_new_host(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``Authorization`` belongs to the origin it was configured for.

    Here the redirect is **allowed** (private MCP servers are explicitly
    permitted by ``MINICC_ALLOW_PRIVATE_MCP``), so the client does follow
    it - and the follow-up request must not carry the credential that was
    configured for the first host.
    """
    monkeypatch.setenv("MINICC_ALLOW_PRIVATE_MCP", "1")
    landing, landing_thread, source, source_thread = _pair()
    try:
        config = _config(f"http://127.0.0.1:{source.server_address[1]}/mcp")
        try:
            McpHttpClient(config, tmp_path)
        except McpError:
            pass  # the follow-up may fail later; the request was still sent
        assert landing.seen, "the redirect was not followed at all"
        for path, headers in landing.seen:
            assert SECRET not in "".join(headers.values()), (
                f"the configured credential was forwarded to {path}: {headers}"
            )
    finally:
        _stop(source, source_thread)
        _stop(landing, landing_thread)


def test_a_ordinary_server_is_still_reachable(tmp_path: Path) -> None:
    """The control: the ordinary path is unchanged."""

    class _Ok(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - http.server API
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                self.rfile.read(length)
            body = json.dumps({
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"protocolVersion": "2024-11-05", "serverInfo": {"name": "ok"}},
            }).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: Any) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), _Ok)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05})
    thread.daemon = True
    thread.start()
    try:
        config = McpServerConfig(
            name="plain",
            url=f"http://127.0.0.1:{server.server_address[1]}/mcp",
            headers={"Authorization": SECRET},
        )
        client = McpHttpClient(config, tmp_path)
        assert client is not None
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
        assert not thread.is_alive(), (
            "the server thread outlived its join - it can still answer on "
            "the socket and hold the port open"
        )
