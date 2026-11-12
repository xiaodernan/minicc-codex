"""M8-T815: minicc/webserver.py - web server tests.

Tests for:
- Error code constants: CODE_*
- Server constants: TASK_STREAM_TIMEOUT, MAX_SSE_CONNECTIONS, etc.
- error_code_for: error code lookup
"""

from __future__ import annotations

import pytest

from minicc.webserver import (
    CODE_ALLOWLIST_ERROR,
    CODE_CHANGE_ERROR,
    CODE_CROSS_ORIGIN_DENIED,
    CODE_FORBIDDEN,
    CODE_INTERNAL_ERROR,
    CODE_INVALID_REQUEST,
    CODE_MCP_ERROR,
    CODE_NOT_FOUND,
    CODE_REQUEST_FAILED,
    CODE_SESSION_ERROR,
    CODE_SNAPSHOT_ERROR,
    CODE_TASK_NOT_FOUND,
    CODE_TOO_MANY_EVENT_STREAMS,
    CODE_UNAUTHORIZED,
    MAX_BODY_BYTES,
    MAX_SSE_CONNECTIONS,
    SSE_WRITE_TIMEOUT,
    TASKS_API_PREFIX,
    TASK_STREAM_TIMEOUT,
    error_code_for,
)


# ============================================================================
# Error code constants
# ============================================================================

def test_error_codes() -> None:
    assert CODE_TASK_NOT_FOUND == "task_not_found"
    assert CODE_NOT_FOUND == "not_found"
    assert CODE_INVALID_REQUEST == "invalid_request"
    assert CODE_SESSION_ERROR == "session_error"
    assert CODE_SNAPSHOT_ERROR == "snapshot_error"
    assert CODE_ALLOWLIST_ERROR == "allowlist_error"
    assert CODE_MCP_ERROR == "mcp_error"
    assert CODE_CHANGE_ERROR == "change_error"
    assert CODE_FORBIDDEN == "forbidden"
    assert CODE_UNAUTHORIZED == "unauthorized"
    assert CODE_CROSS_ORIGIN_DENIED == "cross_origin_denied"
    assert CODE_TOO_MANY_EVENT_STREAMS == "too_many_event_streams"
    assert CODE_REQUEST_FAILED == "request_failed"
    assert CODE_INTERNAL_ERROR == "internal_error"


# ============================================================================
# Server constants
# ============================================================================

def test_task_stream_timeout() -> None:
    assert isinstance(TASK_STREAM_TIMEOUT, int)
    assert TASK_STREAM_TIMEOUT > 0


def test_max_sse_connections() -> None:
    assert isinstance(MAX_SSE_CONNECTIONS, int)
    assert MAX_SSE_CONNECTIONS > 0


def test_sse_write_timeout() -> None:
    assert isinstance(SSE_WRITE_TIMEOUT, (int, float))
    assert SSE_WRITE_TIMEOUT > 0


def test_max_body_bytes() -> None:
    assert isinstance(MAX_BODY_BYTES, int)
    assert MAX_BODY_BYTES > 0


def test_tasks_api_prefix() -> None:
    assert isinstance(TASKS_API_PREFIX, str)
    assert TASKS_API_PREFIX == "/api/tasks/"


# ============================================================================
# error_code_for
# ============================================================================

def test_error_code_for_none() -> None:
    assert error_code_for(None) == CODE_REQUEST_FAILED


def test_error_code_for_unknown_exception() -> None:
    assert error_code_for(RuntimeError("test")) == CODE_INTERNAL_ERROR
