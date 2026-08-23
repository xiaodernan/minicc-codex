"""Context window management — deterministic compaction when the conversation grows.

Adapted from specproof craft/context.py. When total message characters exceed
the threshold, older messages are summarised into a single system note so the
tool-result detail that the model has already acted on does not waste tokens.

The compaction is transparent to the agent loop: compact() returns the new
message list and the caller just replaces it.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any

# The compaction message itself has a known prefix so it can be detected
# and excluded from future compaction passes.
COMPACTION_MARKER = "[CONTEXT COMPACTED]"


def _msg_chars(messages: list[dict[str, Any]]) -> int:
    total = 0
    for m in messages:
        for key in ("content", "tool_calls", "name", "tool_call_id"):
            val = m.get(key)
            if isinstance(val, str):
                total += len(val)
            elif isinstance(val, list):
                total += len(str(val))
    return total


def message_chars(messages: list[dict[str, Any]]) -> int:
    """Return the approximate wire size used by the compaction guard."""
    return _msg_chars(messages)


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """Estimate tokens for gateways that omit usage in streamed responses."""
    chars = _msg_chars(messages)
    return math.ceil(chars / 4) if chars else 0


def _hash_messages(messages: list[dict[str, Any]]) -> str:
    raw = str([(m.get("role"), m.get("content", "")[:80]) for m in messages])
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def compact(
    messages: list[dict[str, Any]],
    *,
    threshold: int = 300_000,
    keep_recent: int = 6,
) -> list[dict[str, Any]]:
    """If *messages* exceeds *threshold* characters, summarise older turns.

    Strategy:
    1. Keep all system messages (they are typically short and essential).
    2. Keep the most recent *keep_recent* messages untouched.
    3. Replace everything in between with a single user message summarising
       the turn count, tool calls made, and final assistant answer.
    4. The summary is never re-compacted (COMPACTION_MARKER guard).

    Returns a (possibly shorter) new list; never mutates the input.
    """
    if _msg_chars(messages) <= threshold:
        return messages

    # Separate system prefix, compactable middle, and recent tail.
    system_msgs: list[dict[str, Any]] = []
    non_system: list[dict[str, Any]] = []
    for m in messages:
        if m.get("role") == "system":
            system_msgs.append(m)
        else:
            non_system.append(m)

    if len(non_system) <= keep_recent:
        return messages

    middle = non_system[: -keep_recent]
    tail = non_system[-keep_recent:]

    # Scan the middle for tool calls and assistant answers to build a summary.
    tool_names: list[str] = []
    turns = 0
    last_answer = ""
    for m in middle:
        role = m.get("role", "")
        if role == "assistant":
            turns += 1
            content = m.get("content") or ""
            if isinstance(content, str) and content and not content.startswith("{"):
                last_answer = content[:200]
            elif isinstance(content, list):
                text_parts = [
                    str(part.get("text") or "")
                    for part in content
                    if isinstance(part, dict) and part.get("type") == "text"
                ]
                if text_parts:
                    last_answer = " ".join(text_parts)[:200]
            for tc in m.get("tool_calls") or []:
                fn = tc.get("function") or {}
                tool_names.append(fn.get("name", "?"))

    # Deduplicate and count tool names.
    from collections import Counter
    tool_summary = ", ".join(
        f"{name}({count}x)"
        for name, count in Counter(tool_names).most_common(10)
    )

    tool_label = tool_summary or "无"
    summary_text = (
        f"{COMPACTION_MARKER} 之前的 {len(middle)} 条消息已压缩 (约 {_msg_chars(middle)} 字符)。"
        f"包含 {turns} 轮对话, 工具调用: {tool_label}。"
        f"最后回复摘要: {last_answer!r}"
    )

    return [
        *system_msgs,
        {"role": "user", "content": summary_text},
        *tail,
    ]
