"""M8-T794: minicc/internal_paths.py tests.

Tests for internal path constants.
"""

from __future__ import annotations

import pytest

from minicc.internal_paths import (
    ALLOWLIST_NAME,
    AUDIT_NAME,
    HOOKS_FILENAME,
    MCP_CONFIG_NAME,
    PERMISSIONS_NAME,
    TOKEN_FILE_NAME,
)


def test_internal_paths_constants() -> None:
    assert ALLOWLIST_NAME == "allowlist.json"
    assert AUDIT_NAME == "audit.jsonl"
    assert HOOKS_FILENAME == "hooks.json"
    assert PERMISSIONS_NAME == "permissions.json"
    assert TOKEN_FILE_NAME == "web_token.json"
    assert MCP_CONFIG_NAME == "mcp.json"


def test_internal_paths_are_strings() -> None:
    for name in [
        ALLOWLIST_NAME,
        AUDIT_NAME,
        HOOKS_FILENAME,
        PERMISSIONS_NAME,
        TOKEN_FILE_NAME,
        MCP_CONFIG_NAME,
    ]:
        assert isinstance(name, str)
        assert len(name) > 0
