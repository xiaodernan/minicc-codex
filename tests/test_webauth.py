"""M8-T820: minicc/webauth.py - web authentication tests.

Tests for:
- ENV_TOKEN, TOKEN_BYTES, LOOPBACK_HOSTS, LOOPBACK_SUFFIXES constants
- is_loopback_host: loopback host detection
- generate_token: token generation
- token_store_path: token store path
- load_or_create_token: load or create token
- WebAuth: authentication check
- WebAuthError: error class
"""

from __future__ import annotations

import os
from pathlib import Path
import tempfile

import pytest

from minicc.webauth import (
    ENV_TOKEN,
    LOOPBACK_HOSTS,
    LOOPBACK_SUFFIXES,
    TOKEN_BYTES,
    TOKEN_FILE_NAME,
    WebAuth,
    WebAuthError,
    generate_token,
    is_loopback_host,
    load_or_create_token,
    token_store_path,
)


# ============================================================================
# Constants
# ============================================================================

def test_env_token() -> None:
    assert isinstance(ENV_TOKEN, str)
    assert ENV_TOKEN == "MINICC_WEB_TOKEN"


def test_token_bytes() -> None:
    assert isinstance(TOKEN_BYTES, int)
    assert TOKEN_BYTES >= 16


def test_token_file_name() -> None:
    assert TOKEN_FILE_NAME == "web_token.json"


def test_loopback_hosts() -> None:
    assert isinstance(LOOPBACK_HOSTS, (list, tuple, set, frozenset))
    assert "127.0.0.1" in LOOPBACK_HOSTS
    assert "localhost" in LOOPBACK_HOSTS
    assert "::1" in LOOPBACK_HOSTS


def test_loopback_suffixes() -> None:
    assert isinstance(LOOPBACK_SUFFIXES, (list, tuple, set, frozenset))
    assert len(LOOPBACK_SUFFIXES) > 0


# ============================================================================
# is_loopback_host
# ============================================================================

def test_is_loopback_host_127_0_0_1() -> None:
    assert is_loopback_host("127.0.0.1") is True


def test_is_loopback_host_localhost() -> None:
    assert is_loopback_host("localhost") is True


def test_is_loopback_host_ipv6() -> None:
    assert is_loopback_host("::1") is True


def test_is_loopback_host_public() -> None:
    assert is_loopback_host("example.com") is False
    assert is_loopback_host("8.8.8.8") is False


# ============================================================================
# generate_token
# ============================================================================

def test_generate_token() -> None:
    token = generate_token()
    assert isinstance(token, str)
    assert len(token) > 0


def test_generate_token_unique() -> None:
    tokens = [generate_token() for _ in range(10)]
    assert len(set(tokens)) == 10


# ============================================================================
# token_store_path
# ============================================================================

def test_token_store_path(tmp_path: Path) -> None:
    path = token_store_path(tmp_path)
    assert isinstance(path, Path)
    assert path.name == TOKEN_FILE_NAME


# ============================================================================
# WebAuth
# ============================================================================

def test_web_auth_creation() -> None:
    auth = WebAuth("test-token", required=True)
    assert auth is not None


def test_web_auth_check_valid() -> None:
    auth = WebAuth("test-token", required=True)
    assert auth.check("test-token") is True


def test_web_auth_check_invalid() -> None:
    auth = WebAuth("test-token", required=True)
    assert auth.check("wrong-token") is False


def test_web_auth_check_none() -> None:
    auth = WebAuth("test-token", required=True)
    assert auth.check(None) is False


# ============================================================================
# load_or_create_token
# ============================================================================

def test_load_or_create_token_creates(tmp_path: Path) -> None:
    token, created = load_or_create_token(tmp_path)
    assert isinstance(token, str)
    assert len(token) > 0
    assert created is True


def test_load_or_create_token_reads_existing(tmp_path: Path) -> None:
    store = tmp_path / ".minicc" / TOKEN_FILE_NAME
    store.parent.mkdir(parents=True)
    store.write_text('{"token": "existing-test-token"}', encoding="utf-8")
    token, created = load_or_create_token(tmp_path)
    assert token == "existing-test-token"
    assert created is False
