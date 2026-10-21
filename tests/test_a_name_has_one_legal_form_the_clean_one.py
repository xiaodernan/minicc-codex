"""M8-T336 — 一个名字只有一种合法形态：干净的那种

M8-T335 定了「无名调用是噪音」这条规则，但"名字带杂音"还有两种写法没被管：

* ``ToolCall.from_openai`` 是线上短语变成**可派发名字**的唯一构造点，它原样
  收下名字：``" read_file "`` 带着边角空格一路走到注册表查找，而注册表是精确
  匹配 → ``[TOOL_ERROR] 未知工具 'read_file '`` → 模型为一个毫无歧义的意图
  付了一轮；
* ``parse_envelope`` 已经拒绝"没有 action"（空的 action 会被 ``or`` 链塌成
  "没有 action"），却**没拒绝空白 action**（``"  "`` 照样通过，造出一个名叫
  ``"  "`` 的合成调用）→ 同样一轮白买。

本门钉住：名字在两个站点上都被收拾干净；空白 action 与空 action 一样被当作
"没有 action"（可修复的信封错误），而不是一次工具派发。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from minicc.llm.envelope import EnvelopeParseError, parse_envelope
from minicc.tools import build_registry
from minicc.tools.editor import Editor
from minicc.tools.schemas import ToolCall


def test_from_openai_trims_the_stray_spaces() -> None:
    call = ToolCall.from_openai({
        "id": "c1",
        "type": "function",
        "function": {"name": " read_file ", "arguments": "{}"},
    })
    assert call.tool == "read_file", call.tool


def test_the_trimmed_name_really_dispatches(tmp_path: Path) -> None:
    """The observable site: the registry runs the tool instead of refusing it."""
    (tmp_path / "note.txt").write_text("hello", encoding="utf-8")
    registry = build_registry(Editor(tmp_path))
    call = ToolCall.from_openai({
        "id": "c1",
        "type": "function",
        "function": {"name": " read_file ", "arguments": '{"path": "note.txt"}'},
    })
    result = registry.execute(call)
    assert result.status == "ok", result.summary
    assert "hello" in (result.output or "") + (result.head or ""), result


def test_a_clean_name_is_left_alone() -> None:
    call = ToolCall.from_openai({
        "id": "c1",
        "type": "function",
        "function": {"name": "read_file", "arguments": "{}"},
    })
    assert call.tool == "read_file", call.tool


def test_a_blank_envelope_action_is_no_action_at_all() -> None:
    """Same verdict as the empty action: a repairable envelope error."""
    with pytest.raises(EnvelopeParseError) as caught:
        parse_envelope('{"action": "  ", "params": {}}')
    assert "action" in str(caught.value)


def test_the_empty_envelope_action_still_raises() -> None:
    with pytest.raises(EnvelopeParseError):
        parse_envelope('{"action": "", "params": {}}')


def test_an_envelope_action_with_stray_spaces_leaves_clean() -> None:
    call = parse_envelope('{"action": " read_file ", "params": {"path": "a.py"}}')
    assert call is not None
    assert call["function"]["name"] == "read_file", call["function"]
    assert ToolCall.from_openai(call).tool == "read_file"
