"""M8-T784: minicc/secret_suffixes.py and minicc/shell_lexing.py - leaf module contracts.

Tests for two small leaf modules that define one-home constants:
- secret_suffixes.KEY_MATERIAL_SUFFIXES: tuple of key-material file suffixes
- shell_lexing.QUOTE_CHARS: frozenset of quote characters for shell tokenizer
"""

from __future__ import annotations

import pytest

from minicc import secret_suffixes
from minicc.shell_lexing import QUOTE_CHARS


# ============================================================================
# secret_suffixes.KEY_MATERIAL_SUFFIXES
# ============================================================================


def test_key_material_suffixes_is_tuple() -> None:
    """KEY_MATERIAL_SUFFIXES is a tuple, not a list or set."""
    assert isinstance(secret_suffixes.KEY_MATERIAL_SUFFIXES, tuple)


def test_key_material_suffixes_values() -> None:
    """The suffix tuple contains exactly the expected key-material extensions."""
    assert secret_suffixes.KEY_MATERIAL_SUFFIXES == (
        ".pem",
        ".key",
        ".p12",
        ".pfx",
        ".kdbx",
    )


def test_key_material_suffixes_endswith_works() -> None:
    """KEY_MATERIAL_SUFFIXES works with str.endswith (its intended use)."""
    assert "cert.pem".endswith(secret_suffixes.KEY_MATERIAL_SUFFIXES)
    assert "key.key".endswith(secret_suffixes.KEY_MATERIAL_SUFFIXES)
    assert "store.p12".endswith(secret_suffixes.KEY_MATERIAL_SUFFIXES)
    assert "vault.pfx".endswith(secret_suffixes.KEY_MATERIAL_SUFFIXES)
    assert "database.kdbx".endswith(secret_suffixes.KEY_MATERIAL_SUFFIXES)
    assert "readme.md".endswith(secret_suffixes.KEY_MATERIAL_SUFFIXES) is False
    assert "script.py".endswith(secret_suffixes.KEY_MATERIAL_SUFFIXES) is False


# ============================================================================
# shell_lexing.QUOTE_CHARS
# ============================================================================


def test_quote_chars_is_frozenset() -> None:
    """QUOTE_CHARS is a frozenset, not a set or list."""
    assert isinstance(QUOTE_CHARS, frozenset)


def test_quote_chars_values() -> None:
    """QUOTE_CHARS contains exactly the single and double quote characters."""
    assert QUOTE_CHARS == frozenset({'"', "'"})


def test_quote_chars_is_immutable() -> None:
    """QUOTE_CHARS cannot be mutated (frozenset property)."""
    with pytest.raises(AttributeError):
        QUOTE_CHARS.add('"')  # type: ignore[attr-defined]


def test_quote_chars_used_for_quoting() -> None:
    """QUOTE_CHARS correctly identifies quote characters."""
    assert '"' in QUOTE_CHARS
    assert "'" in QUOTE_CHARS
    assert '`' not in QUOTE_CHARS
    assert '\\' not in QUOTE_CHARS
