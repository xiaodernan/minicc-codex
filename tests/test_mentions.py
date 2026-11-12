"""M8-T809: minicc/mentions.py - mention extraction and context tests.

Tests for:
- MENTION_STATUS_*: mention status constants
- MENTION_STATUSES: status set
- MENTION_TOKEN_RE: mention token regex
- MENTION_MAX_*: limit constants
- extract_mention_tokens: extract mention tokens from text
- build_mention_context: build mention context
- credential_injection_refusal: credential refusal
- deny_rule_injection_refusal: deny rule refusal
"""

from __future__ import annotations

from pathlib import Path

import pytest

from minicc.mentions import (
    MENTION_MAX_CHARS_PER_FILE,
    MENTION_MAX_FILES,
    MENTION_MAX_TOTAL_CHARS,
    MENTION_READ_BYTES,
    MENTION_STATUS_INJECTED,
    MENTION_STATUS_OMITTED,
    MENTION_STATUS_REJECTED,
    MENTION_STATUSES,
    MENTION_TOKEN_RE,
    build_mention_context,
    credential_injection_refusal,
    deny_rule_injection_refusal,
    extract_mention_tokens,
)


# ============================================================================
# Status constants
# ============================================================================

def test_mention_status_constants() -> None:
    assert isinstance(MENTION_STATUS_INJECTED, str)
    assert isinstance(MENTION_STATUS_REJECTED, str)
    assert isinstance(MENTION_STATUS_OMITTED, str)


def test_mention_statuses() -> None:
    assert isinstance(MENTION_STATUSES, (list, tuple, set, frozenset))
    assert MENTION_STATUS_INJECTED in MENTION_STATUSES
    assert MENTION_STATUS_REJECTED in MENTION_STATUSES
    assert MENTION_STATUS_OMITTED in MENTION_STATUSES


# ============================================================================
# Limits
# ============================================================================

def test_mention_limits() -> None:
    assert isinstance(MENTION_MAX_FILES, int)
    assert MENTION_MAX_FILES > 0
    assert isinstance(MENTION_MAX_CHARS_PER_FILE, int)
    assert MENTION_MAX_CHARS_PER_FILE > 0
    assert isinstance(MENTION_MAX_TOTAL_CHARS, int)
    assert MENTION_MAX_TOTAL_CHARS > 0
    assert isinstance(MENTION_READ_BYTES, int)
    assert MENTION_READ_BYTES > 0


# ============================================================================
# MENTION_TOKEN_RE
# ============================================================================

def test_mention_token_re() -> None:
    assert MENTION_TOKEN_RE is not None


# ============================================================================
# extract_mention_tokens
# ============================================================================

def test_extract_mention_tokens_simple() -> None:
    result = extract_mention_tokens("@file:test.txt")
    assert isinstance(result, list)


def test_extract_mention_tokens_none() -> None:
    result = extract_mention_tokens("no mentions here")
    assert result == []


def test_extract_mention_tokens_empty() -> None:
    result = extract_mention_tokens("")
    assert result == []


# ============================================================================
# credential_injection_refusal
# ============================================================================

def test_credential_injection_refusal() -> None:
    result = credential_injection_refusal()
    assert isinstance(result, str)
    assert len(result) > 0


# ============================================================================
# deny_rule_injection_refusal
# ============================================================================

def test_deny_rule_injection_refusal() -> None:
    result = deny_rule_injection_refusal()
    assert isinstance(result, str)
    assert len(result) > 0


# ============================================================================
# build_mention_context
# ============================================================================

def test_build_mention_context_empty() -> None:
    result = build_mention_context("", Path("."))
    assert result is not None
