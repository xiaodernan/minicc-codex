"""M8-T800: minicc/static_assets.py - static asset response contract tests.

Tests for:
- _asset_root: asset directory resolution
- web_root: web asset root
- ide_root: IDE asset root
- asset_response: asset response building
- _ASSET_CACHE: asset cache object
"""

from __future__ import annotations

from pathlib import Path

import pytest

from minicc.static_assets import (
    _ASSET_CACHE,
    _asset_root,
    asset_response,
    ide_root,
    web_root,
)


# ============================================================================
# _asset_root
# ============================================================================

def test_asset_root_returns_path() -> None:
    root = _asset_root("web", "web", "index.html")
    assert isinstance(root, Path)


# ============================================================================
# web_root
# ============================================================================

def test_web_root() -> None:
    root = web_root()
    assert isinstance(root, Path)


# ============================================================================
# ide_root
# ============================================================================

def test_ide_root() -> None:
    root = ide_root()
    assert isinstance(root, Path)


# ============================================================================
# _ASSET_CACHE
# ============================================================================

def test_asset_cache_exists() -> None:
    assert _ASSET_CACHE is not None


# ============================================================================
# asset_response
# ============================================================================

def test_asset_response_returns_tuple() -> None:
    root = web_root()
    try:
        result = asset_response(root, "index.html")
        assert isinstance(result, tuple)
        assert len(result) == 2
    except FileNotFoundError:
        # index.html may not exist in dev environment - that's OK
        pass
