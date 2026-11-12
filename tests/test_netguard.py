"""M8-T807: minicc/netguard.py - network guard tests.

Tests for:
- ALLOWED_SCHEMES: allowed URL schemes
- SCHEME_PREFIXES: scheme prefix mappings
- REDIRECT_STATUSES: redirect HTTP status codes
- BlockedAddressError: error for blocked addresses
- parse_http_url: parse HTTP URLs
- redirect_limit_message: redirect limit message
"""

from __future__ import annotations

import pytest

from minicc.netguard import (
    ALLOWED_SCHEMES,
    BlockedAddressError,
    REDIRECT_STATUSES,
    SCHEME_PREFIXES,
    parse_http_url,
    redirect_limit_message,
)


# ============================================================================
# Constants
# ============================================================================

def test_allowed_schemes() -> None:
    assert isinstance(ALLOWED_SCHEMES, (list, tuple, set, frozenset))
    assert len(ALLOWED_SCHEMES) > 0
    assert "http" in ALLOWED_SCHEMES
    assert "https" in ALLOWED_SCHEMES


def test_scheme_prefixes() -> None:
    assert isinstance(SCHEME_PREFIXES, (list, tuple, set, frozenset))
    assert len(SCHEME_PREFIXES) > 0


def test_redirect_statuses() -> None:
    assert isinstance(REDIRECT_STATUSES, (list, tuple, set, frozenset))
    assert len(REDIRECT_STATUSES) > 0


# ============================================================================
# parse_http_url
# ============================================================================

def test_parse_http_url_simple() -> None:
    result = parse_http_url("https://example.com/path")
    assert result is not None


def test_parse_http_url_with_port() -> None:
    result = parse_http_url("https://example.com:8443/path")
    assert result is not None


def test_parse_http_url_invalid() -> None:
    with pytest.raises(Exception):
        parse_http_url("not-a-url")


# ============================================================================
# redirect_limit_message
# ============================================================================

def test_redirect_limit_message() -> None:
    result = redirect_limit_message(5)
    assert isinstance(result, str)
    assert len(result) > 0


# ============================================================================
# BlockedAddressError
# ============================================================================

def test_blocked_address_error() -> None:
    err = BlockedAddressError("blocked")
    assert str(err) == "blocked"
