"""M8-T797: minicc/tools/schemas.py - tool protocol contract tests.

Tests for pure functions and constants:
- Tool status codes: TOOL_STATUS_*, TOOL_RESULT_STATUSES, FAILED_TOOL_RESULT_STATUSES, UNSUCCESSFUL_TOOL_RESULT_STATUSES
- Error codes: CODE_* constants
- tool_call_name: tool name extraction
- normalized_tool_calls: tool call normalization
- ToolCall, ToolResult: data classes
- tagged: tool result tagging
- _clip_notice, _clip_raw: clipping utilities
"""

from __future__ import annotations

import pytest

from minicc.tools.schemas import (
    CODE_BUDGET,
    CODE_CANCELLED,
    CODE_DENIED,
    CODE_ERROR,
    CODE_HOOK_DENIED,
    CODE_INTERRUPTED_TOOL_RESULT,
    CODE_INVALID_ARGUMENTS,
    CODE_INVALID_TOOL_ARGUMENTS,
    CODE_RUNTIME_GUARD,
    CODE_RECOVERY_GUARD,
    CODE_SANDBOX_UNAVAILABLE,
    CODE_TIMED_OUT,
    CODE_TOOL_ERROR,
    CODE_UNKNOWN_SHELL,
    CODE_UNKNOWN_TOOL,
    FAILED_TOOL_RESULT_STATUSES,
    HEAD_CHARS,
    RECORD_CLIP_NOTICE,
    TAIL_CHARS,
    TOOL_RESULT_STATUSES,
    TOOL_STATUS_CANCELLED,
    TOOL_STATUS_DENIED,
    TOOL_STATUS_ERROR,
    TOOL_STATUS_OK,
    TOOL_STATUS_TIMED_OUT,
    TRUNCATION_MARKER,
    UNSUCCESSFUL_TOOL_RESULT_STATUSES,
    _clip_notice,
    _clip_raw,
    tagged,
    tool_call_name,
    normalized_tool_calls,
    ToolCall,
    ToolResult,
)


# ============================================================================
# Tool status constants
# ============================================================================

def test_tool_status_constants() -> None:
    assert TOOL_STATUS_OK == "ok"
    assert TOOL_STATUS_ERROR == "error"
    assert TOOL_STATUS_DENIED == "denied"
    assert TOOL_STATUS_CANCELLED == "cancelled"
    assert TOOL_STATUS_TIMED_OUT == "timed_out"


def test_tool_result_statuses() -> None:
    assert isinstance(TOOL_RESULT_STATUSES, tuple)
    assert TOOL_STATUS_OK in TOOL_RESULT_STATUSES
    assert TOOL_STATUS_ERROR in TOOL_RESULT_STATUSES


def test_failed_tool_result_statuses() -> None:
    assert isinstance(FAILED_TOOL_RESULT_STATUSES, frozenset)
    assert TOOL_STATUS_ERROR in FAILED_TOOL_RESULT_STATUSES
    assert TOOL_STATUS_DENIED in FAILED_TOOL_RESULT_STATUSES


def test_unsuccessful_tool_result_statuses() -> None:
    assert isinstance(UNSUCCESSFUL_TOOL_RESULT_STATUSES, frozenset)
    assert TOOL_STATUS_ERROR in UNSUCCESSFUL_TOOL_RESULT_STATUSES
    assert TOOL_STATUS_CANCELLED in UNSUCCESSFUL_TOOL_RESULT_STATUSES
    assert TOOL_STATUS_TIMED_OUT in UNSUCCESSFUL_TOOL_RESULT_STATUSES


# ============================================================================
# Error code constants
# ============================================================================

