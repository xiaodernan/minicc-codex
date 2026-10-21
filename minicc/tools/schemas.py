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

#: The sentence ``render()`` puts between head and tail.  It names the shipped
#: budget, so any later clip of that text must not drop bytes it advertises.
TRUNCATION_MARKER = f"… [输出已截断: 保留头 {HEAD_CHARS} + 尾 {TAIL_CHARS} 字符] …"

#: The sentence ``record_text`` appends when it has to cut the raw ``output`` channel.
#: It counts the bytes the clip kept and dropped, so the stored text admits its own width.
#: Its narrowest spelling - every count a single digit - is the floor a ceiling has to
#: clear for the sentence to stand inside the record; under that floor the clip keeps the
#: silent prefix it shipped before, which is why the shipped ceilings are read and pinned.
RECORD_CLIP_NOTICE = "… [记录截断：以上只入库前 {kept} 字符，其后 {dropped} 字符未入库；完整输出另有 {total} 字符] …"

#: ``kept`` sets the width of the sentence that prints ``kept``, so the split is solved by
#: iteration; one step per digit a count can gain or lose is more than the loop needs.
_CLIP_NOTICE_STEPS = 8

TOOL_RESULT_STATUSES = ("ok", "error", "denied", "cancelled", "timed_out")


def _clip_notice(kept: int, dropped: int, total: int) -> str:
    return RECORD_CLIP_NOTICE.format(kept=kept, dropped=dropped, total=total)


def _clip_raw(text: str, ceiling: int) -> str:
    """Cut ``text`` to ``ceiling`` characters and say, inside them, how much was lost."""
    total = len(text)
    kept = ceiling - len(_clip_notice(0, total, total))
    for _ in range(_CLIP_NOTICE_STEPS):
        candidate = ceiling - len(_clip_notice(kept, total - kept, total))
        if candidate == kept:
            break
        kept = candidate
    notice = _clip_notice(kept, total - kept, total)
    if kept < 0 or kept + len(notice) != ceiling:
        return text[:ceiling]
    return text[:kept] + notice


def tool_call_name(call: dict[str, Any]) -> str:
    """The **normalized** name of one wire tool call (M8-T341).

    A name has one legal form - a clean one (M8-T336) - and the wire has
    **five** readers of that name: the dispatcher, the round trace, the
    conversation census, the review transcript and the Anthropic wire
    conversion.  Only the dispatcher asked the rule; the other four read the
    raw dictionary, so the same call was called ``read_file`` in one place and
    ``" read_file "`` in another - and the last of those hands the untrimmed
    name to an API that only knows the declared ones.

    This function is the one home: every reader asks it.
    """
    if not isinstance(call, dict):
        return ""
    function = call.get("function") or {}
    return str(function.get("name") or call.get("name") or "").strip()


def normalized_tool_calls(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The wire tool calls with the one legal spelling of each name (M8-T347).

    M8-T341 gave the name one home and made the readers ask it.  But the
    **chat** wire sends the history as it is, and two other wires (the
    envelope and the Responses formats) render the history themselves - so
    the raw spelling still reached the model, the API and the session log.

    Cleaning it once, where the assistant turn enters the history, makes
    every form carry the same name - the one the dispatcher used.
    """
    out: list[dict[str, Any]] = []
    for call in calls or []:
        function = call.get("function") if isinstance(call, dict) else None
        if not isinstance(function, dict):
            out.append(call)
            continue
        name = tool_call_name(call)
        if name == function.get("name"):
            out.append(call)
            continue
        out.append({**call, "function": {**function, "name": name}})
    return out


@dataclass(frozen=True)
class ToolCall:
    tool: str
    arguments: dict[str, Any] = field(default_factory=dict)
    call_id: str = ""
    parse_error: str | None = None

    @staticmethod
    def from_openai(call: dict[str, Any]) -> ToolCall:
        """Parse an OpenAI wire-format tool_call (arguments is a JSON string)."""
        import json

        function = call.get("function") or {}
        raw_args = function.get("arguments") or "{}"
        parse_error: str | None = None
        try:
            if isinstance(raw_args, dict):
                arguments = raw_args
            else:
                arguments = json.loads(raw_args)
        except (json.JSONDecodeError, TypeError):
            # Some compatible gateways serialize function arguments with
            # single quotes.  Accept that narrow Python-literal dialect, but
            # preserve a structured error when it still cannot be decoded.
            try:
                import ast

                arguments = ast.literal_eval(raw_args)
            except (SyntaxError, ValueError, TypeError, MemoryError, RecursionError):
                arguments = {}
                parse_error = "工具参数不是合法 JSON 对象，执行器将把解析错误反馈给模型。"
        if not isinstance(arguments, dict):
            arguments = {}
            parse_error = "工具参数顶层必须是对象，执行器将把参数解析错误反馈给模型。"
        # M8-T336: a name has one legal form - a clean one.  This is the
        # single place a wire phrase becomes the dispatchable name, so the
        # trim is asked once here and every consumer below (the registry
        # lookup, the risk rules, the traces, the duplicate signature) reads
        # the same normalized call.  A name with stray edges used to reach
        # the registry untrimmed and buy the model a paid round of
        # "[TOOL_ERROR] 未知工具 'read_file '" for an intent that was not
        # ambiguous.
        return ToolCall(
            tool=tool_call_name(call),
            arguments=arguments,
            call_id=str(call.get("id") or ""),
            parse_error=parse_error,
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
            # the sentence below promises a tail; it may print only with those bytes
            if self.truncated and self.tail:
                parts.append(f"\n{TRUNCATION_MARKER}\n")
                parts.append(self.tail)
        elif self.output:
            parts.append(self.output)
        text = "\n".join(parts).strip()
        return text or f"[{self.status}]"

    def record_text(self, ceiling: int) -> str:
        """The stored form of ``render()``: ``ceiling`` bounds only the raw ``output``
        channel.  A body that came through ``split_output`` is already inside the
        shipped head/tail budget, and cutting it further would drop tail bytes
        while the stored text still prints the marker that promises them.  A cut of
        the raw channel appends the sentence counting the bytes it dropped.
        """
        text = self.render()
        if self.head:
            return text
        if len(text) <= ceiling:
            return text
        return _clip_raw(text, ceiling)

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
