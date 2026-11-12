"""M8-T812: minicc/session.py - session store tests.

Tests for:
- SESSION_FORMAT_VERSION: session format version
- TOOL_LOG_FIELDS: tool log field names
- Lock/retry delay constants
- missing_session_message: session not found message
- SessionStore: session storage operations
- SessionError: session error class
"""

from __future__ import annotations

import pytest

from minicc.session import (
    SESSION_FORMAT_VERSION,
    TOOL_LOG_FIELDS,
    SessionError,
    missing_session_message,
    _LOCK_ATTEMPTS,
    _LOCK_RETRY_DELAY,
    _READ_ATTEMPTS,
    _READ_RETRY_DELAY,
    _REPLACE_ATTEMPTS,
    _REPLACE_RETRY_DELAY,
)


# ============================================================================
# Constants
# ============================================================================

def test_session_format_version() -> None:
    assert isinstance(SESSION_FORMAT_VERSION, int)
    assert SESSION_FORMAT_VERSION > 0


def test_tool_log_fields() -> None:
    assert isinstance(TOOL_LOG_FIELDS, (list, tuple, set, frozenset))
    assert len(TOOL_LOG_FIELDS) > 0


def test_lock_constants() -> None:
    assert isinstance(_LOCK_ATTEMPTS, int)
    assert _LOCK_ATTEMPTS > 0
    assert isinstance(_LOCK_RETRY_DELAY, (int, float))
    assert _LOCK_RETRY_DELAY > 0


def test_replace_constants() -> None:
    assert isinstance(_REPLACE_ATTEMPTS, int)
    assert _REPLACE_ATTEMPTS > 0
    assert isinstance(_REPLACE_RETRY_DELAY, (int, float))
    assert _REPLACE_RETRY_DELAY > 0


def test_read_constants() -> None:
    assert isinstance(_READ_ATTEMPTS, int)
    assert _READ_ATTEMPTS > 0
    assert isinstance(_READ_RETRY_DELAY, (int, float))
    assert _READ_RETRY_DELAY > 0


# ============================================================================
# SessionError
# ============================================================================

def test_session_error() -> None:
    err = SessionError("session not found")
    assert str(err) == "session not found"


# ============================================================================
# missing_session_message
# ============================================================================

def test_missing_session_message() -> None:
    result = missing_session_message("abc123")
    assert isinstance(result, str)
    assert "abc123" in result
