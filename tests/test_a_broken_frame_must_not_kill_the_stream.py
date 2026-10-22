"""M8-T359 — 流式帧的编号也是网关给的：读不出来不该把整条流掐断

Anthropic 的 SSE 帧里，`index`（工具调用分片的编号 ✓）是**我们自己解析**的字段
✓（OpenAI 那条线的分片编号由 SDK 解析 ✓，所以它永远是个整数 ✓）。而这里用的是
裸的 `int(event.get("index") or 0)` ✓ —— 网关把这一帧的编号写坏（对象 ✓ / 数组
✓ / 非数字字符串 ✓）时，**TypeError** ✓ 从流里抛出去 ✓ → 整轮任务死掉 ✓。

同一条"网关畸形输出"这一族（名字 ✓、id ✓、参数 ✓、计数器 ✓），这一项是**帧的
编号** ✓。

本门钉住：编号坏掉的帧**不抛** ✓（那一帧被跳过，流继续 ✓）；控制组——正常编号
的帧照旧被归到同一个工具调用上 ✓。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from minicc.llm.anthropic_provider import _consume_anthropic_sse


class _FakeResponse:
    def __init__(self, lines: list[str]) -> None:
        self._lines = list(lines)

    async def aiter_lines(self):
        for line in self._lines:
            yield line


def _frame(payload: dict[str, Any]) -> str:
    return "data: " + json.dumps(payload, ensure_ascii=False)


async def _consume(lines: list[str]) -> dict[str, Any]:
    emitted = {"chars": 0}
    return await _consume_anthropic_sse(
        _FakeResponse(lines), lambda text: None, emitted
    )


def test_a_broken_frame_index_does_not_kill_the_stream() -> None:
    """The observable: the stream keeps going."""
    parsed = asyncio.run(_consume([
        _frame({
            "type": "content_block_start",
            "index": {"nope": 1},
            "content_block": {"type": "tool_use", "id": "t1", "name": "read_file", "input": {}},
        }),
        _frame({
            "type": "message_delta",
            "delta": {"stop_reason": "tool_use"},
            "usage": {"input_tokens": 3, "output_tokens": 2},
        }),
    ]))
    assert parsed["stop_reason"] == "tool_use", parsed


def test_a_block_that_is_not_an_object_does_not_kill_the_stream() -> None:
    """The JSON path skips such a block; the stream path must not raise."""
    parsed = asyncio.run(_consume([
        _frame({
            "type": "content_block_start",
            "index": 1,
            "content_block": ["not", "an", "object"],
        }),
        _frame({
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn"},
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }),
    ]))
    assert parsed["stop_reason"] == "end_turn", parsed


def test_a_delta_that_is_not_an_object_does_not_kill_the_stream() -> None:
    parsed = asyncio.run(_consume([
        _frame({"type": "content_block_delta", "index": 1, "delta": "not an object"}),
        _frame({
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn"},
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }),
    ]))
    assert parsed["stop_reason"] == "end_turn", parsed


def test_a_well_formed_index_still_groups_the_fragments() -> None:
    """The control: the ordinary path is untouched."""
    parsed = asyncio.run(_consume([
        _frame({
            "type": "content_block_start",
            "index": 1,
            "content_block": {"type": "tool_use", "id": "t1", "name": "read_file", "input": {}},
        }),
        _frame({
            "type": "content_block_delta",
            "index": 1,
            "delta": {"type": "input_json_delta", "partial_json": '{"path": "a.py"}'},
        }),
    ]))
    assert list(parsed["tools"]) == [1], parsed["tools"]
    assert parsed["tools"][1]["json"] == '{"path": "a.py"}', parsed["tools"][1]
