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


def safe_int(value: Any, default: int | None = None) -> int | None:
    """Read an integer a gateway may have sent malformed.

    M8-T359: the Anthropic stream's framing fields (``index``) were read
    with a bare ``int(...)`` - so a gateway that mangled the framing raised
    TypeError and killed the whole turn, while the other wire simply
    retried.  One home: every wire reader asks it.  ``default=None`` means
    "not reported"; pass 0 for a field that is simply absent.
    """
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def as_dict(value: Any) -> dict[str, Any]:
    """Read an object a gateway may have sent as something else.

    M8-T359: the JSON path already skipped a block that was not an object
    ("if not isinstance(block, dict): continue"), while the stream path
    called ``.get`` on whatever arrived - so a list in place of a block
    raised AttributeError and killed the turn.  One home, both readers.
    """
    return value if isinstance(value, dict) else {}


def unique_tool_call_id(raw_id: str, fallback: str, seen: set[str] | None = None) -> str:
    """Return a non-empty, unique tool_call id for one response.

    M8-T356: this is the **one** home for the id repair.  Gateways may omit
    ids or reuse one id across calls; the agent loop and
    ``repair_interrupted_tool_rounds`` key tool results by id, so a duplicate
    silently drops or misroutes a result - and an empty id makes the protocol
    validator refuse the history, which kills the turn.  First use wins for a
    given raw id; later duplicates and empty ids get ``<base>-dup<N>``.

    It used to live in ``openai_provider`` only - so the OpenAI-compatible
    wire was repaired and the Anthropic wire was not: the same malformed
    gateway answer gave two different behaviors (M8-T334's family, again).
    """
    base = (raw_id or "").strip() or fallback
    if seen is None:
        return base
    candidate = base
    counter = 1
    while candidate in seen:
        counter += 1
        candidate = f"{base}-dup{counter}"
    seen.add(candidate)
    return candidate


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


def tool_call(call_id: str, name: str, arguments: str) -> dict[str, Any]:
    """The one shape of a function tool call on the wire.

    Eight places used to write this three-key record by hand: the agent
    loop's recovery call, the fake provider, the envelope action, and five
    parse paths across the OpenAI and Anthropic providers.  ``type`` is
    always ``"function"`` and the name/arguments pair always travels inside
    a nested ``function`` dict - two facts a hand-written copy can get
    subtly wrong (a flat ``name``, a missing ``type``), and the readers on
    the other side read exactly these keys.
    """
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


def tool_result_msg(tool_call_id: str, content: str) -> dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": content,
    }


def retry_detail(attempt: int, retry_limit: int) -> dict[str, int]:
    """The one shape of the provider-retry trace detail.

    The real stream retry and the fake provider's deliberate imitation
    of it spell these two keys by hand.  The imitation exists so a log
    or event assertion written against the fake describes the
    production trace - a key it drops is a test that passes while the
    real event's readers see nothing.
    """
    return {"attempt": attempt, "retry_limit": retry_limit}


#: The one wording of the provider-retry trace summary.  The fake provider
#: emits this exact sentence on purpose: an assertion written against the
#: fake must describe the production trace (see ``retry_detail`` above).  A
#: rename of the real sentence that the fake does not follow is a test that
#: keeps passing while describing a trace production no longer emits
#: (M8-T488).  The pre-stream ``模型请求暂时失败`` retry is a different fact
#: about a different moment and keeps its own wording.
STREAM_RETRY_SUMMARY = "模型流中断，正在进行第 {attempt} 次重试"


def stream_retry_summary(attempt: int) -> str:
    """The provider-retry summary for the given attempt number."""
    return STREAM_RETRY_SUMMARY.format(attempt=attempt)


#: The one wording of the mid-stream partial failure.  Both channels' streams
#: can break after deltas were already delivered, and each channel raises its
#: own partial error carrying this sentence.  The sentence reaches the model
#: context through ``LLM 调用失败: {exc}``, so a wording only one channel
#: follows is an error message the other channel's readers have never seen
#: (M8-T489).  ``responses stream ended without a final response`` is a
#: different moment and keeps its own sentence.
def stream_broke_message(channel: str, chars: int, exc: BaseException) -> str:
    """The partial-failure sentence for a stream that broke mid-delivery."""
    return f"{channel} stream broke after delivering {chars} chars: {type(exc).__name__}"


def image_part(url: str, detail: str | None = None) -> dict[str, Any]:
    """The one shape of an image part on the chat-completions wire.

    Two sites built it by hand: the context normalizer (with an optional
    ``detail``) and the task manager's attachment parts (without).  This
    is **not** the Responses wire's image part - that one spells
    ``type="input_image"`` and carries the url as a bare string
    (``openai_provider._responses_content_parts``), a different fact
    with the same two key names.  ``VISUAL_PART_TYPES`` in
    ``agent/context.py`` is the vocabulary that names both.
    """
    image_url: dict[str, Any] = {"url": str(url)}
    if detail:
        image_url["detail"] = str(detail)
    return {"type": "image_url", "image_url": image_url}


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
