"""M8-T801: minicc/llm/envelope.py - JSON Action Envelope parsing tests.

Tests for:
- ENVELOPE_BLOCK: envelope block marker
- MAX_REPAIR_CONTENT_CHARS: max repair content chars
- _next_envelope_id: envelope ID generation
- _render_envelope_action: action rendering
- envelope_system_suffix: system suffix generation
- extract_json_object: JSON object extraction
- parse_envelope: envelope parsing
"""

from __future__ import annotations

import pytest

from minicc.llm.envelope import (
    ENVELOPE_BLOCK,
    MAX_REPAIR_CONTENT_CHARS,
    EnvelopeParseError,
    extract_json_object,
    parse_envelope,
    envelope_system_suffix,
    _next_envelope_id,
    _render_envelope_action,
)


# ============================================================================
# Constants
# ============================================================================

def test_envelope_block() -> None:
    assert isinstance(ENVELOPE_BLOCK, str)
    assert len(ENVELOPE_BLOCK) > 0


def test_max_repair_content_chars() -> None:
    assert isinstance(MAX_REPAIR_CONTENT_CHARS, int)
    assert MAX_REPAIR_CONTENT_CHARS > 0


# ============================================================================
# _next_envelope_id
# ============================================================================

def test_next_envelope_id_increments() -> None:
    id1 = _next_envelope_id()
    id2 = _next_envelope_id()
    assert id1 != id2


# ============================================================================
# envelope_system_suffix
# ============================================================================

def test_envelope_system_suffix() -> None:
    suffix = envelope_system_suffix('[{"name": "read_file"}]')
    assert isinstance(suffix, str)
    assert len(suffix) > 0
    assert "read_file" in suffix


# ============================================================================
# _render_envelope_action
# ============================================================================

def test_render_envelope_action() -> None:
    result = _render_envelope_action({"function": {"name": "read_file", "arguments": '{"path": "test.txt"}'}})
    assert isinstance(result, str)
    assert "read_file" in result


# ============================================================================
# extract_json_object
# ============================================================================

def test_extract_json_object_simple() -> None:
    result = extract_json_object('{"key": "value"}')
    assert result == {"key": "value"}


def test_extract_json_object_with_text() -> None:
    result = extract_json_object('some text {"key": "value"} more text')
    assert result == {"key": "value"}


def test_extract_json_object_none() -> None:
    result = extract_json_object("no json here")
    assert result is None


# ============================================================================
# parse_envelope
# ============================================================================

def test_parse_envelope_valid() -> None:
    envelope = '{"action": "read_file", "params": {"path": "test.txt"}}'
    result = parse_envelope(envelope)
    assert result is not None


def test_parse_envelope_no_json() -> None:
    result = parse_envelope("not valid json at all")
    assert result is None


def test_parse_envelope_malformed() -> None:
    with pytest.raises(EnvelopeParseError):
        parse_envelope('{"action": "read_file", "params": {broken}')
