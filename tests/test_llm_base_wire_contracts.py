"""M8-T767 — ``minicc/llm/base.py`` 的线缆形状与一个主（one-home）助手。

这个模块是 LLM 线缆"长什么样"的一个家（M1-T4 / M8-T356 / M8-T359 …），
零同名测试（模块→测试映射发现）。钉住：

1. finish_reason 白名单（`stop` / `tool_calls`）——M1-T4：这之外一律不许
   作为正常终局；
2. `safe_int` / `as_dict` 容错（坏 framing 不再杀死整轮）；
3. `unique_tool_call_id` 的唯一性（重复 → `-dup2`/`-dup3`、空 → fallback）；
4. `tool_call` 嵌套 shape；`image_part`；`retry_detail`；summary 占位符；
5. `is_nameless_tool_name`（空白/空 → True）是噪声调用的一眼判据。
"""

from __future__ import annotations

import pytest

from minicc.llm import base


def test_terminal_finish_reasons_are_stop_and_tool_calls():
    assert base.TERMINAL_FINISH_REASONS == frozenset({"stop", "tool_calls"})


def test_safe_int_parses_and_falls_back():
    assert base.safe_int("42") == 42
    assert base.safe_int(None) is None
    assert base.safe_int(None, 0) == 0
    assert base.safe_int("not a number", 7) == 7


def test_as_dict_only_accepts_dicts():
    assert base.as_dict({"a": 1}) == {"a": 1}
    assert base.as_dict(["not", "a", "dict"]) == {}
    assert base.as_dict(None) == {}


def test_unique_tool_call_id_empty_uses_fallback():
    assert base.unique_tool_call_id("", "fallback-1") == "fallback-1"
    assert base.unique_tool_call_id(None, "fallback-1") == "fallback-1"


def test_unique_tool_call_id_deduplicates_against_seen():
    seen: set[str] = set()
    first = base.unique_tool_call_id("id-1", "fb", seen)
    second = base.unique_tool_call_id("id-1", "fb", seen)
    third = base.unique_tool_call_id("id-1", "fb", seen)
    assert first == "id-1"
    assert second == "id-1-dup2"
    assert third == "id-1-dup3"


def test_unique_tool_call_id_without_seen_is_per_call():
    assert base.unique_tool_call_id("id-1", "fb") == "id-1"
    assert base.unique_tool_call_id("id-1", "fb") == "id-1"


def test_retry_detail_shape():
    assert base.retry_detail(2, 3) == {"attempt": 2, "retry_limit": 3}


def test_stream_retry_summary_substitutes_attempt():
    summary = base.stream_retry_summary(3)
    assert "{attempt}" not in summary
    assert "3" in summary
    assert base.STREAM_RETRY_SUMMARY.count("{attempt}") == 1


def test_stream_broke_message_names_channel_and_exception():
    msg = base.stream_broke_message("chat", 123, ValueError())
    assert msg.startswith("chat stream broke after delivering 123 chars:")
    assert "ValueError" in msg


def test_tool_call_shape_is_the_function_nested_shape():
    assert base.tool_call("id-1", "read_file", '{"path":"x"}') == {
        "id": "id-1",
        "type": "function",
        "function": {"name": "read_file", "arguments": '{"path":"x"}'},
    }


def test_image_part_shape():
    assert base.image_part("https://x/y.png") == {
        "type": "image_url",
        "image_url": {"url": "https://x/y.png"},
    }
    assert base.image_part("https://x/y.png", "high")["image_url"]["detail"] == "high"


def test_is_nameless_tool_name_matches_only_blank():
    assert base.is_nameless_tool_name("") is True
    assert base.is_nameless_tool_name("   ") is True
    assert base.is_nameless_tool_name(None) is True
    assert base.is_nameless_tool_name("read_file") is False


def test_llm_response_text_property_and_defaults():
    r = base.LLMResponse()
    assert r.text == ""
    assert r.finish_reason == "stop"
    assert r.tool_calls == []
    r = base.LLMResponse(content="hello", finish_reason="tool_calls")
    assert r.text == "hello"


def test_assistant_msg_shapes():
    assert base.assistant_msg("hi") == {"role": "assistant", "content": "hi"}
    tc = [base.tool_call("i", "n", "a")]
    m = base.assistant_msg(tool_calls=tc)
    assert m["role"] == "assistant"
    assert m["tool_calls"] == tc
    assert "content" not in m  # 无 content 时不带空 content 键


def test_system_and_user_and_tool_result_msg_shapes():
    assert base.system_msg("s") == {"role": "system", "content": "s"}
    assert base.user_msg("u") == {"role": "user", "content": "u"}
    assert base.tool_result_msg("id-1", "body") == {
        "role": "tool",
        "tool_call_id": "id-1",
        "content": "body",
    }
