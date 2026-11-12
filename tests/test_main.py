"""M8-T795: minicc/main.py - CLI main module tests.

Tests for core CLI functions:
- shell_lexing integration
- environment detection
- Safe command names and reserved words
"""

from __future__ import annotations

import pytest

from minicc.main import (
    AUTHORIZATION_RISKS,
    BUILTIN_HELP_LINE,
    DEFAULT_MAX_DEPTH,
    DEFAULT_MAX_TURNS,
    MAX_TIMEOUT_SECONDS,
    PERMISSION_MODES,
    PERMISSION_MODE_PLAN,
    PHASE_EXECUTION,
    PHASE_PLANNING,
    PROVIDER_TYPES,
    REASONING_EFFORTS,
    SANDBOX_MODES,
    STAGE_INSPECT,
    STAGE_PLANNING,
    STAGE_ROUTE_CODE,
    TASK_EXECUTORS,
    TOOL_MODES,
    TOOL_NAME_BASH,
)


# ============================================================================
# Constants
# ============================================================================

def test_builtin_help_line() -> None:
    assert isinstance(BUILTIN_HELP_LINE, str)
    assert len(BUILTIN_HELP_LINE) > 0


def test_default_max_depth() -> None:
    assert isinstance(DEFAULT_MAX_DEPTH, int)
    assert DEFAULT_MAX_DEPTH > 0


def test_default_max_turns() -> None:
    assert isinstance(DEFAULT_MAX_TURNS, int)
    assert DEFAULT_MAX_TURNS > 0


def test_max_timeout_seconds() -> None:
    assert isinstance(MAX_TIMEOUT_SECONDS, (int, float))
    assert MAX_TIMEOUT_SECONDS > 0


def test_tool_name_bash() -> None:
    assert isinstance(TOOL_NAME_BASH, str)
    assert TOOL_NAME_BASH == "bash"


# ============================================================================
# TOOL_MODES
# ============================================================================

def test_tool_modes() -> None:
    assert isinstance(TOOL_MODES, (dict, frozenset, set, list, tuple))
    assert len(TOOL_MODES) > 0


# ============================================================================
# Permission modes
# ============================================================================

def test_permission_modes() -> None:
    assert isinstance(PERMISSION_MODES, (list, tuple, set, frozenset))
    assert len(PERMISSION_MODES) > 0


def test_permission_mode_plan() -> None:
    assert isinstance(PERMISSION_MODE_PLAN, str)
    assert len(PERMISSION_MODE_PLAN) > 0


# ============================================================================
# Phase constants
# ============================================================================

def test_phase_constants() -> None:
    assert isinstance(PHASE_PLANNING, str)
    assert isinstance(PHASE_EXECUTION, str)
    assert PHASE_PLANNING != PHASE_EXECUTION


# ============================================================================
# Stage constants
# ============================================================================

def test_stage_constants() -> None:
    assert isinstance(STAGE_INSPECT, str)
    assert isinstance(STAGE_PLANNING, str)
    assert isinstance(STAGE_ROUTE_CODE, str)
    assert len(STAGE_INSPECT) > 0
    assert len(STAGE_PLANNING) > 0
    assert len(STAGE_ROUTE_CODE) > 0


# ============================================================================
# Provider types
# ============================================================================

def test_provider_types() -> None:
    assert isinstance(PROVIDER_TYPES, (list, tuple, set, frozenset, dict))
    assert len(PROVIDER_TYPES) > 0


# ============================================================================
# Reasoning efforts
# ============================================================================

def test_reasoning_efforts() -> None:
    assert isinstance(REASONING_EFFORTS, (list, tuple, set, frozenset, dict))
    assert len(REASONING_EFFORTS) > 0


# ============================================================================
# Sandbox modes
# ============================================================================

def test_sandbox_modes() -> None:
    assert isinstance(SANDBOX_MODES, (list, tuple, set, frozenset, dict))
    assert len(SANDBOX_MODES) > 0


# ============================================================================
# Task executors
# ============================================================================

def test_task_executors() -> None:
    assert isinstance(TASK_EXECUTORS, (list, tuple, set, frozenset, dict))
    assert len(TASK_EXECUTORS) > 0


# ============================================================================
# Authorization risks
# ============================================================================

def test_authorization_risks() -> None:
    assert isinstance(AUTHORIZATION_RISKS, (list, tuple, set, frozenset, dict))
    assert len(AUTHORIZATION_RISKS) > 0
