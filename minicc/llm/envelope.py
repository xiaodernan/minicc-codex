"""JSON Action Envelope — fallback protocol for gateways without tool_calls.

Adapted from specproof (providers/prompt_templates.py + craft/llm.py
extract_json_object): the tool definitions are injected into the system
prompt and the model answers tool intent as a single JSON object
{"action": "<tool>", "params": {...}}. The provider converts that object
into a synthetic OpenAI tool_call so the agent loop stays uniform.

extract_json_object is the tolerant parser: it finds the first balanced
JSON object in free text (models like to wrap envelopes in prose or
markdown fences despite the contract) and rejects trailing garbage.
"""

from __future__ import annotations

import json
from typing import Any

ENVELOPE_BLOCK = """\
TOOL CALLING PROTOCOL — JSON Action Envelope:
When you want to call a tool, respond with EXACTLY ONE JSON object of the form
{"action": "<tool_name>", "params": {<tool arguments>}}
and NOTHING else — no markdown fences, no commentary before or after.
When you have the final answer for the user and need no tool, respond with
plain text (no JSON object)."""


def envelope_system_suffix(tools_json: str) -> str:
    return (
        f"{ENVELOPE_BLOCK}\n\nAvailable tools:\n{tools_json}"
    )


def extract_json_object(text: str) -> dict[str, Any] | None:
    """First balanced {...} object in text; None when there is none.

    Raises ValueError when text contains a top-level object candidate that
    fails to parse — callers surface that error to the model for repair.
    """
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start : index + 1]
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
                raise ValueError(f"顶层 JSON 不是对象: {candidate[:80]!r}")
    return None


def parse_envelope(content: str) -> dict[str, Any] | None:
    """Parse a JSON Action Envelope out of assistant text.

    Returns the synthetic OpenAI tool_call dict, or None when the text does
    not carry a tool intent (a malformed object raises ValueError).
    """
    if "{" not in content:
        return None
    obj = extract_json_object(content)
    if obj is None:
        return None
    action = obj.get("action") or obj.get("tool") or obj.get("name")
    if not isinstance(action, str) or not action:
        raise ValueError(f"信封缺少 action 字段: {str(obj)[:120]!r}")
    params = obj.get("params", obj.get("arguments", {}))
    if not isinstance(params, dict):
        raise ValueError(f"信封 params 不是对象: {str(params)[:80]!r}")
    return {
        "id": f"envelope-{id(obj) & 0xFFFFFF:x}",
        "type": "function",
        "function": {"name": action, "arguments": json.dumps(params, ensure_ascii=False)},
    }
