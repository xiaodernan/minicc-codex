"""M8-T335 — 一份"没有名字的工具调用"，每条解析线必须读到同一个答案

M8-T334 把「无名的调用是噪音，丢掉」定在了 chat-completions 的两条路径上，
但这条规则其实有**五个**读者，另外三个从未被修：

* Responses 解析路径 ``_responses_to_response``：无名 ``function_call`` 被
  **留着** → loop 派发 ``tool=""`` → 付费换一条 ``[TOOL_ERROR] 未知工具 ''``；
* 原生 Anthropic 的 JSON 路径 ``response_to_llm``：无名 ``tool_use`` 块被留着；
* 原生 Anthropic 的流式路径 ``_sse_to_llm``：无名 SSE 块被留着。

同一个畸形回答，五条线两种行为。谓词 ``is_nameless_tool_name`` 在
``minicc/llm/base.py`` 里只有一个家（仿 M8-T307 的 ``is_network_tool``〕，
每个读者直接问它。本门钉住：每条线上的无名调用被丢弃，且**不遮住**
同一回答里的有名调用；空白名字与空名字同样属于"没有目标"。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from minicc.llm.anthropic_provider import _sse_to_llm, response_to_llm
from minicc.llm.base import is_nameless_tool_name
from minicc.llm.openai_provider import OpenAICompatibleProvider


def _ns_call(name: str, call_id: str = "1") -> Any:
    return SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments="{}"))


def _chat_response(*tool_calls: Any) -> Any:
    return SimpleNamespace(
        choices=[SimpleNamespace(
            message=SimpleNamespace(
                content=None,
                tool_calls=list(tool_calls) or None,
                reasoning_content=None,
            ),
            finish_reason="tool_calls",
            reasoning_content=None,
        )],
        usage=None,
        model="m",
    )


def _responses_payload(*names_with_ids: tuple[str, str]) -> Any:
    output: list[dict[str, Any]] = []
    for name, call_id in names_with_ids:
        output.append({
            "type": "function_call",
            "call_id": call_id,
            "name": name,
            "arguments": "{}",
        })
    return {"output": output, "status": "completed", "usage": None, "model": "m"}


def _sse_parsed(*names_with_ids: tuple[str, str]) -> dict[str, Any]:
    tools: dict[int, dict[str, str]] = {}
    for index, (name, call_id) in enumerate(names_with_ids, start=1):
        tools[index] = {"id": call_id, "name": name, "json": '{"path": "a.py"}'}
    return {
        "text": "",
        "tools": tools,
        "usage": {},
        "stop_reason": "tool_use",
        "model": "m",
    }


def _anthropic_payload(*blocks: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": "claude-x",
        "stop_reason": "tool_use",
        "content": [
            {"type": "text", "text": "先看文件"},
            *blocks,
        ],
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


def test_the_responses_path_drops_the_nameless_call_too() -> None:
    """M8-T334's rule reaches the third OpenAI parse path."""
    response = OpenAICompatibleProvider._responses_to_response(
        _responses_payload(("", "1"), ("read_file", "2"))
    )
    assert len(response.tool_calls) == 1, response.tool_calls
    assert response.tool_calls[0]["function"]["name"] == "read_file"


def test_the_chat_completions_oneshot_path_asks_the_one_home() -> None:
    response = OpenAICompatibleProvider._to_response(
        _chat_response(_ns_call(""), _ns_call("read_file", "2"))
    )
    assert len(response.tool_calls) == 1, response.tool_calls
    assert response.tool_calls[0]["function"]["name"] == "read_file"


def test_the_streaming_assembler_asks_the_one_home() -> None:
    calls = OpenAICompatibleProvider._assembled_tool_calls({
        1: {"id": "1", "name": "", "arguments": "{}"},
        2: {"id": "2", "name": "read_file", "arguments": "{}"},
    })
    assert len(calls) == 1, calls
    assert calls[0]["function"]["name"] == "read_file"


def test_the_anthropic_json_path_drops_the_nameless_block() -> None:
    response = response_to_llm(
        _anthropic_payload(
            {"type": "tool_use", "id": "tu-1", "name": "", "input": {}},
            {"type": "tool_use", "id": "tu-2", "name": "read_file",
             "input": {"path": "a.py"}},
        ),
        "claude-x",
    )
    assert len(response.tool_calls) == 1, response.tool_calls
    assert response.tool_calls[0]["function"]["name"] == "read_file"
    # The text of the same answer is untouched by the drop.
    assert response.text == "先看文件"


def test_the_anthropic_stream_path_drops_the_nameless_slot() -> None:
    response = _sse_to_llm(_sse_parsed(("", "1"), ("read_file", "2")), "claude-x")
    assert len(response.tool_calls) == 1, response.tool_calls
    assert response.tool_calls[0]["function"]["name"] == "read_file"


def test_a_whitespace_only_name_is_as_targetless_as_an_empty_one() -> None:
    """The one home defines the predicate: both spellings name no tool."""
    assert is_nameless_tool_name("") is True
    assert is_nameless_tool_name("   ") is True
    assert is_nameless_tool_name("read_file") is False
    assert is_nameless_tool_name(None) is True
    response = OpenAICompatibleProvider._to_response(
        _chat_response(_ns_call("  "))
    )
    assert response.tool_calls == [], response.tool_calls
    response = response_to_llm(
        _anthropic_payload({"type": "tool_use", "id": "tu-3", "name": "  ", "input": {}}),
        "claude-x",
    )
    assert response.tool_calls == [], response.tool_calls