def test_error_code_constants() -> None:
    assert CODE_INVALID_TOOL_ARGUMENTS == "INVALID_TOOL_ARGUMENTS"
    assert CODE_TOOL_ERROR == "TOOL_ERROR"
    assert CODE_DENIED == "DENIED"
    assert CODE_CANCELLED == "CANCELLED"
    assert CODE_TIMED_OUT == "TIMED_OUT"
    assert CODE_BUDGET == "BUDGET"
    assert CODE_UNKNOWN_TOOL == "UNKNOWN_TOOL"


# ============================================================================
# ToolCall
# ============================================================================

def test_tool_call_defaults() -> None:
    call = ToolCall(tool="read_file", arguments={})
    assert call.tool == "read_file"
    assert call.arguments == {}


def test_tool_call_with_arguments() -> None:
    call = ToolCall(tool="write_file", arguments={"path": "test.txt", "content": "hello"})
    assert call.tool == "write_file"
    assert call.arguments == {"path": "test.txt", "content": "hello"}


def test_tool_call_from_openai() -> None:
    call = ToolCall.from_openai({
        "id": "call_1",
        "function": {"name": "read_file", "arguments": '{"path": "test.txt"}'},
    })
    assert call.tool == "read_file"
    assert call.arguments == {"path": "test.txt"}
    assert call.call_id == "call_1"


# ============================================================================
# ToolResult
# ============================================================================

def test_tool_result_defaults() -> None:
    result = ToolResult()
    assert result.status == "ok"
    assert result.output == ""
    assert result.summary == ""
    assert result.error is None if hasattr(result, 'error') else True


def test_tool_result_with_values() -> None:
    result = ToolResult(
        status="error",
        output="something went wrong",
        summary="failed",
    )
    assert result.status == "error"
    assert result.output == "something went wrong"
    assert result.summary == "failed"


# ============================================================================
# tool_call_name
# ============================================================================

def test_tool_call_name_simple() -> None:
    assert tool_call_name({"name": "read_file", "arguments": {}}) == "read_file"


def test_tool_call_name_function_format() -> None:
    assert tool_call_name({"function": {"name": "write_file"}}) == "write_file"


def test_tool_call_name_missing() -> None:
    assert tool_call_name({}) == ""
    assert tool_call_name({"name": ""}) == ""


# ============================================================================
# normalized_tool_calls
# ============================================================================

def test_normalized_tool_calls_empty() -> None:
    assert normalized_tool_calls([]) == []


def test_normalized_tool_calls_single() -> None:
    calls = [{"name": "read_file", "arguments": {"path": "test.txt"}}]
    result = normalized_tool_calls(calls)
    assert len(result) == 1


# ============================================================================
# tagged
# ============================================================================

def test_tagged_ok() -> None:
    result = tagged("OK", "read_file completed")
    assert result == "[OK] read_file completed"


def test_tagged_error() -> None:
    result = tagged("ERROR", "failed")
    assert result == "[ERROR] failed"


# ============================================================================
# _clip_notice and _clip_raw
# ============================================================================

def test_clip_raw_long() -> None:
    text = "x" * 1000
    result = _clip_raw(text, ceiling=100)
    assert len(result) <= 100
    assert len(result) <= len(text)


def test_clip_raw_exact_ceiling() -> None:
    text = "x" * 50
    result = _clip_raw(text, ceiling=50)
    assert len(result) <= 50


def test_clip_notice() -> None:
    result = _clip_notice(kept=500, dropped=500, total=1000)
    assert "500" in result


# ============================================================================
# Constants
# ============================================================================

def test_head_chars() -> None:
    assert isinstance(HEAD_CHARS, int)
    assert HEAD_CHARS > 0


def test_tail_chars() -> None:
    assert isinstance(TAIL_CHARS, int)
    assert TAIL_CHARS > 0


def test_truncation_marker() -> None:
    assert isinstance(TRUNCATION_MARKER, str)
    assert len(TRUNCATION_MARKER) > 0


def test_record_clip_notice() -> None:
    assert isinstance(RECORD_CLIP_NOTICE, str)
    assert len(RECORD_CLIP_NOTICE) > 0
