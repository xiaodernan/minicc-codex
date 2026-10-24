"""M8-T504 — 重定向判词两个家：_download 的两条 3xx 出口各拼一句

「重定向缺少 Location 头（状态码 X）」在 `webfetch.py` 的 `_download` 里
有两个家：opener.open 成功返回 3xx 但无 Location 头的出口，和 3xx 被
urllib 提升为 HTTPError 的出口。两处逐字相同（只有状态码来源不同）。一个
坏重定向从哪条路进来，读到的就是哪份拼写——一处改了措词其余没跟上，没有
任何测试会红。

家安在 `minicc/tools/webfetch.py` 模块层，紧挨 `_download`——两个调用点
都在它里面。
"""

from __future__ import annotations

import ast
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/tools/webfetch.py"
SENTENCE = "重定向缺少 Location 头（状态码 ）"


def _literal_shapes():
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


def _webfetch_module():
    import importlib

    return importlib.import_module("minicc.tools.webfetch")


def test_the_home_pins_the_sentence() -> None:
    from minicc.tools.webfetch import redirect_missing_location_message

    assert redirect_missing_location_message(302) == "重定向缺少 Location 头（状态码 302）"


def test_the_sentence_is_spelled_exactly_once_in_the_package() -> None:
    offenders = [
        f"{path.relative_to(REPO).as_posix()}:{lineno}"
        for path, lineno, text in _literal_shapes()
        if text == SENTENCE
    ]
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the redirect sentence is spelled by hand outside its one home: "
        + ", ".join(offenders)
    )


def test_both_exits_ask_the_home() -> None:
    source = (REPO / HOME).read_text(encoding="utf-8")
    assert source.count("redirect_missing_location_message(") == 3, (
        "webfetch.py asks the home "
        f"{source.count('redirect_missing_location_message(')} times, expected 3 "
        "(one definition plus two exits)"
    )


class _FakeResponse:
    def __init__(self, status: int, headers: dict[str, str]) -> None:
        self.status = status
        self.headers = headers

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args) -> bool:
        return False

    def read(self, size: int) -> bytes:
        return b""


def test_the_opened_3xx_exit_emits_the_homes_sentence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    webfetch = _webfetch_module()

    opener = SimpleNamespace(
        open=lambda request, timeout=None: _FakeResponse(302, {"Location": ""})
    )
    monkeypatch.setattr(webfetch, "_OPENER", opener)
    with pytest.raises(webfetch.FetchError) as excinfo:
        webfetch._download("https://example.test/", "", timeout=1.0, max_bytes=16)
    assert str(excinfo.value) == "重定向缺少 Location 头（状态码 302）", excinfo.value


def test_the_httperror_3xx_exit_emits_the_homes_sentence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    webfetch = _webfetch_module()

    def raise_http_error(request, timeout=None):
        raise urllib.error.HTTPError(
            "https://example.test/", 301, "Moved", {}, None
        )

    opener = SimpleNamespace(open=raise_http_error)
    monkeypatch.setattr(webfetch, "_OPENER", opener)
    with pytest.raises(webfetch.FetchError) as excinfo:
        webfetch._download("https://example.test/", "", timeout=1.0, max_bytes=16)
    assert str(excinfo.value) == "重定向缺少 Location 头（状态码 301）", excinfo.value
