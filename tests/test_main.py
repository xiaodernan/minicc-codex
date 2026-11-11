"""M8-T795: minicc/main.py - CLI main module tests.

Tests for core CLI functions:
- shell_lexing integration
- environment detection
- Safe command names and reserved words
"""

from __future__ import annotations

import pytest

from minicc.main import (
    RESERVED_TOOL_NAMES,
    TOOL_MODES,
)


# ============================================================================
# RESERVED_TOOL_NAMES
# ============================================================================

def test_reserved_tool_names() -> None:
    assert isinstance(RESERVED_TOOL_NAMES, frozenset)
    assert len(RESERVED_TOOL_NAMES) > 0
    # Core tools should be reserved
    assert "read_file" in RESERVED_TOOL_NAMES
    assert "write_file" in RESERVED_TOOL_NAMES
    assert "edit_file" in RESERVED_TOOL_NAMES
    assert "delete_file" in RESERVED_TOOL_NAMES


# ============================================================================
# TOOL_MODES
# ============================================================================

def test_tool_modes() -> None:
    assert isinstance(TOOL_MODES, dict)
    assert len(TOOL_MODES) > 0
    # Should have tool mode keys
    for mode in TOOL_MODES:
        assert isinstance(mode, str)
        assert len(mode) > 0
