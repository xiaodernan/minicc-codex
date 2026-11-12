"""M8-T810: minicc/impact.py - change impact analysis tests.

Tests for:
- _JS_SUFFIXES: JavaScript file suffixes
- _SUFFIXES: file suffixes
- _SKIP_DIRS: directories to skip
- _MAX_*: limit constants
- _is_test: check if path is a test file
- analyze_change_impact: analyze change impact
"""

from __future__ import annotations

from pathlib import Path

import pytest

from minicc.impact import (
    _JS_SUFFIXES,
    _MAX_CACHE,
    _MAX_ENTRIES,
    _MAX_FILE_BYTES,
    _MAX_IMPORTS,
    _MAX_TOTAL_BYTES,
    _MAX_WARNINGS,
    _SKIP_DIRS,
    _SUFFIXES,
    _is_test,
    analyze_change_impact,
)


# ============================================================================
# Constants
# ============================================================================

def test_js_suffixes() -> None:
    assert isinstance(_JS_SUFFIXES, (list, tuple, set, frozenset))
    assert len(_JS_SUFFIXES) > 0


def test_suffixes() -> None:
    assert isinstance(_SUFFIXES, (list, tuple, set, frozenset))
    assert len(_SUFFIXES) > 0


def test_skip_dirs() -> None:
    assert isinstance(_SKIP_DIRS, (list, tuple, set, frozenset))
    assert len(_SKIP_DIRS) > 0


def test_max_constants() -> None:
    assert isinstance(_MAX_FILE_BYTES, int)
    assert _MAX_FILE_BYTES > 0
    assert isinstance(_MAX_TOTAL_BYTES, int)
    assert _MAX_TOTAL_BYTES > 0
    assert isinstance(_MAX_ENTRIES, int)
    assert _MAX_ENTRIES > 0
    assert isinstance(_MAX_CACHE, int)
    assert _MAX_CACHE > 0
    assert isinstance(_MAX_WARNINGS, int)
    assert _MAX_WARNINGS > 0
    assert isinstance(_MAX_IMPORTS, int)
    assert _MAX_IMPORTS > 0


# ============================================================================
# _is_test
# ============================================================================

def test_is_test_true() -> None:
    assert _is_test(Path("tests/test_foo.py")) is True
    assert _is_test(Path("test_bar.py")) is True


def test_is_test_false() -> None:
    assert _is_test(Path("src/main.py")) is False
    assert _is_test(Path("minicc/core.py")) is False


# ============================================================================
# analyze_change_impact
# ============================================================================

def test_analyze_change_impact_empty() -> None:
    result = analyze_change_impact(Path("."), [])
    assert result is not None


def test_analyze_change_impact_no_changes() -> None:
    result = analyze_change_impact(Path("."), [])
    assert result is not None
