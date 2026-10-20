"""M8-T296 / M8-T297 — 一份畸形输入不该让整次任务崩掉

两处都是**裸异常**从模块里逃出去：

* M8-T296（`agent/context.py`）：合并检查点时读 `archive` 计数器，假定
  ``archive`` 是对象、计数是数字。而检查点是**任何**一条消息里恰好含
  `[CONTEXT COMPACTED]` 的 JSON —— 一条 ``"archive": "nope"`` 就能让
  `AttributeError` 抛进压缩，而压缩在 agent loop 的 **try 之外**被调用，
  整次任务以未处理异常结束。
* M8-T297（`tools/webfetch.py`）：页面的字符集名交给 `bytes.decode()`，
  而 Python 对**未知的编码名**抛 `LookupError`（`errors="replace"` 只覆盖
  *解码*错误，不覆盖*未知的编码*）。于是 `<meta charset="utf8mb4">` 让工具
  回答"未处理异常"，而不是"这个页面的编码我不认识"。

本门禁钉住两处。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from minicc.agent.context import compact_with_checkpoint


# --- M8-T296: a malformed checkpoint must not kill the run -------------------


def _messages_with_checkpoint(checkpoint: dict[str, Any]) -> list[dict[str, Any]]:
    marker = "[CONTEXT COMPACTED]\n" + json.dumps(checkpoint, ensure_ascii=False)
    return [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "A" * 300},
        {"role": "user", "content": marker},
        {"role": "assistant", "content": "B" * 300},
        {"role": "user", "content": "C" * 300},
        {"role": "assistant", "content": "D" * 300},
    ]


@pytest.mark.parametrize(
    "archive",
    [
        "nope",
        123,
        [],
        {"messages": "abc"},
        {"messages": None},
        {"characters": "x"},
    ],
)
def test_a_malformed_archive_does_not_kill_the_compaction(
    archive: Any,
) -> None:
    """It used to raise out of the compaction, and the compaction is fatal."""
    messages = _messages_with_checkpoint({
        "version": 3,
        "archive": archive,
        "objectives": ["做点事"],
    })
    compacted, checkpoint = compact_with_checkpoint(messages, threshold=100, keep_recent=2)
    assert compacted, "the conversation was compacted away entirely"
    assert isinstance(checkpoint, dict)
    assert isinstance(checkpoint.get("archive", {}).get("messages", 0), int)


def test_a_well_formed_checkpoint_still_merges() -> None:
    """The control: the ordinary path is unchanged."""
    messages = _messages_with_checkpoint({
        "version": 3,
        "archive": {"messages": 4, "characters": 100},
        "objectives": ["做点事"],
    })
    _compacted, checkpoint = compact_with_checkpoint(messages, threshold=100, keep_recent=2)
    assert checkpoint.get("objectives"), checkpoint


# --- M8-T297: an unknown charset is an answer, not a crash ------------------


class _FakeResponse:
    def __init__(self, payload: bytes, content_type: str) -> None:
        self.status = 200
        self.headers = {"Content-Type": content_type}
        self._payload = payload

    def read(self, *_args: Any) -> bytes:
        return self._payload

    def geturl(self) -> str:
        return "https://example.com/"

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args: Any) -> None:
        return None


class _FakeOpener:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    def open(self, *_args: Any, **_kwargs: Any) -> _FakeResponse:
        return self._response


def _fetch_with(payload: bytes, content_type: str) -> dict[str, Any]:
    """Fetch through a fake opener, so no network is involved."""
    import importlib

    webfetch = importlib.import_module("minicc.tools.webfetch")
    response = _FakeResponse(payload, content_type)
    original_opener = webfetch._OPENER
    original_build = webfetch._build_opener
    webfetch._OPENER = _FakeOpener(response)  # type: ignore[assignment]
    webfetch._build_opener = lambda *_a, **_k: _FakeOpener(response)  # type: ignore[assignment]
    try:
        return webfetch.fetch_url_text("https://example.com/")
    finally:
        webfetch._OPENER = original_opener  # type: ignore[assignment]
        webfetch._build_opener = original_build  # type: ignore[assignment]


def test_an_unknown_meta_charset_is_handled(tmp_path: Path) -> None:
    """``utf8mb4`` is MySQL's spelling; Python has never heard of it."""
    result = _fetch_with(
        b"<html><head><meta charset=\"utf8mb4\"></head>"
        b"<body><p>hello</p></body></html>",
        "text/html; charset=utf-8",
    )
    assert not result.get("error"), f"the fetch failed: {result}"
    assert "hello" in str(result.get("text") or ""), result


def test_an_unknown_header_charset_is_handled(tmp_path: Path) -> None:
    """The same shape, in the response header."""
    result = _fetch_with(b'{"a": 1}', "application/json; charset=bogus")
    assert not result.get("error"), f"the fetch failed: {result}"
    assert '"a"' in str(result.get("text") or ""), result


def test_a_known_charset_is_still_honoured(tmp_path: Path) -> None:
    """The control: the ordinary path is unchanged."""
    result = _fetch_with(
        "<html><body><p>hello</p></body></html>".encode("utf-8"),
        "text/html; charset=utf-8",
    )
    assert not result.get("error"), result
    assert "hello" in str(result.get("text") or ""), result
