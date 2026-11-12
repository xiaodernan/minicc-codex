"""M8-T820 — Responses 线上 ``name: null`` 的工具调用是噪音，不是叫 "None" 的工具。

真实网关（wkapi.pro /v1，gpt-6-sol）实测：Reasoning 模型偶尔在
``output[]`` 里夹一条 ``{"type":"function_call","name":null,...}``。
谓词 ``is_nameless_tool_name(None)`` 本已答 True（见 M8-T335 的门），
但 ``_responses_to_response`` 在问谓词**之前**先做了 ``str(...)``：
``str(None) == "None"`` —— 一个非空、非空白的字符串，于是谓词放行，
loop 派发 ``tool="None"``，registry 回 ``[UNKNOWN_TOOL] 未知工具 'None'``，
下一轮去重又添一条 ``[DUPLICATE_TOOL_CALL]``。两条都是**付费**的死轮。

M8-T334/T335 定的规矩是「没有目标名字的调用，每条线都当噪音丢掉」。
本门把这条规矩补到 ``name`` 是 JSON ``null``（而非缺失/空串/空白）的形状：
不管 wire 把「没有名字」写成缺字段、空串、空白还是 null，答案必须是同一个——
丢掉，且不遮住同一回答里的有名调用。

fake provider 从不发 ``name: null``，所以这条只有真实 wire 才照得出来。
"""

from __future__ import annotations

from typing import Any

from minicc.llm.openai_provider import OpenAICompatibleProvider


def _responses_payload(*items: dict[str, Any]) -> dict[str, Any]:
    return {"output": list(items), "status": "completed", "usage": None, "model": "gpt-6-sol"}


def _call(name: Any, call_id: str) -> dict[str, Any]:
    return {"type": "function_call", "call_id": call_id, "name": name, "arguments": "{}"}


def test_a_null_name_function_call_is_dropped_like_an_empty_one() -> None:
    """The real defect: ``name: null`` must not survive as the literal "None"."""
    response = OpenAICompatibleProvider._responses_to_response(
        _responses_payload(
            _call(None, "1"),
            _call("read_file", "2"),
        )
    )
    assert len(response.tool_calls) == 1, response.tool_calls
    assert response.tool_calls[0]["function"]["name"] == "read_file"


def test_a_null_name_alone_yields_no_tool_calls() -> None:
    response = OpenAICompatibleProvider._responses_to_response(
        _responses_payload(_call(None, "1"))
    )
    assert response.tool_calls == [], response.tool_calls


def test_every_nameless_spelling_on_the_responses_wire_is_noise() -> None:
    """Missing key, empty, whitespace and null are all "no target"."""
    nameless: list[dict[str, Any]] = [
        {"type": "function_call", "call_id": "a", "arguments": "{}"},        # missing name
        _call("", "b"),                                                      # empty
        _call("   ", "c"),                                                  # whitespace
        _call(None, "d"),                                                   # JSON null (real wire)
    ]
    for item in nameless:
        response = OpenAICompatibleProvider._responses_to_response(_responses_payload(item))
        assert response.tool_calls == [], (item, response.tool_calls)
