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

import ast
import json
from typing import Any

ENVELOPE_BLOCK = """\
TOOL CALLING PROTOCOL — JSON Action Envelope:
When you want to call a tool, respond with EXACTLY ONE JSON object of the form
{"action": "<tool_name>", "params": {<tool arguments>}}
and NOTHING else — no markdown fences, no commentary before or after.
When you have the final answer for the user and need no tool, respond with
plain text (no JSON object)."""
MAX_REPAIR_CONTENT_CHARS = 12_000


def envelope_system_suffix(tools_json: str) -> str:
    return (
        f"{ENVELOPE_BLOCK}\n\nAvailable tools:\n{tools_json}"
    )


class EnvelopeParseError(ValueError):
    """A model action envelope was present but could not be normalized."""

    def __init__(self, message: str, *, content: str = "") -> None:
        super().__init__(message)
        raw_content = str(content or "")
        if len(raw_content) > MAX_REPAIR_CONTENT_CHARS:
            head = MAX_REPAIR_CONTENT_CHARS // 2
            tail = MAX_REPAIR_CONTENT_CHARS - head
            raw_content = (
                raw_content[:head]
                + "\n[损坏的模型输出已截断]\n"
                + raw_content[-tail:]
            )
        self.content = raw_content


def _parse_object(candidate: str) -> dict[str, Any]:
    """Parse strict JSON first, then the small Python-literal dialect models emit."""
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as json_error:
        try:
            parsed = ast.literal_eval(candidate)
        except (SyntaxError, ValueError, TypeError, MemoryError, RecursionError) as literal_error:
            raise EnvelopeParseError(
                "动作信封无法解析：需要合法 JSON 对象；"
                f"JSON 错误为 {json_error.msg}，兼容解析也失败 ({type(literal_error).__name__})。"
            ) from json_error
    if not isinstance(parsed, dict):
        raise EnvelopeParseError(f"动作信封顶层必须是对象，实际为 {type(parsed).__name__}。")
    return parsed


def extract_json_object(text: str) -> dict[str, Any] | None:
    """First balanced {...} object in text; None when there is none.

    Raises ValueError when text contains a top-level object candidate that
    fails to parse — callers surface that error to the model for repair.
    """
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    quote: str | None = None
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in ('"', "'"):
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start : index + 1]
                return _parse_object(candidate)
    return None


def parse_envelope(content: str) -> dict[str, Any] | None:
    """Parse a JSON Action Envelope out of assistant text.

    Returns the synthetic OpenAI tool_call dict, or None when the text does
    not carry a tool intent (a malformed object raises ValueError).
    """
    if "{" not in content:
        return None
    try:
        obj = extract_json_object(content)
    except EnvelopeParseError as exc:
        if exc.content:
            raise
        raise EnvelopeParseError(str(exc), content=content) from exc
    if obj is None:
        raise EnvelopeParseError("动作信封不完整：对象缺少结束括号。", content=content)
    action = obj.get("action") or obj.get("tool") or obj.get("name")
    params = obj.get("params", obj.get("arguments", {}))
    if isinstance(action, dict):
        action_object = dict(action)
        action = action_object.get("action") or action_object.get("tool") or action_object.get("name")
        nested_params = action_object.get("params", action_object.get("arguments"))
        action_params = {
            key: value
            for key, value in action_object.items()
            if key not in {"action", "tool", "name", "params", "arguments"}
        }
        if isinstance(nested_params, dict):
            action_params.update(nested_params)
        if isinstance(params, dict):
            action_params.update(params)
        params = action_params
        if not action and "command" in action_object:
            action = "bash"
    elif isinstance(action, str) and action == "bash" and isinstance(params, dict) and not params and "command" in obj:
        params = {"command": obj["command"]}
    if not isinstance(action, str) or not action:
        raise EnvelopeParseError(f"信封缺少 action 字段: {str(obj)[:120]!r}", content=content)
    if not isinstance(params, dict):
        raise EnvelopeParseError(f"信封 params 不是对象: {str(params)[:80]!r}", content=content)
    return {
        "id": f"envelope-{id(obj) & 0xFFFFFF:x}",
        "type": "function",
        "function": {"name": action, "arguments": json.dumps(params, ensure_ascii=False)},
    }
