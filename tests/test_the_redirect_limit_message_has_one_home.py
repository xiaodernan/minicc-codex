"""M8-T491 — 重定向上限判词两个家：MCP HTTP 传输与 webfetch 各拼一句

「重定向超过 N 次，已停止跟踪」有两个家：`mcp.py` 的 HTTP 传输（主语是
server 名）与 `tools/webfetch.py` 的抓取循环（裸句）。两个 HTTP 客户端放
弃时的判词各拼一遍——一个改了措辞另一个没跟上，就是一类用户从没见过的
错误消息。

家安在 `minicc/netguard.py`——它的 docstring 本来就写着「Shared SSRF
checks for webfetch and HTTP MCP URLs」，这两个客户端共用的模块，重定向
上限正是它们共有的另一件事。两个客户端各自的重定向上限常量
（MAX_MCP_REDIRS / MAX_REDIRECTS）是两份独立策略，不合并。
"""

from __future__ import annotations

import ast
import urllib.error
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/netguard.py"
MCP = "minicc/mcp.py"
WEBFETCH = "minicc/tools/webfetch.py"
TAIL = "次，已停止跟踪"


def _literal_strings():
    """Every string literal's text - f-string parts joined, so a
    hand-written f-string is seen as one literal, not its pieces."""
    for path in sorted(PACKAGE.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        inside_fstring: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                for child in ast.iter_child_nodes(node):
                    inside_fstring.add(id(child))
        for node in ast.walk(tree):
            if id(node) in inside_fstring:
                continue
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                yield path, node.lineno, node.value
            elif isinstance(node, ast.JoinedStr):
                parts = [
                    part.value
                    for part in node.values
                    if isinstance(part, ast.Constant) and isinstance(part.value, str)
                ]
                yield path, node.lineno, "".join(parts)


def _sites(fragment: str) -> list[str]:
    return [
        f"{path.relative_to(REPO).as_posix()}:{lineno}"
        for path, lineno, text in _literal_strings()
        if fragment in text
    ]


def test_the_home_pins_both_shapes() -> None:
    from minicc.netguard import redirect_limit_message

    assert redirect_limit_message(3) == "重定向超过 3 次，已停止跟踪"
    assert (
        redirect_limit_message(3, "MCP HTTP server srv")
        == "MCP HTTP server srv 重定向超过 3 次，已停止跟踪"
    )


def test_the_verdict_is_spelled_exactly_once_in_the_package() -> None:
    offenders = _sites(TAIL)
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the redirect-limit verdict is spelled by hand outside its one home: "
        + ", ".join(offenders)
    )


def test_both_clients_ask_the_home() -> None:
    mcp = (REPO / MCP).read_text(encoding="utf-8")
    webfetch = (REPO / WEBFETCH).read_text(encoding="utf-8")
    assert mcp.count("redirect_limit_message(") == 1, (
        "the MCP HTTP transport must ask the home"
    )
    assert webfetch.count("redirect_limit_message(") == 1, (
        "the webfetch tool must ask the home"
    )


def _webfetch_module():
    """The module, not the tool function that shadows its name in the package."""
    from importlib import import_module

    return import_module("minicc.tools.webfetch")


def test_both_clients_share_one_object() -> None:
    from minicc import mcp
    from minicc.netguard import redirect_limit_message

    assert mcp.redirect_limit_message is redirect_limit_message
    assert _webfetch_module().redirect_limit_message is redirect_limit_message


def test_webfetch_gives_up_with_the_homes_sentence(monkeypatch) -> None:
    """Drive the real fetch loop: every hop redirects, the limit wins."""
    from minicc.netguard import redirect_limit_message

    webfetch = _webfetch_module()
    monkeypatch.setattr(webfetch, "_validate_url", lambda url: (None, "127.0.0.1"))
    monkeypatch.setattr(
        webfetch, "_download", lambda *args, **kwargs: (302, "", b"/next", False)
    )
    result = webfetch.fetch_url_text("http://example.invalid/x", max_redirects=2)
    assert result["error"] == redirect_limit_message(2)
    assert result["error"] == "重定向超过 2 次，已停止跟踪"


def test_the_mcp_client_gives_up_with_the_homes_sentence(
    monkeypatch, tmp_path: Path
) -> None:
    """Drive the real MCP POST loop: every hop redirects, the limit wins."""
    from minicc import mcp
    from minicc.mcp import MAX_MCP_REDIRECTS, McpHttpClient, McpServerConfig
    from minicc.netguard import redirect_limit_message

    monkeypatch.setattr(mcp, "assert_public_http_url", lambda *args, **kwargs: None)

    class _RedirectingOpener:
        def open(self, request, timeout=None):  # noqa: ANN001 - urllib API
            raise urllib.error.HTTPError(
                request.full_url, 302, "Found", {"Location": "/next"}, None
            )

    monkeypatch.setattr(mcp, "_MCP_OPENER", _RedirectingOpener())
    # The constructor initializes over the same POST path, so the redirect
    # loop runs before any explicit call.
    with pytest.raises(mcp.McpError) as excinfo:
        McpHttpClient(
            McpServerConfig(name="srv", url="http://mcp.invalid./mcp"), tmp_path
        )
    assert str(excinfo.value) == redirect_limit_message(
        MAX_MCP_REDIRECTS, "MCP HTTP server srv"
    )
