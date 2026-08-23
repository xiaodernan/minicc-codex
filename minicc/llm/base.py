"""LLM message/response types — messages are plain OpenAI wire-format dicts.

Kept as dataclasses with light helpers (adapted from specproof providers/base.py):
the agent loop, the session log and the provider all share these shapes, and
nothing outside the provider ever imports the openai SDK.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMResponse:
    """One complete assistant turn (stream chunks already aggregated)."""

    content: str | None = None
    # OpenAI wire format: [{"id": ..., "type": "function",
    #                       "function": {"name": ..., "arguments": "<json str>"}}]
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    finish_reason: str = "stop"
    model: str = ""
    reasoning_content: str | None = None

    @property
    def text(self) -> str:
        return self.content or ""


def user_msg(content: str | list[dict[str, Any]]) -> dict[str, Any]:
    return {"role": "user", "content": content}


def system_msg(content: str) -> dict[str, Any]:
    return {"role": "system", "content": content}


def assistant_msg(
    content: str | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    msg: dict[str, Any] = {"role": "assistant"}
    if content is not None:
        msg["content"] = content
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return msg


def tool_result_msg(tool_call_id: str, content: str) -> dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": content,
    }
