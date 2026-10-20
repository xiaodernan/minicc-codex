"""M8-T273: a handled failure must not be reported as an unhandled crash.

Two tools validated their input and rejected it on purpose, but the
exception they raised was not a ``ToolError`` - so the registry's catch-all
caught it and answered "工具 'read_file' 未处理异常: UnicodeDecodeError" /
"工具 'todo_write' 未处理异常: TodoError".

To the model that reads as "the tool crashed", and it says nothing about
what was actually wrong: the file is in another encoding, the checklist is
malformed.  Both are answers the model can act on.

The door runs the calls through the *registry*, because that is where the
two branches diverge - the catch-all returns a result too, so the difference
is in the message the model sees.

This door pins:

* a non-UTF-8 file is reported as an encoding problem, not a crash;
* a malformed checklist is reported as a bad payload, not a crash;
* the controls: a UTF-8 file and a valid checklist still work.
"""

from __future__ import annotations

import json
from pathlib import Path

from minicc.tools import build_registry
from minicc.tools.editor import Editor
from minicc.tools.registry import ToolCall, ToolError
from minicc.tools.todo import TodoError

CRASH_MARKER = "未处理异常"


def _call(tool: str, arguments: dict[str, object]) -> ToolCall:
    return ToolCall(tool=tool, arguments=dict(arguments), call_id="call-0")


def test_a_non_utf8_file_is_reported_as_an_encoding_problem(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "gbk.py").write_bytes("# 中文注释\nprint('hi')\n".encode("gbk"))
    registry = build_registry(Editor(workspace))
    result = registry.execute(_call("read_file", {"path": "gbk.py"}))
    assert result.status == "error"
    message = result.render()
    assert CRASH_MARKER not in message, f"a handled failure was reported as a crash: {message!r}"
    assert "UTF-8" in message, f"the encoding was not named: {message!r}"


def test_a_malformed_checklist_is_reported_as_a_bad_payload(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    registry = build_registry(Editor(workspace))
    result = registry.execute(
        _call("todo_write", {"todos": [{"content": "", "status": "pending"}]})
    )
    assert result.status == "error"
    message = result.render()
    assert CRASH_MARKER not in message, f"a handled failure was reported as a crash: {message!r}"


def test_the_todo_error_is_a_tool_error() -> None:
    """The shape itself: the registry routes by exception type."""
    assert issubclass(TodoError, ToolError)


def test_a_utf8_file_still_reads(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "ok.py").write_text("print('hi')\n", encoding="utf-8")
    registry = build_registry(Editor(workspace))
    result = registry.execute(_call("read_file", {"path": "ok.py"}))
    assert result.status == "ok"
    assert "print" in result.render()


def test_a_valid_checklist_still_works(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    registry = build_registry(Editor(workspace))
    result = registry.execute(
        _call("todo_write", {"todos": [{"content": "第一步", "status": "pending"}]})
    )
    assert result.status == "ok"
