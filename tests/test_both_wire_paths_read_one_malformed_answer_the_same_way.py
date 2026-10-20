"""M8-T334 — 同一份畸形网关输出，两条解析路径不许给出两种行为

OpenAI 兼容网关偶尔会回一个**无名**的工具调用（内容过滤/工具截断时），或者
回一个**空的** `choices`。而两条路径的读法不同：

* **流式**的装配器 ``_assembled_tool_calls`` 有 ``if not slot["name"]: continue``
  → 无名的调用**被丢掉**；
* **非流式**的 ``_to_response`` 把它**留着** → loop 派发出一次
  ``tool=""`` 的调用 → 模型收到 "[TOOL_ERROR] 未知工具 ''"，**白白花掉一轮**；
* 而 ``_to_response`` 里的 ``response.choices[0]`` 在 ``choices: []`` 时抛
  **未捕获的 `IndexError`**（流式路径是 ``if not choices: continue`` ✓，Responses
  路径也是优雅处理的 ✓）。

本门禁钉住：两条路径对同一份畸形输出一致；空 `choices` 是一个**回答**而不是
一次崩溃。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from minicc.llm.openai_provider import OpenAICompatibleProvider


def _tool_call(name: str, call_id: str = "1") -> Any:
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments="{}"),
    )


def _response(*tool_calls: Any, choices: Any = None) -> Any:
    if choices is None:
        choices = [SimpleNamespace(
            message=SimpleNamespace(
                content=None,
                tool_calls=list(tool_calls) or None,
                reasoning_content=None,
            ),
            finish_reason="tool_calls",
            reasoning_content=None,
        )]
    return SimpleNamespace(choices=choices, usage=None, model="m")


def test_a_nameless_call_is_dropped() -> None:
    """The streaming path drops it; the one-shot path must too."""
    response = OpenAICompatibleProvider._to_response(_response(_tool_call("")))
    assert response.tool_calls == [], response.tool_calls


def test_a_nameless_call_does_not_hide_the_named_ones() -> None:
    """Only the nameless one goes."""
    response = OpenAICompatibleProvider._to_response(
        _response(_tool_call(""), _tool_call("read_file", "2"))
    )
    assert len(response.tool_calls) == 1, response.tool_calls
    assert response.tool_calls[0]["function"]["name"] == "read_file", response.tool_calls


def test_an_empty_choices_is_an_answer_not_a_crash() -> None:
    """``choices[0]`` used to raise a bare IndexError."""
    response = OpenAICompatibleProvider._to_response(_response(choices=[]))
    assert response.tool_calls == [], response.tool_calls
    assert response.content == "", response.content
    assert response.finish_reason == "stop", response.finish_reason


def test_the_ordinary_response_is_unchanged() -> None:
    """The control: a normal answer still comes through."""
    payload = SimpleNamespace(
        choices=[SimpleNamespace(
            message=SimpleNamespace(
                content="hello",
                tool_calls=[_tool_call("read_file")],
                reasoning_content=None,
            ),
            finish_reason="tool_calls",
            reasoning_content=None,
        )],
        usage=None,
        model="m",
    )
    response = OpenAICompatibleProvider._to_response(payload)
    assert response.content == "hello", response.content
    assert len(response.tool_calls) == 1, response.tool_calls
    assert response.tool_calls[0]["function"]["name"] == "read_file", response.tool_calls
