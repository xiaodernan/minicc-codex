"""M8-T785: minicc/env_files.py and minicc/internal_paths.py - leaf module contracts.

Tests for two small leaf modules that define one-home constants:
- env_files.ENV_FILENAME, ENV_FAMILY_PREFIX, is_env_filename()
- internal_paths.ALLOWLIST_NAME, AUDIT_NAME, HOOKS_FILENAME, PERMISSIONS_NAME,
  TOKEN_FILE_NAME, MCP_CONFIG_NAME
"""

from __future__ import annotations

import pytest

from minicc import env_files
from minicc import internal_paths


# ============================================================================
# env_files.ENV_FILENAME and ENV_FAMILY_PREFIX
# ============================================================================


def test_env_filename_constant() -> None:
    assert env_files.ENV_FILENAME == ".env"


def test_env_family_prefix_constant() -> None:
    assert env_files.ENV_FAMILY_PREFIX == ".env."


# ============================================================================
# env_files.is_env_filename
# ============================================================================

@pytest.mark.parametrize(
    ("name", "expected"),
    [
        (".env", True),
        (".env.local", True),
        (".env.production", True),
        (".env.example", True),
        (".envrc", False),
        ("env", False),
        ("foo.env", False),
        (".ENV", False),
        ("", False),
    ],
)
def test_is_env_filename(name: str, expected: bool) -> None:
    assert env_files.is_env_filename(name) is expected


# ============================================================================
# internal_paths constants
# ============================================================================

def test_internal_paths_constants() -> None:
    assert internal_paths.ALLOWLIST_NAME == "allowlist.json"
    assert internal_paths.AUDIT_NAME == "audit.jsonl"
    assert internal_paths.HOOKS_FILENAME == "hooks.json"
    assert internal_paths.PERMISSIONS_NAME == "permissions.json"
    assert internal_paths.TOKEN_FILE_NAME == "web_token.json"
    assert internal_paths.MCP_CONFIG_NAME == "mcp.json"


def test_internal_paths_all_strings() -> None:
    """All internal path constants are non-empty strings."""
    for name in (
        internal_paths.ALLOWLIST_NAME,
        internal_paths.AUDIT_NAME,
        internal_paths.HOOKS_FILENAME,
        internal_paths.PERMISSIONS_NAME,
        internal_paths.TOKEN_FILE_NAME,
        internal_paths.MCP_CONFIG_NAME,
    ):
        assert isinstance(name, str)
        assert len(name) > 0
        assert "/" not in name  # bare filenames, not paths
        assert "\\" not in name
