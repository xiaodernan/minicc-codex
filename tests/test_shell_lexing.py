"""M8-T793: minicc/shell_lexing.py - shell lexing constants tests.

Tests for shell lexing quote characters.
"""

from __future__ import annotations

import pytest

from minicc.shell_lexing import QUOTE_CHARS


def test_quote_chars_is_frozenset() -> None:
    assert isinstance(QUOTE_CHARS, frozenset)


def test_quote_chars_content() -> None:
    assert QUOTE_CHARS == frozenset({'"', "'"})
