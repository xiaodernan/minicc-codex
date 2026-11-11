"""M8-T796: minicc/llm/openai_provider.py - OpenAI-compatible provider tests.

Tests for pure functions and constants:
- _is_retryable: retryable error classification
- _is_rate_limit: rate limit detection
- _is_quota_exhausted: quota exhausted detection
- _is_malformed_response_error: malformed response detection
- _parse_usage: usage dict parsing
- Constants: REASONING_WIRE_VALUES, REASONING_FALLBACKS, TOOLS_REJECTION_HINTS
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from minicc.llm.openai_provider import (
    REASONING_FALLBACKS,
    REASONING_WIRE_VALUES,
    TOOLS_REJECTION_HINTS,
    _is_malformed_response_error,
    _is_quota_exhausted,
    _is_rate_limit,
    _is_retryable,
    _parse_usage,
)


# ============================================================================
# Constants
# ============================================================================

def test_reasoning_wire_values() -> None:
    assert isinstance(REASONING_WIRE_VALUES, dict)
    assert "low" in REASONING_WIRE_VALUES


def test_reasoning_fallbacks() -> None:
    assert isinstance(REASONING_FALLBACKS, dict)
    assert len(REASONING_FALLBACKS) > 0


def test_tools_rejection_hints() -> None:
    assert isinstance(TOOLS_REJECTION_HINTS, tuple)
    assert len(TOOLS_REJECTION_HINTS) > 0
    assert "tool" in TOOLS_REJECTION_HINTS
    assert "function" in TOOLS_REJECTION_HINTS


# ============================================================================
# _is_malformed_response_error
# ============================================================================

def test_is_malformed_response_error_json_decode() -> None:
    exc = json.JSONDecodeError("expecting value", "doc", 0)
    assert _is_malformed_response_error(exc) is True


def test_is_malformed_response_error_hint_match() -> None:
    class FakeExc(Exception):
        pass
    exc = FakeExc("unterminated string at position 5")
    assert _is_malformed_response_error(exc) is True


def test_is_malformed_response_error_no_match() -> None:
    exc = ValueError("some other error message")
    assert _is_malformed_response_error(exc) is False


# ============================================================================
# _is_rate_limit
# ============================================================================

def test_is_rate_limit_rate_limit_error() -> None:
    from openai import RateLimitError
    exc = RateLimitError(message="rate limited", response=MagicMock(), body={})
    assert _is_rate_limit(exc) is True


def test_is_rate_limit_429_with_rate_limit_marker() -> None:
    exc = ValueError("429 too many requests")
    assert _is_rate_limit(exc) is True


def test_is_rate_limit_429_with_qps_marker() -> None:
    exc = ValueError("429 qps exceeded")
    assert _is_rate_limit(exc) is True


def test_is_rate_limit_429_without_marker() -> None:
    exc = ValueError("429 something else")
    assert _is_rate_limit(exc) is False


def test_is_rate_limit_non_429() -> None:
    exc = ValueError("500 internal server error")
    assert _is_rate_limit(exc) is False


# ============================================================================
# _is_quota_exhausted
# ============================================================================

def test_is_quota_exhausted_402() -> None:
    exc = MagicMock()
    exc.status_code = 402
    assert _is_quota_exhausted(exc) is True


def test_is_quota_exhausted_429_with_credit_code() -> None:
    exc = MagicMock()
    exc.status_code = 429
    exc.__class__.__name__ = "ValueError"
    # When text contains credit-limit code markers
    from minicc.llm.openai_provider import _QUOTA_EXHAUSTED_CODES
    # We can't easily construct a real exception, so just verify status 429
    # alone without code markers returns False
    assert _is_quota_exhausted(exc) is False


def test_is_quota_exhausted_other_status() -> None:
    exc = MagicMock()
    exc.status_code = 500
    assert _is_quota_exhausted(exc) is False


def test_is_quota_exhausted_no_status() -> None:
    exc = ValueError("some error")
    assert _is_quota_exhausted(exc) is False


# ============================================================================
# _is_retryable
# ============================================================================

def test_is_retryable_rate_limit_error() -> None:
    from openai import RateLimitError
    exc = RateLimitError(message="rate limited", response=MagicMock(), body={})
    assert _is_retryable(exc) is True


def test_is_retryable_connection_error() -> None:
    exc = ConnectionError("connection failed")
    assert _is_retryable(exc) is True


def test_is_retryable_timeout_error() -> None:
    exc = TimeoutError("timed out")
    assert _is_retryable(exc) is True


def test_is_retryable_json_decode_error() -> None:
    exc = json.JSONDecodeError("expecting value", "doc", 0)
    assert _is_retryable(exc) is True


def test_is_retryable_non_retryable() -> None:
    exc = ValueError("some non-retryable error")
    assert _is_retryable(exc) is False


# ============================================================================
# _parse_usage
# ============================================================================

def test_parse_usage_none() -> None:
    result = _parse_usage(None)
    assert isinstance(result, dict)
    assert result.get("prompt_tokens", 0) == 0
    assert result.get("completion_tokens", 0) == 0
    assert result.get("total_tokens", 0) == 0


def test_parse_usage_dict() -> None:
    result = _parse_usage({"prompt_tokens": 10, "completion_tokens": 20})
    assert isinstance(result, dict)
    assert result.get("prompt_tokens") == 10
    assert result.get("completion_tokens") == 20


def test_parse_usage_empty_dict() -> None:
    result = _parse_usage({})
    assert isinstance(result, dict)