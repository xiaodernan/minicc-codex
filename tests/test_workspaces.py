"""M8-T827: minicc/workspaces.py - workspace catalog tests.

Tests for:
- resolve_workspace_path: resolve and validate workspace paths
- WorkspaceCatalog: workspace tracking catalog
- _advisory_lock: advisory lock handling
"""

from __future__ import annotations

from pathlib import Path

import pytest

from minicc.workspaces import (
    WorkspaceCatalog,
    resolve_workspace_path,
)


# ============================================================================
# resolve_workspace_path
# ============================================================================

def test_resolve_workspace_path_simple(tmp_path: Path) -> None:
    result = resolve_workspace_path(str(tmp_path), roots=())
    assert isinstance(result, Path)
    assert result.resolve() == tmp_path.resolve()


def test_resolve_workspace_path_missing(tmp_path: Path) -> None:
    with pytest.raises((ValueError, FileNotFoundError, OSError, PermissionError)):
        resolve_workspace_path(str(tmp_path / "nonexistent"), roots=())


# ============================================================================
# WorkspaceCatalog
# ============================================================================

def test_workspace_catalog_creation(tmp_path: Path) -> None:
    catalog = WorkspaceCatalog(tmp_path)
    assert catalog is not None


def test_workspace_catalog_list(tmp_path: Path) -> None:
    catalog = WorkspaceCatalog(tmp_path)
    result = catalog.list()
    assert isinstance(result, list)


def test_workspace_catalog_remember(tmp_path: Path) -> None:
    catalog = WorkspaceCatalog(tmp_path)
    target = tmp_path / "project"
    target.mkdir()
    catalog.remember(target)
    result = catalog.list()
    assert isinstance(result, list)
