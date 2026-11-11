"""M8-T790: minicc/webserver.py - web server error code tests.

Tests for functions in webserver.py:
- error_code_for: maps exceptions to error codes
"""

from __future__ import annotations

import pytest

from minicc.webserver import (
    error_code_for,
    CODE_REQUEST_FAILED,
    CODE_INTERNAL_ERROR,
    CODE_NOT_FOUND,
    CODE_SESSION_ERROR,
    CODE_WORKTREE_ERROR,
    CODE_SNAPSHOT_ERROR,
    CODE_ALLOWLIST_ERROR,
    CODE_MCP_ERROR,
    CODE_CHANGE_ERROR,
    CODE_FORBIDDEN,
    CODE_UNAUTHORIZED,
    CODE_CROSS_ORIGIN_DENIED,
    CODE_TOO_MANY_EVENT_STREAMS,
)


def test_error_code_for_none() -> None:
    assert error_code_for(None) == CODE_REQUEST_FAILED


def test_error_code_for_file_not_found() -> None:
    assert error_code_for(FileNotFoundError("file not found")) == CODE_NOT_FOUND


def test_error_code_for_edit_error() -> None:
    from minicc.tools.editor import EditError
    result = error_code_for(EditError("test"))
    # EditError maps to CODE_INTERNAL_ERROR via MRO (no specific mapping)
    assert result == CODE_INTERNAL_ERROR


# ============================================================================
# Known error code constants exist
# ============================================================================

def test_error_code_constants() -> None:
    assert CODE_REQUEST_FAILED
    assert CODE_INTERNAL_ERROR
    assert CODE_NOT_FOUND
    assert CODE_SESSION_ERROR
    assert CODE_WORKTREE_ERROR
    assert CODE_SNAPSHOT_ERROR
    assert CODE_ALLOWLIST_ERROR
    assert CODE_MCP_ERROR
    assert CODE_CHANGE_ERROR
    assert CODE_FORBIDDEN
    assert CODE_UNAUTHORIZED
    assert CODE_CROSS_ORIGIN_DENIED
    assert CODE_TOO_MANY_EVENT_STREAMS
