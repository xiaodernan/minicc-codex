"""WebFetch tool tests: extraction, truncation, and SSRF guard."""

from __future__ import annotations

import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from minicc.tools.webfetch import (
    FetchDeniedError,
    build_tool_result,
    fetch_url_text,
    webfetch,
)

HTML_PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Minicc 测试页</title>
<style>body { color: red }</style></head>
<body>
<h1>主标题</h1>
<script>window.tracked = "should-not-appear";</script>
<p>第一段内容，包含关键词 minicc-fetch。</p>
<ul><li>列表项甲</li><li>列表项乙</li></ul>
<h2>第二节</h2>
<p>第二段内容。</p>
</body></html>"""


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - http.server naming
        if self.path == "/html":
            body = HTML_PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
        elif self.path == "/plain":
            body = "纯文本内容 plain-text-body".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
        elif self.path == "/binary":
            body = b"\x89PNG-fake-binary"
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
        elif self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/html")
            body = b""
        elif self.path == "/redirect-evil":
            # Second hop points at a host that resolves to loopback; the guard
            # must re-validate every hop and refuse to follow it.
            self.send_response(302)
            self.send_header("Location", "http://evil.test/html")
            body = b""
        elif self.path == "/server-error":
            body = b"boom"
            self.send_response(500)
            self.send_header("Content-Type", "text/plain")
        elif self.path == "/big":
            body = ("x" * 700_000).encode("ascii")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
        else:
            body = b"not found"
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


@pytest.fixture()
def local_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def test_ssrf_guard_rejects_loopback_by_default(local_server):
    # The public API reports the rejection in the error field; the registry
    # handler turns it into a ToolError.
    result = fetch_url_text(f"{local_server}/html")
    assert "SSRF" in result["error"]
    assert result["text"] == ""


def test_html_extraction(local_server, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MINICC_ALLOW_PRIVATE_FETCH", "1")
    result = fetch_url_text(f"{local_server}/html")
    assert result["error"] == ""
    assert result["title"] == "Minicc 测试页"
    text = result["text"]
    assert "# 主标题" in text
    assert "第一段内容" in text
    assert "- 列表项甲" in text
    assert "## 第二节" in text
    assert "should-not-appear" not in text
    assert "color: red" not in text
    assert result["truncated"] is False


def test_plain_text_passthrough(local_server, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MINICC_ALLOW_PRIVATE_FETCH", "1")
    result = fetch_url_text(f"{local_server}/plain")
    assert result["error"] == ""
    assert "plain-text-body" in result["text"]
    assert result["title"] == ""


def test_redirect_followed(local_server, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MINICC_ALLOW_PRIVATE_FETCH", "1")
    result = fetch_url_text(f"{local_server}/redirect")
    assert result["error"] == ""
    assert result["final_url"].endswith("/html")
    assert result["title"] == "Minicc 测试页"


def test_binary_content_type_rejected(local_server, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MINICC_ALLOW_PRIVATE_FETCH", "1")
    result = fetch_url_text(f"{local_server}/binary")
    assert "不支持的内容类型" in result["error"]


def test_server_error_lands_in_error_field(local_server, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MINICC_ALLOW_PRIVATE_FETCH", "1")
    result = fetch_url_text(f"{local_server}/server-error")
    assert "HTTP 500" in result["error"]


def test_oversized_page_truncated(local_server, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MINICC_ALLOW_PRIVATE_FETCH", "1")
    result = fetch_url_text(f"{local_server}/big", max_bytes=4096)
    assert result["truncated"] is True
    assert result["bytes"] <= 4096


def test_invalid_url_raises_value_error():
    with pytest.raises(ValueError):
        fetch_url_text("ftp://example.com/file")
    with pytest.raises(ValueError):
        fetch_url_text("   ")


def test_build_tool_result_error_raises_tool_error(local_server):
    result = fetch_url_text(f"{local_server}/server-error", timeout=5)
    # Loopback is denied before connecting; force an error result by direct dict.
    from minicc.tools.registry import ToolError

    with pytest.raises(ToolError):
        build_tool_result({"error": "HTTP 500，页面不可用", "url": "x"})


def test_build_tool_result_success_shape(local_server, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MINICC_ALLOW_PRIVATE_FETCH", "1")
    fetched = fetch_url_text(f"{local_server}/html")
    tool_result = build_tool_result(fetched)
    assert tool_result.status == "ok"
    assert "untrusted" in tool_result.security_tags
    assert "network" in tool_result.security_tags
    assert tool_result.data["title"] == "Minicc 测试页"
    assert "不可信数据" in tool_result.output


def test_webfetch_handler_rejects_empty_url():
    from minicc.tools.registry import ToolError

    with pytest.raises(ToolError):
        webfetch({"url": ""})


# ---------------------------------------------------------------------------
# M3-T3: SSRF IP pinning (resolve once, validate, dial the pinned IP)
# ---------------------------------------------------------------------------


def test_pinning_dials_validated_ip_not_rebind_target(
    monkeypatch: pytest.MonkeyPatch,
):
    """DNS rebinding: guard resolves a public IP; connect must dial that exact IP.

    A naive client that re-resolved at connect time could be tricked into hitting
    loopback. Pinning closes that window, so we assert the socket is created
    against the validated public address and never 127.0.0.1.
    """
    monkeypatch.delenv("MINICC_ALLOW_PRIVATE_FETCH", raising=False)
    public_ip = "93.184.216.34"
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, *a, **k: [(2, 1, 6, "", (public_ip, 0))],
    )
    dialed: dict[str, object] = {}

    def fake_create_connection(address, *args, **kwargs):
        dialed["address"] = address
        raise OSError("test: no real network egress")

    monkeypatch.setattr(socket, "create_connection", fake_create_connection)

    result = fetch_url_text("http://rebind.test/html")
    assert dialed.get("address", (None,))[0] == public_ip
    assert result["text"] == ""
    assert result["error"]  # connection failed, but only after dialing the safe IP


def test_redirect_hop_to_loopback_denied_without_env(
    local_server, monkeypatch: pytest.MonkeyPatch
):
    """Every hop is re-validated: a redirect to a loopback host is refused.

    Runs with the guard *enabled* (no MINICC_ALLOW_PRIVATE_FETCH). Hop 1
    (good.test) is pinned to a public IP that we route to the local server; the
    302 then points at evil.test, which resolves to 127.0.0.1 and must be denied
    before any connection is made.
    """
    monkeypatch.delenv("MINICC_ALLOW_PRIVATE_FETCH", raising=False)
    port = local_server.rsplit(":", 1)[1]
    public_ip = "93.184.216.34"
    real_getaddrinfo = socket.getaddrinfo

    def fake_getaddrinfo(host, *args, **kwargs):
        if host == "good.test":
            return [(2, 1, 6, "", (public_ip, 0))]
        if host == "evil.test":
            return [(2, 1, 6, "", ("127.0.0.1", 0))]
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    real_cc = socket.create_connection

    def fake_cc(address, *args, **kwargs):
        host, target_port = address[0], address[1]
        if host == public_ip:
            host = "127.0.0.1"
        return real_cc((host, target_port), *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fake_cc)

    result = fetch_url_text(f"http://good.test:{port}/redirect-evil")
    assert "SSRF" in result["error"]
    assert result["text"] == ""
