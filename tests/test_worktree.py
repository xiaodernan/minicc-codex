"""M8-T825: minicc/worktree.py - worktree manager tests.

Tests for:
- _NAME: name regex pattern
- WorktreeError: error class
- WorktreeManager: creation, validation, list
- _validate_name: name validation
- _target_within_root: path containment check
"""

from __future__ import annotations

import pytest

from minicc.worktree import (
    WorktreeError,
    WorktreeManager,
    _NAME,
)
from pathlib import Path


# ============================================================================
# _NAME regex
# ============================================================================

def test_name_regex_valid() -> None:
    assert _NAME.fullmatch("feature-branch") is not None
    assert _NAME.fullmatch("fix_bug") is not None
    assert _NAME.fullmatch("v2.0") is not None
    assert _NAME.fullmatch("a") is not None


def test_name_regex_invalid() -> None:
    assert _NAME.fullmatch("../escape") is None
    assert _NAME.fullmatch("") is None
    assert _NAME.fullmatch(".hidden") is None
    assert _NAME.fullmatch("with space") is None
    assert _NAME.fullmatch("a" * 65) is None


# ============================================================================
# WorktreeError
# ============================================================================

def test_worktree_error() -> None:
    err = WorktreeError("worktree failed")
    assert str(err) == "worktree failed"


# ============================================================================
# WorktreeManager
# ============================================================================

def test_worktree_manager_creation(tmp_path: Path) -> None:
    manager = WorktreeManager(tmp_path)
    assert manager.workspace == tmp_path.resolve()
    assert manager.root is not None


def test_worktree_manager_validate_name_valid() -> None:
    manager = WorktreeManager(Path("."))
    assert manager._validate_name("feature-branch") == "feature-branch"


def test_worktree_manager_validate_name_invalid() -> None:
    manager = WorktreeManager(Path("."))
    with pytest.raises(WorktreeError):
        manager._validate_name("../escape")


def test_worktree_manager_target_within_root(tmp_path: Path) -> None:
    manager = WorktreeManager(tmp_path)
    target = manager._target_within_root("feature-branch")
    assert isinstance(target, Path)


def test_worktree_manager_target_within_root_escape(tmp_path: Path) -> None:
    manager = WorktreeManager(tmp_path)
    with pytest.raises(WorktreeError):
        manager._target_within_root("../escape")
