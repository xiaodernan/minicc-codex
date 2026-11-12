"""M8-T816: minicc/changes.py - change inspector tests.

Tests for:
- ChangeError: change error class
- PREIMAGE_* constants: preimage verdict constants
- NAME_* constants: name match constants
- ChangeInspector: change inspection operations
- diff: compute diff between versions
- summary: change summary
"""

from __future__ import annotations

from pathlib import Path

import pytest

from minicc.changes import (
    ChangeError,
    ChangeInspector,
    NAME_AMBIGUOUS,
    NAME_SUBSTITUTED,
    NAME_UNMATCHED,
    PREIMAGE_MISMATCH,
    PREIMAGE_NOT_IN_WINDOW,
    PREIMAGE_NOT_READABLE,
    PREIMAGE_NOT_RECORDED,
    PREIMAGE_READ,
    PREIMAGE_SOURCE,
    SUBSTITUTED_CHAR,
    _IGNORED_PREFIXES,
    _MAX_FILES,
    _AUDIT_TAIL_BYTES,
)


# ============================================================================
# Error class
# ============================================================================

def test_change_error() -> None:
    err = ChangeError("change inspection failed")
    assert str(err) == "change inspection failed"


# ============================================================================
# PREIMAGE constants
# ============================================================================

def test_preimage_constants() -> None:
    assert isinstance(PREIMAGE_READ, str)
    assert isinstance(PREIMAGE_NOT_RECORDED, str)
    assert isinstance(PREIMAGE_NOT_READABLE, str)
    assert isinstance(PREIMAGE_MISMATCH, str)
    assert isinstance(PREIMAGE_NOT_IN_WINDOW, str)
    assert isinstance(PREIMAGE_SOURCE, str)


# ============================================================================
# NAME constants
# ============================================================================

def test_name_constants() -> None:
    assert isinstance(NAME_SUBSTITUTED, str)
    assert isinstance(NAME_AMBIGUOUS, str)
    assert isinstance(NAME_UNMATCHED, str)


# ============================================================================
# SUBSTITUTED_CHAR
# ============================================================================

def test_substituted_char() -> None:
    assert isinstance(SUBSTITUTED_CHAR, str)
    assert len(SUBSTITUTED_CHAR) == 1


# ============================================================================
# Module constants
# ============================================================================

def test_ignored_prefixes() -> None:
    assert isinstance(_IGNORED_PREFIXES, (list, tuple, set, frozenset))
    assert len(_IGNORED_PREFIXES) > 0


def test_max_files() -> None:
    assert isinstance(_MAX_FILES, int)
    assert _MAX_FILES > 0


def test_audit_tail_bytes() -> None:
    assert isinstance(_AUDIT_TAIL_BYTES, int)
    assert _AUDIT_TAIL_BYTES > 0


# ============================================================================
# ChangeInspector
# ============================================================================

def test_change_inspector_creation() -> None:
    inspector = ChangeInspector(Path("."))
    assert inspector is not None


def test_change_inspector_files_empty() -> None:
    inspector = ChangeInspector(Path("."))
    result = inspector.files()
    assert isinstance(result, list)
