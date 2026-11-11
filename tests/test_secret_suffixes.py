"""M8-T793: minicc/secret_suffixes.py and minicc/shell_lexing.py tests.

Tests for one-home leaf modules:
- secret_suffixes.KEY_MATERIAL_SUFFIXES: key material file suffixes
- shell_lexing.QUOTE_CHARS: shell quote characters
"""

from __future__ import annotations

import pytest

from minicc.secret_suffixes import KEY_MATERIAL_SUFFIXES
from minicc.shell_lexing import QUOTE_CHARS


# ============================================================================
# KEY_MATERIAL_SUFFIXES
# ============================================================================

def test_key_material_suffixes_is_tuple() -> None:
    assert isinstance(KEY_MATERIAL_SUFFIXES, tuple)


def test_key_material_suffixes_content() -> None:
    assert KEY_MATERIAL_SUFFIXES == (".pem", ".key", ".p12", ".pfx", ".kdbx")


def test_key_material_suffixes_match_files() -> None:
    assert "cert.pem".endswith(KEY_MATERIAL_SUFFIXES)
    assert "key.pem".endswith(KEY_MATERIAL_SUFFIXES)
    assert "store.pfx".endswith(KEY_MATERIAL_SUFFIXES)
    assert "database.kdbx".endswith(KEY_MATERIAL_SUFFIXES)
    assert "script.py".endswith(KEY_MATERIAL_SUFFIXES) is False


# ============================================================================
# QUOTE_CHARS
# ============================================================================

def test_quote_chars_is_frozenset() -> None:
    assert isinstance(QUOTE_CHARS, frozenset)


def test_quote_chars_content() -> None:
    assert QUOTE_CHARS == frozenset({'"', "'"})
