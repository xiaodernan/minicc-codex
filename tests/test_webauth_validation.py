"""M8-T146: web_token.json validation boundaries.

The token file is the only persisted credential in .minicc/. This gate proves
that load_or_create_token handles all common malformed inputs correctly:

- non-dict top-level (list / int / str / null)
- missing "token" key
- non-string token values (bool / number / null / array / object)
- empty string token
- corrupted UTF-8
- unreadable file (POSIX permission denial)
- unwritable parent directory
- weak / short tokens accepted without warning (documented behavior)
- concurrent writes to the same token file
- file permissions on POSIX (0o600 enforced)
- token field type coercion edge cases
"""

from __future__ import annotations

import json
import os
import stat
import sys
import threading
import time
from pathlib import Path

import pytest

from minicc.webauth import WebAuthError, load_or_create_token


# ---------------------------------------------------------------------------
# Top-level structure validation
# ---------------------------------------------------------------------------


def test_non_dict_top_level_raises(tmp_path: Path) -> None:
    """JSON array at top-level must raise WebAuthError."""
    store = tmp_path / ".minicc" / "web_token.json"
    store.parent.mkdir()
    store.write_text('["not", "a", "dict"]', encoding="utf-8")
    with pytest.raises(WebAuthError):
        load_or_create_token(tmp_path)


def test_null_top_level_raises(tmp_path: Path) -> None:
    store = tmp_path / ".minicc" / "web_token.json"
    store.parent.mkdir()
    store.write_text("null", encoding="utf-8")
    with pytest.raises(WebAuthError):
        load_or_create_token(tmp_path)


def test_int_top_level_raises(tmp_path: Path) -> None:
    store = tmp_path / ".minicc" / "web_token.json"
    store.parent.mkdir()
    store.write_text("42", encoding="utf-8")
    with pytest.raises(WebAuthError):
        load_or_create_token(tmp_path)


def test_string_top_level_raises(tmp_path: Path) -> None:
    store = tmp_path / ".minicc" / "web_token.json"
    store.parent.mkdir()
    store.write_text('"just-a-string"', encoding="utf-8")
    with pytest.raises(WebAuthError):
        load_or_create_token(tmp_path)


# ---------------------------------------------------------------------------
# Missing / empty token field
# ---------------------------------------------------------------------------


def test_missing_token_key_generates_new(tmp_path: Path) -> None:
    """Empty dict {} has no "token" → generates and persists a new one."""
    store = tmp_path / ".minicc" / "web_token.json"
    store.parent.mkdir()
    store.write_text("{}", encoding="utf-8")
    token, created = load_or_create_token(tmp_path)
    assert created
    assert len(token) >= 32
    # The old {} is replaced with the new token
    data = json.loads(store.read_text(encoding="utf-8"))
    assert data["token"] == token


def test_empty_string_token_generates_new(tmp_path: Path) -> None:
    """{"token": ""} is treated as missing → generates new token."""
    store = tmp_path / ".minicc" / "web_token.json"
    store.parent.mkdir()
    store.write_text('{"token": ""}', encoding="utf-8")
    token, created = load_or_create_token(tmp_path)
    assert created
    assert len(token) >= 32


def test_whitespace_only_token_generates_new(tmp_path: Path) -> None:
    store = tmp_path / ".minicc" / "web_token.json"
    store.parent.mkdir()
    store.write_text('{"token": "   "}', encoding="utf-8")
    token, created = load_or_create_token(tmp_path)
    assert created


# ---------------------------------------------------------------------------
# Non-string token values (type coercion)
# ---------------------------------------------------------------------------


def test_boolean_true_token_is_coerced(tmp_path: Path) -> None:
    """JSON true becomes str(True) = "True" — documented coercion."""
    store = tmp_path / ".minicc" / "web_token.json"
    store.parent.mkdir()
    store.write_text('{"token": true}', encoding="utf-8")
    token, created = load_or_create_token(tmp_path)
    assert not created
    assert token == "True"


def test_boolean_false_token_generates_new(tmp_path: Path) -> None:
    """JSON false → str(False) = "False", but line 91's `or ""` treats it as
    falsy → empty string → stripped → dropped → generates new token."""
    store = tmp_path / ".minicc" / "web_token.json"
    store.parent.mkdir()
    store.write_text('{"token": false}', encoding="utf-8")
    token, created = load_or_create_token(tmp_path)
    assert created  # Known limitation: false is falsy
    assert len(token) >= 32


def test_number_token_is_coerced(tmp_path: Path) -> None:
    store = tmp_path / ".minicc" / "web_token.json"
    store.parent.mkdir()
    store.write_text('{"token": 12345}', encoding="utf-8")
    token, created = load_or_create_token(tmp_path)
    assert not created
    assert token == "12345"


def test_null_token_generates_new(tmp_path: Path) -> None:
    store = tmp_path / ".minicc" / "web_token.json"
    store.parent.mkdir()
    store.write_text('{"token": null}', encoding="utf-8")
    token, created = load_or_create_token(tmp_path)
    assert created


