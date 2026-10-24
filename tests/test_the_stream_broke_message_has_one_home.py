"""M8-T488 的邻居 — M8-T489 — 流中断判词三个家：两个通道各拼各的

一条流在**已经吐出字符之后**断掉，两个通道（Anthropic SSE 与 OpenAI
Responses）都抛各自的 partial error，消息里写着「stream broke after
delivering N chars: ExcType」。这句话有三个家：anthropic_provider 的两
处（重试循环里一处、SSE 消费器里一处，变量拼法还不一样——`{emitted}` 与
`{emitted['chars']}`）加 openai_provider 的一处。句子会经
``LLM 调用失败: {exc}`` 流进模型上下文——一个通道改了措辞而另一个没跟
上，就是模型在一种通道里从没见过的错误消息，而没有任何测试会红。

家安在 ``minicc/llm/base.py``，紧挨 T488 刚立的 ``stream_retry_summary``
——同一个「流的异常词汇表」。

``responses stream ended without a final response after N chars`` 是另一
个时刻（流没抛异常，只是没给最终响应），按前缀家族判别式留在原地，门禁
钉住它仍只有一个现场。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/llm/base.py"
ANTHROPIC = "minicc/llm/anthropic_provider.py"
OPENAI = "minicc/llm/openai_provider.py"
BROKE = "stream broke after delivering"
NO_FINAL = "ended without a final response"


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


def test_the_home_pins_both_channel_wordings() -> None:
    from minicc.llm.base import stream_broke_message

    assert (
        stream_broke_message("Anthropic", 5, RuntimeError("x"))
        == "Anthropic stream broke after delivering 5 chars: RuntimeError"
    )
    assert (
        stream_broke_message("responses", 0, ValueError())
        == "responses stream broke after delivering 0 chars: ValueError"
    )


def test_the_sentence_is_spelled_exactly_once_in_the_package() -> None:
    offenders = _sites(BROKE)
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the mid-stream break sentence is spelled by hand outside its one "
        "home: " + ", ".join(offenders)
    )


def test_both_channels_ask_the_home() -> None:
    anthropic = (REPO / ANTHROPIC).read_text(encoding="utf-8")
    openai = (REPO / OPENAI).read_text(encoding="utf-8")
    assert anthropic.count('stream_broke_message("Anthropic"') == 2, (
        "both Anthropic raise sites must ask the home"
    )
    assert openai.count('stream_broke_message("responses"') == 1, (
        "the Responses raise site must ask the home"
    )


def test_both_channels_share_one_object() -> None:
    from minicc.llm import anthropic_provider, base, openai_provider

    assert anthropic_provider.stream_broke_message is base.stream_broke_message
    assert openai_provider.stream_broke_message is base.stream_broke_message


def test_the_anthropic_consumer_reports_the_break_with_the_homes_sentence() -> None:
    """Drive the real SSE consumer: a delta, then a broken connection."""
    import asyncio
    import json

    from minicc.llm.anthropic_provider import AnthropicPartialError, _consume_anthropic_sse
    from minicc.llm.base import stream_broke_message

    class _BreakingResponse:
        async def aiter_lines(self):
            yield "data: " + json.dumps(
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "hello"},
                }
            )
            raise RuntimeError("connection reset")

    emitted = {"chars": 0}
    with pytest.raises(AnthropicPartialError) as excinfo:
        asyncio.run(
            _consume_anthropic_sse(_BreakingResponse(), lambda text: None, emitted)
        )
    assert emitted["chars"] == 5
    assert str(excinfo.value) == stream_broke_message(
        "Anthropic", 5, RuntimeError("connection reset")
    )
    assert str(excinfo.value) == (
        "Anthropic stream broke after delivering 5 chars: RuntimeError"
    )


def test_the_no_final_response_sentence_is_a_different_fact() -> None:
    """A stream that ended quietly is a different moment, one site."""
    offenders = _sites(NO_FINAL)
    assert len(offenders) == 1 and offenders[0].startswith(OPENAI + ":"), (
        "the no-final-response sentence is one fact with one site: "
        + ", ".join(offenders)
    )
