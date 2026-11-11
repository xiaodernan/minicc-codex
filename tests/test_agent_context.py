"""M8-T787: minicc/agent/context.py - context assembly tests.

Tests for the context module functions:
- tool_round_walk: walks messages for tool protocol validation
- pending_tool_calls: gets pending tool calls from last round
- validate_tool_protocol: validates tool protocol before network I/O
- repair_interrupted_tool_rounds: repairs interrupted tool rounds
- message_chars: character count of message history
- estimate_tokens: estimates token count
- normalize_vision_context: normalizes vision context parts
- has_visual_content: checks for visual content in messages
- tool_protocol_error: constructs protocol error messages
"""

from __future__ import annotations

import pytest

from minicc.agent.context import (
    estimate_tokens,
    has_visual_content,
    message_chars,
    normalize_vision_context,
    pending_tool_calls,
    repair_interrupted_tool_rounds,
    tool_protocol_error,
    tool_round_walk,
    validate_tool_protocol,
)


# ============================================================================
# tool_round_walk
# ============================================================================

def test_tool_round_walk_empty() -> None:
    assert list(tool_round_walk([])) == []


def test_tool_round_walk_non_dict_message() -> None:
    result = list(tool_round_walk(["just a string"]))
    assert len(result) == 1
    assert result[0][0] == 0
    assert result[0][1] == "just a string"
    assert result[0][2] == set()
    assert result[0][3] == set()


def test_tool_round_walk_tool_call_and_result() -> None:
    messages = [
        {"role": "assistant", "tool_calls": [{"id": "call_1", "function": {"name": "read_file", "arguments": '{"path": "a.txt"}'}}]},
        {"role": "tool", "tool_call_id": "call_1", "content": "file content"},
    ]
    results = list(tool_round_walk(messages))
    assert len(results) == 2
    assert results[0][0] == 0
    assert results[0][1] == messages[0]
    assert results[0][2] == set()
    assert results[0][3] == {"call_1"}
    assert results[1][0] == 1
    assert results[1][1] == messages[1]
    assert results[1][2] == {"call_1"}
    assert results[1][3] == set()


