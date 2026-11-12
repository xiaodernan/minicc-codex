"""M8-T805: minicc/atomic_file.py - atomic file operations with retry tests.

Tests for:
- DEFAULT_ATTEMPTS: default retry attempts
- DEFAULT_DELAY: default delay
- _wait: wait function
- replace_with_retry: atomic replace with retry
- read_text_with_retry: read text with retry
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from minicc.atomic_file import (
    DEFAULT_ATTEMPTS,
    DEFAULT_DELAY,
    _wait,
    read_text_with_retry,
    replace_with_retry,
)


# ============================================================================
# Constants
# ============================================================================

def test_default_attempts() -> None:
    assert isinstance(DEFAULT_ATTEMPTS, int)
    assert DEFAULT_ATTEMPTS > 0


def test_default_delay() -> None:
    assert isinstance(DEFAULT_DELAY, (int, float))
    assert DEFAULT_DELAY > 0


# ============================================================================
# _wait
# ============================================================================

def test_wait_with_float_delay() -> None:
    result = _wait(0.001, 0)
    assert isinstance(result, float)
    assert result == 0.001


def test_wait_with_callable_delay() -> None:
    def delay_fn(attempt: int) -> float:
        return 0.1 * (attempt + 1)
    result = _wait(delay_fn, 2)
    assert abs(result - 0.3) < 1e-9


# ============================================================================
# replace_with_retry
# ============================================================================

def test_replace_with_retry_simple() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Path(tmpdir) / "source.txt"
        dst = Path(tmpdir) / "dest.txt"
        src.write_text("hello world")
        replace_with_retry(src, dst)
        assert dst.read_text() == "hello world"


def test_replace_with_retry_overwrites() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Path(tmpdir) / "source.txt"
        dst = Path(tmpdir) / "dest.txt"
        src.write_text("new content")
        dst.write_text("old content")
        replace_with_retry(src, dst)
        assert dst.read_text() == "new content"


# ============================================================================
# read_text_with_retry
# ============================================================================

def test_read_text_with_retry() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        f = Path(tmpdir) / "test.txt"
        f.write_text("test content")
        result = read_text_with_retry(f)
        assert result == "test content"


def test_read_text_with_retry_missing() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        f = Path(tmpdir) / "missing.txt"
        with pytest.raises(FileNotFoundError):
            read_text_with_retry(f)
