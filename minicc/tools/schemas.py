"""Tool call/result schemas (plain dataclasses; adapted from specproof).

ToolResult.output is always untrusted model-facing data: it carries stable
[CODE] error prefixes and a security_tags list, and handlers must route it
through redact_text + head/tail truncation before returning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Output truncation: keep the head and the tail, honestly flag the cut.
HEAD_CHARS = 2000
TAIL_CHARS = 4000

TOOL_RESULT_STATUSES = ("ok", "error", "denied", "cancelled", "timed_out")


@dataclass(frozen=True)
class ToolCall:
    tool: str
    arguments: dict[str, Any] = field(default_factory=dict)
    call_id: str = ""

    @staticmethod
    def from_openai(call: dict[str, Any]) -> ToolCall:
        """Parse an OpenAI wire-format tool_call (arguments is a JSON string)."""
        import json

        function = call.get("function") or {}
        raw_args = function.get("arguments") or "{}"
        try:
            arguments = json.loads(raw_args)
        except (json.JSONDecodeError, TypeError):
            arguments = {"_raw_arguments": raw_args}
        if not isinstance(arguments, dict):
            arguments = {"_raw_arguments": raw_args}
        return ToolCall(
            tool=str(function.get("name") or call.get("name") or ""),
            arguments=arguments,
            call_id=str(call.get("id") or ""),
        )


@dataclass
class ToolResult:
    status: str = "ok"  # ok | error | denied | cancelled | timed_out
    summary: str = ""
    output: str = ""
    head: str = ""
    tail: str = ""
    truncated: bool = False
    exit_code: int | None = None
    duration: float = 0.0
    security_tags: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)  # structured extras (digest etc.)

    def render(self) -> str:
        """Model-facing text: summary line + output body (head…tail)."""
        parts = [self.summary] if self.summary else []
        if self.head:
            parts.append(self.head)
            if self.truncated:
                parts.append(f"\n… [输出已截断: 保留头 {HEAD_CHARS} + 尾 {TAIL_CHARS} 字符] …\n")
                parts.append(self.tail)
        elif self.output:
            parts.append(self.output)
        text = "\n".join(parts).strip()
        return text or f"[{self.status}]"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "summary": self.summary,
            "exit_code": self.exit_code,
            "duration": round(self.duration, 3),
            "truncated": self.truncated,
            "security_tags": list(self.security_tags),
            "data": dict(self.data),
        }
