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


#: finish_reason values that may end a turn normally. Anything else
#: (length/content_filter/failed/incomplete/refusal/...) must not be
#: accepted as a final answer — see M1-T4.
TERMINAL_FINISH_REASONS = frozenset({"stop", "tool_calls"})


class NonTerminalModelTurn(RuntimeError):
    """A model turn ended without a terminal finish_reason."""


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


def is_nameless_tool_name(name: Any) -> bool:
    """True when the wire said "here is a tool action" but named no tool.

    M8-T335: one malformed answer must read as one behavior on **every** wire
    reader.  M8-T334 settled the rule - a nameless call is noise, drop it - but
    only on two of the five parse paths: the Responses path kept it, and the
    native Anthropic provider kept it on both of its paths.  The consequence is
    always the same paid round: the loop dispatches ``tool=""``, the registry
    answers ``[TOOL_ERROR] 未知工具 ''`` and the model pays for a call that
    never had a target.

    The predicate therefore has **one home** (this function), and each wire
    reader asks it - mirroring ``is_network_tool`` (M8-T307): one rule, many
    asking sites, no divergent copies.  A name that is only whitespace is as
    targetless as an empty one, so both count as nameless.

    Ask it at the only place a wire phrase becomes a tool call:

    * OpenAI chat-completions one-shot and streaming assembly (M8-T334's rule);
    * OpenAI Responses ``function_call`` items;
    * native Anthropic ``tool_use`` blocks (JSON) and SSE assembly.
    """
    return not str(name or "").strip()
