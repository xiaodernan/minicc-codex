"""M8-T764 — ``minicc/tools/schemas.py`` 的协议形状钉住。

这个模块是"工具调用/结果线缆形状"的一个家，零同名测试（模块→测试映射发现）。
确定性契约钉成回归：

1. 状态词汇 + 派生集（FAILED/UNSUCCESSFUL——M8-T376 的推导，防止
   `failed` 这类幽灵成员渗入）；
2. ``tagged()`` 的 ``[CODE] message`` 形状；
3. ``ToolCall.from_openai`` 的名字修剪 + 参数容错（坏 JSON → dict + parse_error）；
4. ``tool_call_name`` / ``normalized_tool_calls`` 只洗名前后空白；
5. ``_clip_raw`` / ``record_text`` 的天花板与截断计数句；
6. ``ToolResult.render()`` 的空结果、含头尾的形状。
"""

from __future__ import annotations

import json

import pytest

from minicc.tools import schemas as s


def test_status_vocabulary_order():
    assert s.TOOL_RESULT_STATUSES == ("ok", "error", "denied", "cancelled", "timed_out")


def test_failed_excludes_ok_and_cancelled():
    assert s.FAILED_TOOL_RESULT_STATUSES == frozenset({"error", "denied", "timed_out"})


def test_unsuccessful_excludes_only_ok():
    assert s.UNSUCCESSFUL_TOOL_RESULT_STATUSES == frozenset(
        {"error", "denied", "cancelled", "timed_out"}
    )


def test_tagged_shape():
    assert s.tagged(s.CODE_TOOL_ERROR, "boom") == "[TOOL_ERROR] boom"


def test_untrusted_tags_fresh_list_each_time():
    a = s.untrusted_tags("web")
    b = s.untrusted_tags("web")
    assert a == ["untrusted", "web"]
    assert a is not b


def test_tool_call_name_trims_wire_edges():
    assert s.tool_call_name({"function": {"name": " read_file "}}) == "read_file"
    assert s.tool_call_name({"name": "bash "}) == "bash"
    assert s.tool_call_name("not a dict") == ""


def test_from_openai_trims_and_parses_arguments():
    call = s.ToolCall.from_openai(
        {"function": {"name": " read_file ", "arguments": '{"path": "x"}'}, "id": "c1"}
    )
    assert call.tool == "read_file"
    assert call.arguments == {"path": "x"}
    assert call.parse_error is None
    assert call.call_id == "c1"


def test_from_openai_walks_past_bad_json_without_crashing():
    call = s.ToolCall.from_openai(
        {"function": {"name": "read_file", "arguments": "{not json"}, "id": "c2"}
    )
    assert call.tool == "read_file"
    assert call.arguments == {}
    assert call.parse_error


def test_from_openai_accepts_single_quoted_literal():
    call = s.ToolCall.from_openai(
        {"function": {"name": "bash", "arguments": "{'cmd': 'ls'}"}, "id": "c3"}
    )
    assert call.arguments == {"cmd": "ls"}
    assert call.parse_error is None


def test_normalized_tool_calls_only_trims_names():
    calls = [{"function": {"name": " read_file ", "arguments": "{}"}, "id": "x"}]
    (only,) = s.normalized_tool_calls(calls)
    assert only["function"]["name"] == "read_file"
    assert only["id"] == "x"


def test_clip_raw_stops_at_ceiling_and_counts_bytes():
    text = "x" * 500
    clipped = s._clip_raw(text, 120)
    assert len(clipped) == 120
    assert "500" in clipped  # total 字符数被写出来
    assert "430" in clipped  # dropped 字符数被写出来


def test_render_without_body_shows_status_as_fallback():
    r = s.ToolResult(status="cancelled")
    assert r.render() == "[cancelled]"


def test_render_head_tail_carries_truncation_marker():
    r = s.ToolResult(summary="sum", head="aaa", tail="zzz", truncated=True)
    out = r.render()
    assert "aaa" in out and "zzz" in out
    assert "2000" in out and "4000" in out


def test_record_text_short_output_passes_through():
    r = s.ToolResult(summary="sum", output="small")
    assert r.record_text(4000) == r.render()


def test_record_text_clips_and_admits_the_loss():
    r = s.ToolResult(summary="sum", output="y" * 500)
    stored = r.record_text(80)
    assert len(stored) == 80
    assert "504" in stored  # render() = "sum\n" + 500 y's = 504 字符，通知句写出 intact 总数
