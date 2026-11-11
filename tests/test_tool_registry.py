"""M8-T790: minicc/tools/registry.py - tool registry tests.

Tests for the tool registry module:
- ToolSpec dataclass
- ToolRegistry registration and lookup
- Risk levels and capability declarations
"""

from __future__ import annotations

import pytest

from minicc.tools.registry import (
    CAPABILITY_MIN_RISK,
    RISK_ORDER,
    ToolRegistry,
    ToolSpec,
)


# ============================================================================
# ToolSpec
# ============================================================================

def test_tool_spec_creation() -> None:
    spec = ToolSpec(
        name="test_tool",
        description="A test tool",
        risk="readonly",
        params=(),
        handler=lambda: None,
    )
    assert spec.name == "test_tool"
    assert spec.description == "A test tool"
    assert spec.risk == "readonly"
    assert spec.capabilities == ()


def test_tool_spec_capabilities() -> None:
    spec = ToolSpec(
        name="test_tool",
        description="A test tool",
        risk="write",
        params=(),
        handler=lambda: None,
        capabilities=["fs_write"],
    )
    assert spec.capabilities == ["fs_write"]


# ============================================================================
# ToolRegistry
# ============================================================================

def test_tool_registry_register_and_lookup() -> None:
    registry = ToolRegistry()
    spec = ToolSpec(
        name="test_tool",
        description="A test tool",
        risk="readonly",
        params=(),
        handler=lambda: None,
    )
    registry.register(spec)
    retrieved = registry.spec("test_tool")
    assert retrieved is not None
    assert retrieved.name == "test_tool"
    assert retrieved.description == "A test tool"


def test_tool_registry_duplicate_registration() -> None:
    registry = ToolRegistry()
    spec1 = ToolSpec(name="test_tool", description="first", risk="readonly", params=(), handler=lambda: None)
    spec2 = ToolSpec(name="test_tool", description="second", risk="readonly", params=(), handler=lambda: None)
    registry.register(spec1)
    with pytest.raises(ValueError):
        registry.register(spec2)


def test_tool_registry_lookup_nonexistent() -> None:
    registry = ToolRegistry()
    result = registry.spec("nonexistent")
    assert result is None


# ============================================================================
# RISK_ORDER
# ============================================================================

def test_risk_order() -> None:
    assert RISK_ORDER == {"readonly": 0, "write": 1, "exec": 2}


def test_capability_min_risk() -> None:
    assert CAPABILITY_MIN_RISK == {
        "fs_read": "readonly",
        "network": "readonly",
        "fs_write": "write",
        "shell": "exec",
    }