def test_tool_round_walk_multiple_calls() -> None:
    messages = [
        {
            "role": "assistant",
            "tool_calls": [
                {"id": "call_1", "function": {"name": "read_file", "arguments": '{"path": "a.txt"}'}},
                {"id": "call_2", "function": {"name": "write_file", "arguments": '{"path": "b.txt"}'}},
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "content a"},
        {"role": "tool", "tool_call_id": "call_2", "content": "content b"},
    ]
    results = list(tool_round_walk(messages))
    assert len(results) == 3
    assert results[0][3] == {"call_1", "call_2"}
    assert results[1][2] == {"call_1", "call_2"}
    assert results[1][3] == {"call_2"}
    assert results[2][2] == {"call_2"}
    assert results[2][3] == set()


# ============================================================================
# pending_tool_calls
# ============================================================================

def test_pending_tool_calls_empty() -> None:
    assert pending_tool_calls([]) == set()


def test_pending_tool_calls_single_round() -> None:
    messages = [
        {"role": "assistant", "tool_calls": [{"id": "call_1", "function": {"name": "read_file", "arguments": "{}"}}]},
    ]
    assert pending_tool_calls(messages) == {"call_1"}


def test_pending_tool_calls_complete_round() -> None:
    messages = [
        {"role": "assistant", "tool_calls": [{"id": "call_1", "function": {"name": "read_file", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "call_1", "content": "done"},
    ]
    assert pending_tool_calls(messages) == set()


# ============================================================================
# tool_protocol_error
# ============================================================================

def test_tool_protocol_error_format() -> None:
    err = tool_protocol_error("test error", 0)
    assert "test error" in err


# ============================================================================
# validate_tool_protocol
# ============================================================================

def test_validate_tool_protocol_valid() -> None:
    messages = [
        {"role": "assistant", "tool_calls": [{"id": "call_1", "function": {"name": "read_file", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "call_1", "content": "content"},
    ]
    validate_tool_protocol(messages)


def test_validate_tool_protocol_empty() -> None:
    assert validate_tool_protocol([]) is None


def test_validate_tool_protocol_orphaned_result() -> None:
    messages = [
        {"role": "tool", "tool_call_id": "orphan_call", "content": "no one asked"},
    ]
    with pytest.raises(ValueError):
        validate_tool_protocol(messages)


def test_validate_tool_protocol_pending_not_resolved() -> None:
    messages = [
        {"role": "assistant", "tool_calls": [{"id": "call_1", "function": {"name": "read_file", "arguments": "{}"}}]},
    ]
    with pytest.raises(ValueError):
        validate_tool_protocol(messages)


# ============================================================================
# repair_interrupted_tool_rounds
# ============================================================================

def test_repair_interrupted_tool_rounds_empty() -> None:
    messages = []
    result = repair_interrupted_tool_rounds(messages)
    assert result == 0
    assert messages == []


def test_repair_interrupted_tool_rounds_complete() -> None:
    messages = [
        {"role": "assistant", "tool_calls": [{"id": "call_1", "function": {"name": "read_file", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "call_1", "content": "done"},
    ]
    result = repair_interrupted_tool_rounds(messages)
    assert result == 0


def test_repair_interrupted_tool_rounds_interrupted() -> None:
    messages = [
        {"role": "assistant", "tool_calls": [{"id": "call_1", "function": {"name": "read_file", "arguments": "{}"}}]},
        {"role": "assistant", "tool_calls": [{"id": "call_2", "function": {"name": "write_file", "arguments": "{}"}}]},
    ]
    result = repair_interrupted_tool_rounds(messages)
    assert result == 2
    assert len(messages) == 4
    # After repair: assistant(call_1), tool(call_1), assistant(call_2), tool(call_2)
    assert messages[0]["role"] == "assistant"
    assert messages[0]["tool_calls"][0]["id"] == "call_1"
    assert messages[1]["role"] == "tool"
    assert messages[1]["tool_call_id"] == "call_1"
    assert messages[2]["role"] == "assistant"
    assert messages[2]["tool_calls"][0]["id"] == "call_2"
    assert messages[3]["role"] == "tool"
    assert messages[3]["tool_call_id"] == "call_2"


# ============================================================================
# message_chars
# ============================================================================

def test_message_chars_empty() -> None:
    assert message_chars([]) == 0


def test_message_chars_simple() -> None:
    messages = [{"role": "user", "content": "hello world"}]
    assert message_chars(messages) == len("hello world")


def test_message_chars_multiple() -> None:
    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "world"},
    ]
    assert message_chars(messages) == len("hello") + len("world")


# ============================================================================
# estimate_tokens
# ============================================================================

def test_estimate_tokens_empty() -> None:
    assert estimate_tokens([]) == 0


def test_estimate_tokens_simple() -> None:
    messages = [{"role": "user", "content": "hello world"}]
    assert estimate_tokens(messages) == 3


# ============================================================================
# has_visual_content
# ============================================================================

def test_has_visual_content_empty() -> None:
    assert has_visual_content([]) is False


def test_has_visual_content_text_only() -> None:
    messages = [{"role": "user", "content": "hello"}]
    assert has_visual_content(messages) is False


def test_has_visual_content_with_image() -> None:
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "look at this"},
                {"type": "image_url", "image_url": {"url": "http://example.com/img.jpg"}},
            ],
        }
    ]
    assert has_visual_content(messages) is True


# ============================================================================
# normalize_vision_context
# ============================================================================

def test_normalize_vision_context_empty() -> None:
    assert normalize_vision_context(None) == []
    assert normalize_vision_context([]) == []


def test_normalize_vision_context_single() -> None:
    result = normalize_vision_context([{"type": "image_url", "image_url": {"url": "http://img.jpg", "detail": "high"}}])
    assert len(result) == 1
    assert result[0]["type"] == "image_url"
    assert result[0]["image_url"]["url"] == "http://img.jpg"
