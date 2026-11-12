"""M8-T831: minicc/snapshots.py - workspace snapshot tests.

Tests for pure helpers:
- WORKSPACE_SNAPSHOT_MANIFEST_VERSION: manifest version constant
- MAX_SNAPSHOT_*: snapshot limit constants
- _SAFE_TASK_ID: task id regex
- SnapshotError: error class
- snapshot_path_escapes_message: escape verdict message
- snapshot_dir: snapshot directory resolution
"""

from __future__ import annotations

from pathlib import Path

import pytest

from minicc.snapshots import (
    MAX_SNAPSHOT_FILE_BYTES,
    MAX_SNAPSHOT_FILES,
    MAX_SNAPSHOT_TOTAL_BYTES,
    WORKSPACE_SNAPSHOT_MANIFEST_VERSION,
    SnapshotError,
    _SAFE_TASK_ID,
    snapshot_dir,
    snapshot_path_escapes_message,
)


# ============================================================================
# Constants
# ============================================================================

def test_manifest_version() -> None:
    assert isinstance(WORKSPACE_SNAPSHOT_MANIFEST_VERSION, (int, str))


def test_snapshot_limits() -> None:
    assert isinstance(MAX_SNAPSHOT_FILES, int)
    assert MAX_SNAPSHOT_FILES > 0
    assert isinstance(MAX_SNAPSHOT_FILE_BYTES, int)
    assert MAX_SNAPSHOT_FILE_BYTES > 0
    assert isinstance(MAX_SNAPSHOT_TOTAL_BYTES, int)
    assert MAX_SNAPSHOT_TOTAL_BYTES >= MAX_SNAPSHOT_FILE_BYTES


# ============================================================================
# _SAFE_TASK_ID
# ============================================================================

def test_safe_task_id() -> None:
    assert _SAFE_TASK_ID.fullmatch("task-abc123") is not None
    assert _SAFE_TASK_ID.fullmatch("") is None


# ============================================================================
# SnapshotError
# ============================================================================

def test_snapshot_error() -> None:
    err = SnapshotError("snapshot failed")
    assert str(err) == "snapshot failed"


# ============================================================================
# snapshot_dir
# ============================================================================

def test_snapshot_dir() -> None:
    root = Path("/tmp/workspace")
    path = snapshot_dir(root, "abc123")
    assert path is not None


# ============================================================================
# snapshot_path_escapes_message
# ============================================================================

def test_snapshot_path_escapes_message() -> None:
    msg = snapshot_path_escapes_message("file.txt")
    assert isinstance(msg, str)
    assert "file.txt" in msg