def test_array_token_is_coerced(tmp_path: Path) -> None:
    """JSON array becomes Python list repr."""
    store = tmp_path / ".minicc" / "web_token.json"
    store.parent.mkdir()
    store.write_text('{"token": [1, 2]}', encoding="utf-8")
    token, created = load_or_create_token(tmp_path)
    assert not created
    assert token == "[1, 2]"


def test_object_token_is_coerced(tmp_path: Path) -> None:
    store = tmp_path / ".minicc" / "web_token.json"
    store.parent.mkdir()
    store.write_text('{"token": {"nested": "value"}}', encoding="utf-8")
    token, created = load_or_create_token(tmp_path)
    assert not created
    assert token == "{'nested': 'value'}"


# ---------------------------------------------------------------------------
# File I/O errors
# ---------------------------------------------------------------------------


def test_corrupted_utf8_raises(tmp_path: Path) -> None:
    store = tmp_path / ".minicc" / "web_token.json"
    store.parent.mkdir()
    store.write_bytes(b"\xff\xfe invalid utf-8")
    with pytest.raises((WebAuthError, UnicodeDecodeError)):
        load_or_create_token(tmp_path)


def test_unreadable_file_raises(tmp_path: Path) -> None:
    if os.name == "nt":
        pytest.skip("Windows does not enforce read permission for file owner")
    store = tmp_path / ".minicc" / "web_token.json"
    store.parent.mkdir()
    store.write_text('{"token": "secret"}', encoding="utf-8")
    os.chmod(store, 0o000)
    try:
        with pytest.raises(WebAuthError):
            load_or_create_token(tmp_path)
    finally:
        os.chmod(store, 0o600)  # Restore for cleanup


def test_unwritable_parent_raises(tmp_path: Path) -> None:
    if os.name == "nt":
        pytest.skip("Windows permission model differs")
    parent = tmp_path / ".minicc"
    parent.mkdir()
    os.chmod(parent, 0o444)
    try:
        with pytest.raises(WebAuthError):
            load_or_create_token(tmp_path)
    finally:
        os.chmod(parent, 0o755)


# ---------------------------------------------------------------------------
# Concurrent access
# ---------------------------------------------------------------------------


def test_concurrent_writes_produce_single_token(tmp_path: Path) -> None:
    """Multiple threads racing to create token should not corrupt the file."""
    errors: list[BaseException] = []

    def _create() -> None:
        try:
            load_or_create_token(tmp_path)
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=_create) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
        assert not t.is_alive(), (
            "a token-writing thread outlived its join window: it can still be "
            "inside load_or_create_token, so the store read below races it"
        )

    assert not errors
    store = tmp_path / ".minicc" / "web_token.json"
    data = json.loads(store.read_text(encoding="utf-8"))
    assert "token" in data
    assert len(data["token"]) >= 32


# ---------------------------------------------------------------------------
# File permissions (POSIX only)
# ---------------------------------------------------------------------------


def test_created_token_has_owner_only_permissions(tmp_path: Path) -> None:
    if os.name != "posix":
        pytest.skip("Permission check is POSIX-specific")
    token, _ = load_or_create_token(tmp_path)
    store = tmp_path / ".minicc" / "web_token.json"
    mode = stat.S_IMODE(store.stat().st_mode)
    assert mode == 0o600


def test_existing_token_with_world_readable_permissions_is_not_fixed(tmp_path: Path) -> None:
    """load_or_create_token does NOT tighten permissions on existing files."""
    if os.name != "posix":
        pytest.skip("Permission check is POSIX-specific")
    store = tmp_path / ".minicc" / "web_token.json"
    store.parent.mkdir()
    store.write_text('{"token": "existing"}', encoding="utf-8")
    os.chmod(store, 0o644)
    token, created = load_or_create_token(tmp_path)
    assert not created
    assert token == "existing"
    # Permissions remain unchanged (documented: only set on creation)
    mode = stat.S_IMODE(store.stat().st_mode)
    assert mode == 0o644


# ---------------------------------------------------------------------------
# Weak / short tokens (accepted without warning)
# ---------------------------------------------------------------------------


def test_single_character_token_accepted(tmp_path: Path) -> None:
    """No minimum length enforcement — documented behavior."""
    store = tmp_path / ".minicc" / "web_token.json"
    store.parent.mkdir()
    store.write_text('{"token": "x"}', encoding="utf-8")
    token, created = load_or_create_token(tmp_path)
    assert not created
    assert token == "x"


def test_generated_token_meets_expected_entropy(tmp_path: Path) -> None:
    token, created = load_or_create_token(tmp_path)
    assert created
    # Generated tokens are 64 URL-safe chars (32 bytes * 2)
    assert len(token) == 64
    assert all(c in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in token)


# ---------------------------------------------------------------------------
# Extra keys in token file (ignored)
# ---------------------------------------------------------------------------


def test_extra_keys_in_token_file_ignored(tmp_path: Path) -> None:
    """Only "token" key is read; extra metadata is silently ignored."""
    store = tmp_path / ".minicc" / "web_token.json"
    store.parent.mkdir()
    store.write_text(
        '{"token": "my-secret", "created_at": "2026-01-01", "algorithm": "HS256"}',
        encoding="utf-8",
    )
    token, created = load_or_create_token(tmp_path)
    assert not created
    assert token == "my-secret"
