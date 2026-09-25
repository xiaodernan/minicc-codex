"""The core multi-turn tool-calling agent loop.

This is the heart of minicc — the part that does NOT exist in specproof
(which has a batch planner-executor loop instead). The design:

1. User message is appended to the conversation history.
2. The provider is called with the full history + tool schemas.
3. If the response contains tool_calls, each is executed and the result
   is appended (as a tool role message). Then go back to 2.
4. If the response is plain text (finish_reason stop, no tool_calls),
   the text is the final answer — return it to the REPL.
5. On each iteration the caller-supplied *on_stream* callback receives
   text deltas for live terminal rendering.
6. After every tool-execution round the context is compacted if needed.
7. The normal Web/CLI runtime has no task-level duration, turn, token, or
   tool-count budget; it continues until the model returns an answer or an
   explicit cancellation/protection condition is reached. The optional
   *max_turns* argument remains only as a programmatic compatibility hook for
   focused tests and embedding callers.

Permission: the *should_allow* callback is consulted before every
write/exec tool call and every network tool (web_search / webfetch).
It receives the tool name and parsed ToolCall; returning False produces
a 'denied' result.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import threading
import time
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable

from ..llm.base import LLMResponse, TERMINAL_FINISH_REASONS, assistant_msg, tool_result_msg, user_msg
from ..llm.envelope import EnvelopeParseError
from ..llm.openai_provider import OpenAICompatibleProvider
from ..llm.usage import add_usage_totals, cache_summary
from ..tools.schemas import ToolCall, ToolResult
from ..tools.registry import ToolRegistry, redact_text
from ..hooks import payloads_for_result, payloads_for_tool_call
from .context import compact_with_checkpoint, estimate_tokens, message_chars, repair_interrupted_tool_rounds, validate_tool_protocol
from .state import AgentState, Budget, BudgetExceeded
from .tool_policy import (
    NETWORK_TOOL_NAMES,
    is_verification_evidence,
    is_workspace_write,
    tool_requires_authorization,
)


# A repeated path is a recovery signal, not an immediate task failure.  The
# limit remains finite so a broken provider cannot consume an unbounded run.
STAGNATION_REPLAN_LIMIT = 3
STAGNATION_REPEAT_LIMIT = 2
STAGNATION_CYCLE_LENGTH = 4
VERIFICATION_RETRY_LIMIT = 1
SEARCH_FAILURE_LIMIT = 2
PROTOCOL_REPAIR_LIMIT = 2
RECOVERY_PROBE_TOOLS = ("git_status", "git_diff", "tree")
MAX_RESULT_TRACE_EVENTS = 1024
MAX_RESULT_USAGE_ENTRIES = 64
MAX_RESULT_COMPACTION_ENTRIES = 64
MAX_TOOL_CACHE_ENTRIES = 128
MAX_VISIBLE_MODEL_UPDATE_CHARS = 1200
MAX_PUBLIC_TOOL_OBSERVATION_CHARS = 900
MAX_PUBLIC_TOOL_DATA_CHARS = 2400
VISION_CONTEXT_MARKER = "[持久视觉上下文]"
WRITE_TOOL_NAMES = frozenset({"write_file", "edit_file", "worktree_create", "worktree_remove"})
# Inspection tools are not verification. Post-write evidence must come from
# bash test/lint commands (see ``is_verification_evidence``).
VERIFY_TOOL_NAMES = frozenset({"bash"})

# M8-T56: the model cannot guess which commands the completion gate accepts.
# These examples are the same whitelist ``is_verification_evidence`` enforces,
# so a nudge can never name a checker the gate would then reject. The fallback
# (``compileall``) is what a fixture workspace with no test suite can still run:
# without it the guard asks for evidence that does not exist and the task dies
# with the artifact already correct.
VERIFICATION_CHECKER_EXAMPLES = (
    "python -m pytest",
    "python -m compileall <改动的.py文件>",
    "mypy <改动的.py文件>",
    "node --check <改动的.js文件>",
    "npm run test",
)
_VERIFICATION_EXAMPLE_HINT = "、".join(VERIFICATION_CHECKER_EXAMPLES)

# Injected after a write, and again when the model tries to finish without
# post-write evidence (``VERIFICATION_RETRY_LIMIT`` keeps that to one nudge).
POST_WRITE_VERIFICATION_NUDGE = (
    "[执行器提示] 本轮已经修改工作区。下一轮必须先检查相关 diff，"
    "再运行最小且直接相关的测试或验证（例如 " + _VERIFICATION_EXAMPLE_HINT + "）；"
    "只有白名单检查器的成功运行算验证证据，直接执行脚本不算。"
    "如果验证失败，继续修复。"
)
PRE_FINISH_VERIFICATION_NUDGE = (
    "[执行器提示] 你已经修改了工作区，但还没有收到修改后的验证证据。"
    "不能先结束任务；请先检查相关 diff，再运行最小且直接相关的验证，然后总结结果。"
    "验证证据必须是 bash 成功运行白名单检查器之一（" + _VERIFICATION_EXAMPLE_HINT + "）；"
    "直接执行脚本或只打印输出不算验证证据。"
    "如果工作区没有任何可运行的检查，运行 python -m compileall 校验改动的 Python 文件语法即可。"
)


class AgentCancelled(Exception):
    """Internal control flow for cancelling an in-flight provider request."""


async def _wait_for_cancel(cancel_event: threading.Event) -> None:
    while not cancel_event.is_set():
        await asyncio.sleep(0.1)


async def chat_with_cancellation(
    provider: OpenAICompatibleProvider,
    *,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    on_delta: Callable[[str], None] | None,
    cancel_event: threading.Event | None,
    timeout_seconds: float | None = None,
) -> LLMResponse:
    """Race a model request against cancellation and an optional request deadline."""
    validate_tool_protocol(messages)
    if cancel_event is None:
        if timeout_seconds is None:
            return await provider.chat(messages=messages, tools=tools, on_delta=on_delta)
        if timeout_seconds <= 0:
            raise BudgetExceeded("最大执行时间已用尽")
        try:
            return await asyncio.wait_for(
                provider.chat(messages=messages, tools=tools, on_delta=on_delta),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise BudgetExceeded("最大执行时间已用尽，已取消当前模型请求") from exc
    if cancel_event.is_set():
        raise AgentCancelled
    request = asyncio.create_task(
        provider.chat(messages=messages, tools=tools, on_delta=on_delta)
    )
    watcher = asyncio.create_task(_wait_for_cancel(cancel_event))
    deadline = (
        asyncio.create_task(asyncio.sleep(timeout_seconds))
        if timeout_seconds is not None
        else None
    )
    try:
        waiters: set[asyncio.Task[Any]] = {request, watcher}
        if deadline is not None:
            waiters.add(deadline)
        done, _pending = await asyncio.wait(
            waiters,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if request in done:
            return request.result()
        if watcher in done:
            request.cancel()
            await asyncio.gather(request, return_exceptions=True)
            raise AgentCancelled
        if deadline is not None and deadline in done:
            request.cancel()
            await asyncio.gather(request, return_exceptions=True)
            raise BudgetExceeded("最大执行时间已用尽，已取消当前模型请求")
        return request.result()
    finally:
        if not watcher.done():
            watcher.cancel()
        if deadline is not None and not deadline.done():
            deadline.cancel()
        if not request.done():
            request.cancel()
        pending_tasks: list[asyncio.Task[Any]] = [watcher, request]
        if deadline is not None:
            pending_tasks.append(deadline)
        await asyncio.gather(*pending_tasks, return_exceptions=True)


@dataclass
class TurnResult:
    """One complete agent run (user msg in → final text out)."""
    answer: str
    turns: int = 0
    tool_calls_total: int = 0
    tokens_used: dict[str, int] = field(default_factory=dict)
    usage_by_turn: list[dict[str, Any]] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    compaction_events: list[dict[str, Any]] = field(default_factory=list)
    trace_events: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    denied_tools: list[str] = field(default_factory=list)
    cancelled: bool = False
    completion: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)


def _visible_model_update(content: str | None) -> str:
    """Return a bounded, redacted public assistant message for the task timeline."""
    if not content:
        return ""
    safe, _ = redact_text(content.strip())
    if len(safe) > MAX_VISIBLE_MODEL_UPDATE_CHARS:
        safe = safe[:MAX_VISIBLE_MODEL_UPDATE_CHARS].rstrip() + "\n[行动说明已截断]"
    return safe


def _visible_model_delta(previous: str, content: str | None) -> tuple[str, str]:
    """Return only the newly appended part of a cumulative public update."""
    current = _visible_model_update(content)
    if not current:
        return previous, ""
    if not previous:
        return current, current
    if current.startswith(previous):
        return current, current[len(previous):]
    if previous.startswith(current):
        return previous, ""
    # A new turn normally starts a new action explanation.  Do not join it to
    # the old sentence, otherwise a later cumulative update can grow forever.
    return current, current


def _merge_incremental_text(previous: str, current: str) -> tuple[str, str]:
    """Fold a cumulative update into what we have; never delete a chunk.

    Exactly one shape is safe to absorb: the new chunk repeating everything so
    far *and extending it*, which is what a gateway resending the whole attempt
    text looks like. The old rule also discarded a chunk that was a prefix of,
    or merely overlapped, what we already had - so streaming "7", ".", "7",
    ".", "7" lost the third piece and the terminal showed "7." for an answer
    that was stored as "7.7.7". Anything uncertain is appended verbatim: a
    repeated fragment is visible and fixable, a dropped one is neither.
    """
    if not previous:
        return current, current
    if not current:
        return previous, ""
    if current.startswith(previous):
        return current, current[len(previous):]
    return previous + current, current


def _normalize_vision_context(parts: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Normalize image parts to the Chat Completions shape used by history."""
    normalized: list[dict[str, Any]] = []
    for raw in parts or []:
        if not isinstance(raw, dict):
            continue
        part_type = str(raw.get("type") or "").lower()
        if part_type not in {"image_url", "input_image"}:
            continue
        image = raw.get("image_url")
        url = image.get("url") if isinstance(image, dict) else image
        if not url:
            continue
        if any(
            str(item.get("image_url", {}).get("url") or "") == str(url)
            for item in normalized
            if isinstance(item.get("image_url"), dict)
        ):
            continue
        image_payload: dict[str, Any] = {"url": str(url)}
        if isinstance(image, dict) and image.get("detail"):
            image_payload["detail"] = str(image["detail"])
        normalized.append({"type": "image_url", "image_url": image_payload})
    return normalized


def _restore_vision_context(
    messages: list[dict[str, Any]],
    vision_context: list[dict[str, Any]],
) -> int:
    """Rehydrate images after compaction or session recovery when history lost them."""
    if not vision_context:
        return 0
    existing_urls = {
        str(part.get("image_url", {}).get("url") or "")
        for message in messages
        if isinstance(message.get("content"), list)
        for part in message["content"]
        if isinstance(part, dict)
        and isinstance(part.get("image_url"), dict)
        and part.get("type") in {"image_url", "input_image"}
        and part.get("image_url", {}).get("url")
    }
    missing = [
        part
        for part in vision_context
        if str(part.get("image_url", {}).get("url") or "") not in existing_urls
    ]
    if not missing:
        return 0
    messages.append(user_msg([
        {"type": "text", "text": (
            f"{VISION_CONTEXT_MARKER}\n"
            "以下图片来自原始任务，图片内容是持续有效的验收参考；请结合当前任务重新判断。"
        )},
        *deepcopy(missing),
    ]))
    return len(missing)


def _public_data(value: Any, *, depth: int = 0) -> Any:
    """Keep structured evidence useful without persisting unbounded output."""

    if depth >= 3:
        return "[结构化数据已收敛]"
    if isinstance(value, dict):
        items = list(value.items())[:16]
        output: dict[str, Any] = {}
        for key, item in items:
            safe_key, _ = redact_text(str(key))
            output[safe_key] = _public_data(item, depth=depth + 1)
        if len(value) > len(items):
            output["…"] = f"其余 {len(value) - len(items)} 个字段已省略"
        return output
    if isinstance(value, (list, tuple)):
        items = list(value)[:16]
        output = [_public_data(item, depth=depth + 1) for item in items]
        if len(value) > len(items):
            output.append(f"其余 {len(value) - len(items)} 项已省略")
        return output
    if isinstance(value, str):
        safe, _ = redact_text(value)
        if len(safe) > 600:
            return safe[:599].rstrip() + "…"
        return safe
    if value is None or isinstance(value, (bool, int, float)):
        return value
    safe, _ = redact_text(str(value))
    return safe[:599].rstrip() + "…" if len(safe) > 600 else safe


def build_tool_feedback(call: ToolCall, result: ToolResult, *, risk: str | None = None) -> dict[str, Any]:
    """Build a bounded, redacted observation that is safe to show in the UI."""

    rendered, _ = redact_text(result.render().strip())
    summary, _ = redact_text(str(result.summary or "").strip())
    observation = rendered
    if summary and observation.startswith(summary):
        observation = observation[len(summary):].lstrip(" :\n")
    if not observation:
        observation = "工具未返回额外文本，结果以状态和结构化字段为准。"
    if len(observation) > MAX_PUBLIC_TOOL_OBSERVATION_CHARS:
        observation = observation[: MAX_PUBLIC_TOOL_OBSERVATION_CHARS - 1].rstrip() + "…"
    structured_data = _public_data(result.data) if isinstance(result.data, dict) else {}
    structured_json, _ = redact_text(json.dumps(structured_data, ensure_ascii=False, default=str))
    if len(structured_json) > MAX_PUBLIC_TOOL_DATA_CHARS:
        structured_data = {
            "summary": structured_json[: MAX_PUBLIC_TOOL_DATA_CHARS - 1].rstrip() + "…",
            "truncated": True,
        }
    data_keys = list(structured_data)[:16] if isinstance(structured_data, dict) else []
    raw_path = str(call.arguments.get("path") or "")
    raw_command = str(call.arguments.get("command") or "")
    safe_path, _ = redact_text(raw_path)
    safe_command, _ = redact_text(raw_command)
    return {
        "tool": call.tool,
        "status": result.status,
        "summary": summary,
        "observation": observation,
        "path": safe_path or None,
        "command": safe_command or None,
        "risk": risk,
        "write": is_workspace_write(call.tool, call.arguments, result.status),
        "exit_code": result.exit_code,
        "duration_ms": round(max(0.0, float(result.duration or 0.0)) * 1000, 1),
        "truncated": bool(result.truncated),
        "security_tags": list(result.security_tags),
        "data_keys": data_keys,
        "structured_data": structured_data,
    }


def _replan_constraints(*, verification_required: bool, feedback: list[dict[str, Any]]) -> list[str]:
    """Describe runtime constraints without exposing hidden model reasoning."""

    constraints: list[str] = []
    if verification_required:
        constraints.append("工作区发生过修改，结束前必须取得修改后的 diff/测试证据")
    failed_tools = [
        str(item.get("tool") or "tool")
        for item in feedback
        if str(item.get("status") or "") in {"error", "failed", "denied", "timed_out"}
    ]
    if failed_tools:
        constraints.append(f"上一轮有失败或被阻止的工具：{', '.join(failed_tools[:6])}")
    if feedback and all(not str(item.get("observation") or "").strip() for item in feedback):
        constraints.append("上一轮没有产生可用观察结果，需要更换检查路径")
    return constraints


async def run_agent(
    provider: OpenAICompatibleProvider,
    registry: ToolRegistry,
    messages: list[dict[str, Any]],
    *,
    max_turns: int | None = None,
    compact_threshold: int = 300_000,
    on_stream: Callable[[str], None] | None = None,
    on_tool: Callable[[ToolCall, ToolResult], None] | None = None,
    on_usage: Callable[[dict[str, Any]], None] | None = None,
    on_context: Callable[[dict[str, Any]], None] | None = None,
    on_compaction: Callable[[dict[str, Any]], None] | None = None,
    on_trace: Callable[[dict[str, Any]], None] | None = None,
    should_allow: Callable[[str, ToolCall], bool] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    cancel_event: threading.Event | None = None,
    context_limit_tokens: int = 300_000,
    budget: Budget | None = None,
    runtime_state: AgentState | None = None,
    require_recovery_inspection: bool = False,
    vision_context: list[dict[str, Any]] | None = None,
    hooks: Any | None = None,
) -> TurnResult:
    """Run the agent loop until a final text answer or explicit cancellation.

    *messages* is mutated in place (tool calls/results are appended).
    The caller is responsible for injecting the initial system prompt
    and the first user message before calling this function. ``max_turns``
    is retained for embedding/test compatibility; Web tasks pass ``None``.
    """
    if max_turns is not None and max_turns <= 0:
        max_turns = None
    result = TurnResult(answer="")
    persistent_vision_context = _normalize_vision_context(vision_context)
    restored_vision_contexts = 0
    allow = should_allow or _always_allow
    runtime_budget = budget or (runtime_state.budget if runtime_state is not None else Budget(max_turns=max_turns))
    if runtime_budget.max_turns is None:
        runtime_budget.max_turns = max_turns
    tools_schemas = registry.openai_schemas()
    streamed_text: list[str] = []
    streamed_output = ""
    last_round_signature = ""
    repeated_rounds = 0
    unproductive_rounds = 0
    stagnation_replans = 0
    recent_observations: list[str] = []
    tool_result_cache: dict[str, ToolResult] = {}
    search_failures = 0
    last_reasoning_status: tuple[str, str] | None = None
    verification_required = False
    soft_wrap_issued = False
    recovery_inspection_required = bool(require_recovery_inspection)
    recovery_refusals = 0
    nonterminal_repairs = 0
    verification_retries = 0
    last_round_feedback: list[dict[str, Any]] = []
    last_replan_trigger = "初始任务上下文"
    protocol_repairs = 0
    last_public_model_update = ""
    hooks_enabled = hooks is not None and bool(getattr(hooks, "enabled", False))

    def cache_tool_result(key: str, value: ToolResult) -> None:
        """Keep read-result reuse bounded during an unlimited run."""
        tool_result_cache.pop(key, None)
        tool_result_cache[key] = deepcopy(value)
        while len(tool_result_cache) > MAX_TOOL_CACHE_ENTRIES:
            tool_result_cache.pop(next(iter(tool_result_cache)))

    def cancellation_requested() -> bool:
        return bool(
            (cancel_event is not None and cancel_event.is_set())
            or (should_cancel is not None and should_cancel())
        )

    def emit_trace(
        summary: str,
        *,
        phase: str = "planning",
        status: str = "ok",
        code: str = "milestone",
        detail: dict[str, Any] | str | None = None,
    ) -> None:
        event = {
            "kind": "trace",
            "name": "agent",
            "status": status,
            "phase": phase,
            "code": code,
            "summary": summary,
        }
        if detail is not None:
            event["detail"] = detail
        result.trace_events.append(event)
        if len(result.trace_events) > MAX_RESULT_TRACE_EVENTS:
            del result.trace_events[: len(result.trace_events) - MAX_RESULT_TRACE_EVENTS]
        if runtime_state is not None:
            runtime_state.add_trace(event)
        if on_trace is not None:
            on_trace(event)

    def emit_stream(delta: str) -> None:
        nonlocal streamed_output
        if delta:
            streamed_output, suffix = _merge_incremental_text(streamed_output, str(delta))
            if not suffix:
                return
            streamed_text.append(suffix)
            if on_stream is not None:
                on_stream(suffix)

    def run_hook(event: str, payload: dict[str, Any]) -> Any:
        """Fire one hook event; returns the outcome or None when disabled.

        Hook failures never raise into the loop — the runner itself is the
        isolation boundary (timeouts, denials, redaction all stay inside).
        """
        if not hooks_enabled:
            return None
        outcome = hooks.run(event, payload)
        for entry in getattr(outcome, "outputs", []):
            emit_trace(
                f"Hook {event} 执行完成（{entry.get('decision', 'allow')}）: {entry.get('command', '')}",
                phase="tool",
                status="error" if entry.get("decision") == "deny" else "ok",
                code="hook_executed",
                detail=dict(entry),
            )
        return outcome

    async def run_recovery_probe(attempt: int) -> list[dict[str, Any]]:
        """Collect fresh, read-only workspace evidence after stagnation.

        The probe is part of the conversation, so the next model turn sees
        the actual state that caused recovery instead of receiving another
        abstract request to "try harder".  It never writes files.
        """

        names = [name for name in RECOVERY_PROBE_TOOLS if registry.spec(name) is not None]
        if not names:
            return []
        if cancellation_requested():
            result.cancelled = True
            result.error = "任务已取消"
            result.answer = "任务已取消。"
            return []
        raw_calls = [
            {
                "id": f"recovery-{attempt}-{index}",
                "type": "function",
                "function": {"name": name, "arguments": "{}"},
            }
            for index, name in enumerate(names, start=1)
        ]
        try:
            runtime_budget.record_tool_call(len(raw_calls))
        except BudgetExceeded as exc:
            result.error = f"Agent 预算超限: {exc}"
            result.answer = f"任务未完成：{result.error}"
            emit_trace(result.error, phase="failed", status="error", code="budget_exceeded")
            return []

        messages.append(assistant_msg(
            content="执行器触发恢复诊断，先读取当前工作区状态。",
            tool_calls=raw_calls,
        ))
        probe_results = await asyncio.gather(
            *(
                asyncio.to_thread(
                    registry.execute,
                    ToolCall.from_openai(raw_call),
                    cancel_event=cancel_event,
                )
                for raw_call in raw_calls
            )
        )
        feedback: list[dict[str, Any]] = []
        for raw_call, tool_result in zip(raw_calls, probe_results):
            call = ToolCall.from_openai(raw_call)
            result.tool_calls_total += 1
            cache_tool_result(_signature({"tool": call.tool, "arguments": call.arguments}), tool_result)
            if on_tool is not None:
                on_tool(call, tool_result)
            messages.append(tool_result_msg(raw_call["id"], tool_result.render()))
            feedback.append(build_tool_feedback(call, tool_result, risk=registry.risk_of(call.tool)))
        emit_trace(
            "已完成恢复诊断，下一轮将基于当前工作区证据重新选择路径",
            phase="planning",
            code="recovery_probe_finished",
            detail={"attempt": attempt, "results": feedback},
        )
        return feedback

    emit_trace(
        "正在界定任务范围，准备检查工作区",
        phase="planning",
        code="run_started",
        detail={
            "max_turns": max_turns,
            "recovery_inspection_required": bool(require_recovery_inspection),
            # Keep the established prefix for clients that classify this
            # trace, while retaining the fuller list of termination guards.
            "turn_policy": (
                "默认不限模型轮次；任务无总轮次上限" if max_turns is None else f"兼容调用轮次上限 {max_turns}"
            ) + "；由交付、取消、协议/停滞纠偏、验证和服务生命周期结束",
            "tool_count": len(tools_schemas),
            "vision_context_count": len(persistent_vision_context),
        },
    )
    repaired_results = repair_interrupted_tool_rounds(messages)
    if repaired_results:
        recovery_inspection_required = True
        emit_trace(
            "已补全中断轮次的未知结果；继续执行前先核对工作区状态",
            code="tool_history_recovered",
            detail={"missing_results": repaired_results},
        )
    reasoning_status_fn = getattr(provider, "reasoning_status", None)
    protocol_status_fn = getattr(provider, "protocol_status", None)
    if callable(protocol_status_fn):
        protocol_status = dict(protocol_status_fn())
        emit_trace(
            f"模型调用协议：{protocol_status.get('active')}",
            phase="planning",
            code="provider_protocol",
            detail=protocol_status,
        )
    if callable(reasoning_status_fn):
        status = dict(reasoning_status_fn())
        requested = str(status.get("requested") or "")
        active = str(status.get("active") or "")
        if requested:
            effort_label = {"low": "低", "mid": "中", "high": "高", "xhigh": "极高", "max": "最高"}.get(requested, requested)
            emit_trace(
                f"已启用{effort_label}推理强度；界面展示阶段摘要，不展示模型私有思维链",
                phase="planning",
                code="reasoning_configured",
                detail={
                    "requested": requested,
                    "active": active,
                    "wire_value": status.get("wire_value"),
                },
            )
            last_reasoning_status = (active, str(status.get("wire_value") or ""))

    turn = 0
    if hooks_enabled:
        prompt_text = ""
        for message in reversed(messages):
            if message.get("role") == "user":
                content = message.get("content")
                if isinstance(content, str):
                    prompt_text = content
                elif isinstance(content, list):
                    prompt_text = "\n".join(
                        str(part.get("text", "")) for part in content if isinstance(part, dict)
                    )
                break
        outcome = run_hook("UserPromptSubmit", {
            "event": "UserPromptSubmit",
            "prompt": redact_text(prompt_text[:8000])[0],
        })
        if outcome is not None and outcome.denied:
            reason = outcome.denial_reason()
            result.error = "UserPromptSubmit hook 拒绝了本次任务"
            result.answer = f"任务未开始：被 UserPromptSubmit hook 阻止。{reason}"[:2000]
            emit_trace(
                result.error,
                phase="failed",
                status="error",
                code="hook_blocked_user_prompt",
                detail={"reason": reason[:500]},
            )
            result.metrics = {
                "turns": 0,
                "tool_calls": 0,
                "trace_events": len(result.trace_events),
                "tokens": dict(result.tokens_used),
                "budget": runtime_budget.snapshot(),
            }
            return result
    while max_turns is None or turn < max_turns:
        turn += 1
        result.turns = turn
        try:
            runtime_budget.record_turn()
        except BudgetExceeded as exc:
            result.error = f"Agent 预算超限: {exc}"
            result.answer = f"任务未完成：{result.error}"
            emit_trace(result.error, phase="failed", status="error", code="budget_exceeded")
            break
        if runtime_budget.soft_limit_hit():
            if not soft_wrap_issued:
                soft_wrap_issued = True
                messages.append({
                    "role": "user",
                    "content": (
                        "[执行器提示] 已达到可选软预算上限。请立即给出当前结论、"
                        "已完成工作和未完成项的摘要，不要再调用工具。"
                    ),
                })
                emit_trace(
                    "已达到软预算，要求模型先收束再停止",
                    phase="planning",
                    code="soft_budget_wrap_up",
                    detail={
                        "tokens": runtime_budget.tokens,
                        "elapsed_seconds": round(runtime_budget.elapsed_seconds(), 3),
                        "soft_max_tokens": runtime_budget.soft_max_tokens,
                        "soft_max_duration_seconds": runtime_budget.soft_max_duration_seconds,
                    },
                )
            else:
                result.answer = (
                    ("".join(streamed_text).strip() if streamed_text else "")
                    or result.answer
                    or "已达到软预算上限，任务已收束。"
                )
                emit_trace(
                    "软预算收束轮次后仍超限，已停止",
                    phase="summarize",
                    code="soft_budget_stopped",
                    detail={
                        "tokens": runtime_budget.tokens,
                        "elapsed_seconds": round(runtime_budget.elapsed_seconds(), 3),
                    },
                )
                break
        if cancellation_requested():
            result.cancelled = True
            result.error = "任务已取消"
            result.answer = "任务已取消。"
            break

        # Possibly compact before the (expensive) API call.
        before_chars = message_chars(messages)
        compacted, checkpoint = compact_with_checkpoint(messages, threshold=compact_threshold)
        if compacted is not messages:
            # Keep the caller's list object usable for the next interactive
            # turn while replacing its contents with the compacted history.
            messages[:] = compacted
            compaction = {
                "before_chars": before_chars,
                "after_chars": message_chars(messages),
                "estimated_before_tokens": max(0, before_chars // 4),
                "estimated_after_tokens": estimate_tokens(messages),
                "turn": turn,
                "checkpoint": checkpoint,
            }
            result.compaction_events = [*result.compaction_events, compaction][-MAX_RESULT_COMPACTION_ENTRIES:]
            if runtime_state is not None:
                runtime_state.set_context_checkpoint(checkpoint)
            if on_compaction is not None:
                on_compaction(compaction)
            emit_trace(
                f"上下文接近上限，已压缩 {compaction['estimated_before_tokens']} → {compaction['estimated_after_tokens']} tokens",
                phase="planning",
                code="context_compacted",
            )

        restored_count = _restore_vision_context(messages, persistent_vision_context)
        if restored_count:
            restored_vision_contexts += restored_count
            emit_trace(
                f"已从持久附件恢复 {restored_count} 张图片，继续进行视觉上下文验收",
                phase="planning",
                code="vision_context_restored",
                detail={"count": restored_count, "source": "persistent_task_attachment"},
            )

        result.context = {
            "chars": message_chars(messages),
            "tokens": estimate_tokens(messages),
            "limit_tokens": max(1, int(context_limit_tokens)),
            "ratio": round(estimate_tokens(messages) / max(1, int(context_limit_tokens)), 4),
            "compacted": bool(result.compaction_events),
            "vision_context_count": len(persistent_vision_context),
            "vision_context_restored": restored_vision_contexts,
        }
        if on_context is not None:
            on_context(dict(result.context))

        try:
            if turn > 1:
                observed = [
                    str(item.get("observation") or item.get("summary") or "")
                    for item in last_round_feedback
                    if str(item.get("observation") or item.get("summary") or "").strip()
                ][:8]
                constraints = _replan_constraints(
                    verification_required=verification_required,
                    feedback=last_round_feedback,
                )
                emit_trace(
                    "已收到工具结果，正在判断下一步并保持任务目标",
                    phase="planning",
                    code="replan",
                    detail={
                        "turn": turn,
                        "previous_turn": turn - 1,
                        "context_tokens": result.context.get("tokens", 0),
                        "trigger": last_replan_trigger,
                        "observed": observed,
                        "constraints": constraints,
                        "basis": "上一轮工具的状态、受控观察和结构化证据；结合原始任务目标与当前运行时约束",
                        "next_action": "由模型基于上述公开证据重新选择读取、修改、验证或交付动作",
                    },
                )
            response = await chat_with_cancellation(
                provider,
                messages=messages,
                tools=tools_schemas,
                on_delta=emit_stream if on_stream is not None else None,
                cancel_event=cancel_event,
                timeout_seconds=runtime_budget.remaining_seconds(),
            )
            protocol_repairs = 0
        except AgentCancelled:
            result.cancelled = True
            result.error = "任务已取消"
            result.answer = "任务已取消。"
            emit_trace("任务已取消，已中止模型请求", phase="cancelled", code="cancelled")
            break
        except EnvelopeParseError as exc:
            if protocol_repairs < PROTOCOL_REPAIR_LIMIT:
                protocol_repairs += 1
                messages.append(assistant_msg(content=exc.content or None))
                messages.append({
                    "role": "user",
                    "content": (
                        "[执行器协议纠错] 上一条输出没有形成可执行的工具调用。"
                        "请立即修正并重新选择动作：工具调用必须是单个合法 JSON 对象，"
                        '格式为 {"action":"工具名","params":{...}}；也可以直接使用原生工具调用。'
                        "不要重复输出损坏的 JSON，不要夹带 markdown 或说明文字。"
                    ),
                })
                emit_trace(
                    "模型工具协议无效，已请求模型修正并重试",
                    phase="planning",
                    status="error",
                    code="protocol_repair",
                    detail={
                        "attempt": protocol_repairs,
                        "limit": PROTOCOL_REPAIR_LIMIT,
                        "error_type": type(exc).__name__,
                    },
                )
                last_replan_trigger = "上一轮模型工具协议无效，需要先修正输出格式"
                continue
            result.error = f"LLM 工具协议连续无效: {exc}"
            result.answer = f"任务未完成：{result.error}"
            emit_trace(
                result.error,
                phase="failed",
                status="error",
                code="protocol_guard",
                detail={"retry_limit": PROTOCOL_REPAIR_LIMIT, "error_type": type(exc).__name__},
            )
            break
        except BudgetExceeded as exc:
            result.error = f"Agent 预算超限: {exc}"
            result.answer = f"任务未完成：{result.error}"
            emit_trace(result.error, phase="failed", status="error", code="budget_exceeded")
            break
        except Exception as exc:
            emit_trace(
                "模型流中断，已保留当前输出并记录可恢复错误",
                phase="failed",
                status="error",
                code="provider_stream_error",
                detail={"error_type": type(exc).__name__, "partial_chars": len("".join(streamed_text))},
            )
            result.error = f"LLM 调用失败: {exc}"
            partial = "".join(streamed_text).strip()
            result.answer = f"{partial}\n\n[错误] {result.error}" if partial else f"\n[错误] {result.error}"
            break

        if callable(reasoning_status_fn):
            status = dict(reasoning_status_fn())
            current_reasoning_status = (str(status.get("active") or ""), str(status.get("wire_value") or ""))
            if last_reasoning_status is not None and current_reasoning_status != last_reasoning_status:
                emit_trace(
                    "当前网关不接受请求的推理参数，已自动降级并继续执行",
                    phase="planning",
                    status="error",
                    code="reasoning_fallback",
                    detail={
                        "requested": status.get("requested"),
                        "active": current_reasoning_status[0],
                    },
                )
            last_reasoning_status = current_reasoning_status

        if cancellation_requested():
            result.cancelled = True
            result.error = "任务已取消"
            result.answer = "任务已取消。"
            break

        # Accumulate provider usage, estimating only when a gateway omits it.
        usage = dict(response.usage or {})
        if not usage.get("total_tokens"):
            prompt_tokens = max(estimate_tokens(messages), 1)
            completion_text = response.content or response.reasoning_content or ""
            completion_tokens = max(len(completion_text) // 4, 1)
            usage.update({
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
                "estimated": True,
            })
        result.usage_by_turn = [*result.usage_by_turn, dict(usage)][-MAX_RESULT_USAGE_ENTRIES:]
        add_usage_totals(result.tokens_used, usage)
        if on_usage is not None:
            on_usage(dict(usage))
        try:
            runtime_budget.record_usage(usage)
        except BudgetExceeded as exc:
            result.error = f"Agent 预算超限: {exc}"
            result.answer = f"任务未完成：{result.error}"
            emit_trace(result.error, phase="failed", status="error", code="budget_exceeded")
            break

        # --- tool calls? execute and loop ---
        if response.tool_calls:
            try:
                runtime_budget.record_tool_call(len(response.tool_calls))
            except BudgetExceeded as exc:
                result.error = f"Agent 预算超限: {exc}"
                result.answer = f"任务未完成：{result.error}"
                emit_trace(result.error, phase="failed", status="error", code="budget_exceeded")
                break
            tool_names = [str((call.get("function") or {}).get("name") or call.get("name") or "tool") for call in response.tool_calls]
            last_public_model_update, visible_update = _visible_model_delta(
                last_public_model_update,
                response.content,
            )
            if visible_update:
                emit_trace(
                    "模型给出了本轮可公开的行动说明，随后执行工具调用",
                    phase="planning",
                    code="model_update",
                    detail={"turn": turn, "text": visible_update},
                )
            emit_trace(
                f"模型已完成本轮判断，正在执行可审计计划：{', '.join(tool_names)}",
                phase="planning",
                code="model_decision",
                detail={
                    "turn": turn,
                    "tool_count": len(tool_names),
                    "tools": tool_names,
                    "basis": "当前任务目标、已记录工具结果和运行时约束",
                    "public_plan": visible_update or "模型未提供额外的公开行动说明",
                },
            )
            emit_trace(
                f"已生成执行计划，本轮准备调用 {len(response.tool_calls)} 个工具：{', '.join(tool_names)}",
                phase="tool",
                code="tool_round_started",
                detail={"turn": turn, "tool_count": len(tool_names), "tools": tool_names},
            )
            messages.append(assistant_msg(
                content=response.content or "",
                tool_calls=response.tool_calls,
            ))
            pending_readonly: list[tuple[int, dict[str, Any], ToolCall]] = []
            pending_writes: list[tuple[int, ToolCall, str]] = []
            serial_writes: list[tuple[int, ToolCall]] = []
            immediate_results: dict[int, tuple[ToolCall, ToolResult]] = {}
            batch_signatures: dict[str, int] = {}
            for index, raw_tc in enumerate(response.tool_calls):
                if cancellation_requested():
                    result.cancelled = True
                    result.error = "任务已取消"
                    result.answer = "任务已取消。"
                    break
                tc = ToolCall.from_openai(raw_tc)
                result.tool_calls_total += 1
                call_signature = _signature({"tool": tc.tool, "arguments": tc.arguments})

                # Permission gate.
                risk = registry.risk_of(tc.tool)
                if call_signature in batch_signatures:
                    immediate_results[index] = (
                        tc,
                        ToolResult(
                            status="error",
                            summary="[DUPLICATE_TOOL_CALL] 本轮重复调用已跳过",
                            output=(
                                f"工具 {tc.tool} 与本轮第 {batch_signatures[call_signature] + 1} 个调用完全相同。"
                                "请合并重复调用，或改用能够产生新证据的工具和参数。"
                            ),
                            data={"duplicate": True, "duplicate_of": batch_signatures[call_signature]},
                            security_tags=["untrusted", "runtime_guard"],
                        ),
                    )
                    continue
                batch_signatures[call_signature] = index

                # After a recovery trigger, prevent another speculative write
                # until the model has seen fresh workspace evidence.
                if recovery_inspection_required and risk == "write":
                    immediate_results[index] = (
                        tc,
                        ToolResult(
                            status="error",
                            summary="[RECOVERY_GUARD] 已暂缓写入，必须先完成只读状态检查",
                            output=(
                                "当前执行器正在从重复/无效路径恢复。请先使用 read_file、git_status、"
                                "git_diff、grep 或 tree 获取新证据；确认目标和当前 diff 后再修改。"
                            ),
                            data={"guard": "recovery_inspection_required"},
                            security_tags=["untrusted", "runtime_guard"],
                        ),
                    )
                    continue

                if tool_requires_authorization(
                    tc.tool, risk, registry.capabilities_of(tc.tool)
                ) and not allow(tc.tool, tc):
                    result.denied_tools.append(tc.tool)
                    denied = ToolResult(
                        status="denied",
                        summary=f"[DENIED] 用户拒绝了此操作 ({tc.tool})",
                        security_tags=["untrusted"],
                    )
                    immediate_results[index] = (tc, denied)
                    continue
                if hooks_enabled:
                    hook_outcome = run_hook(
                        "PreToolUse",
                        payloads_for_tool_call("PreToolUse", tc.tool, tc.arguments, risk=risk),
                    )
                    # A hook may only *deny*; it can never widen what the
                    # permission model already decided (M7-T1 contract).
                    if hook_outcome is not None and hook_outcome.denied:
                        result.denied_tools.append(tc.tool)
                        immediate_results[index] = (
                            tc,
                            ToolResult(
                                status="denied",
                                summary=f"[HOOK_DENIED] PreToolUse hook 拒绝了此操作 ({tc.tool})",
                                output=hook_outcome.denial_reason()[:2000],
                                data={"hook": "PreToolUse"},
                                security_tags=["untrusted"],
                            ),
                        )
                        continue
                if risk == "readonly":
                    if tc.tool in NETWORK_TOOL_NAMES and search_failures >= SEARCH_FAILURE_LIMIT:
                        immediate_results[index] = (
                            tc,
                            ToolResult(
                                status="error",
                                summary="联网工具熔断：连续失败后已停止重复请求",
                                output="请改换更具体的关键词，或基于已经取得的项目证据继续；不要重复相同的联网请求。",
                                data={"circuit_open": True, "failures": search_failures},
                                security_tags=["untrusted", "network"],
                            ),
                        )
                    elif tc.tool not in NETWORK_TOOL_NAMES and call_signature in tool_result_cache:
                        cached = deepcopy(tool_result_cache[call_signature])
                        cached.summary = (
                            f"[DUPLICATE_TOOL_CALL] 已复用 {tc.tool} 的最近一次成功结果；"
                            "不要重复调用相同参数，请基于已有证据继续。"
                        )
                        cached.data = {
                            **(cached.data if isinstance(cached.data, dict) else {}),
                            "cached": True,
                            "duplicate": True,
                        }
                        immediate_results[index] = (tc, cached)
                    else:
                        pending_readonly.append((index, raw_tc, tc))
                else:
                    write_key = _parallel_write_key(tc.tool, tc.arguments)
                    if write_key is not None:
                        pending_writes.append((index, tc, write_key))
                    else:
                        serial_writes.append((index, tc))
            if result.cancelled:
                break

            # Write phase: independent paths fan out, same-path writes stay
            # ordered, and the whole phase precedes the read-only gather so
            # inspections still observe freshly written files.
            await _run_write_phase(
                registry=registry,
                pending_writes=pending_writes,
                serial_writes=serial_writes,
                immediate_results=immediate_results,
                cancel_event=cancel_event,
            )

            # Independent inspection calls do not need to serialize. This is
            # the executor part of the runtime and keeps broad repo scans fast.
            if pending_readonly:
                readonly_results = await asyncio.gather(
                    *(
                        asyncio.to_thread(
                            registry.execute,
                            tc,
                            cancel_event=cancel_event,
                        )
                        for _, _, tc in pending_readonly
                    )
                )
                for (index, _raw_tc, tc), tool_result in zip(pending_readonly, readonly_results):
                    immediate_results[index] = (tc, tool_result)

            if cancellation_requested():
                result.cancelled = True
                result.error = "任务已取消"
                result.answer = "任务已取消。"
                break

            for index, raw_tc in enumerate(response.tool_calls):
                item = immediate_results.get(index)
                if item is None:
                    continue
                tc, tool_result = item
                if (
                    registry.risk_of(tc.tool) == "readonly"
                    and tc.tool not in NETWORK_TOOL_NAMES
                    and tool_result.status == "ok"
                    and not (tool_result.data or {}).get("duplicate")
                ):
                    cache_tool_result(_signature({"tool": tc.tool, "arguments": tc.arguments}), tool_result)
                if on_tool is not None:
                    on_tool(tc, tool_result)
                if (
                    hooks_enabled
                    and tool_result.status != "denied"
                    and not (tool_result.data or {}).get("duplicate")
                    and not (tool_result.data or {}).get("cached")
                ):
                    run_hook(
                        "PostToolUse",
                        {
                            **payloads_for_tool_call(
                                "PostToolUse", tc.tool, tc.arguments,
                                risk=registry.risk_of(tc.tool),
                            ),
                            "result": payloads_for_result(tool_result),
                        },
                    )
                messages.append(tool_result_msg(
                    raw_tc.get("id", ""),
                    tool_result.render(),
                ))

            round_feedback = [
                build_tool_feedback(
                    call,
                    tool_result,
                    risk=registry.risk_of(call.tool),
                )
                for call, tool_result in (
                    immediate_results[index]
                    for index in sorted(immediate_results)
                )
            ]

            for _index in sorted(immediate_results):
                search_call, search_result = immediate_results[_index]
                if search_call.tool not in NETWORK_TOOL_NAMES:
                    continue
                if search_result.status == "error":
                    search_failures += 1
                    if search_failures == SEARCH_FAILURE_LIMIT:
                        emit_trace(
                            "联网工具连续失败，已打开熔断；后续将改换策略而不是原地重试",
                            phase="planning",
                            status="error",
                            code="search_circuit_open",
                        )
                elif search_result.status == "ok":
                    search_failures = 0

            successful_writes = any(
                is_workspace_write(call.tool, call.arguments, tool_result.status)
                for call, tool_result in immediate_results.values()
            )
            successful_verification = any(
                is_verification_evidence(call.tool, call.arguments, tool_result.status)
                for call, tool_result in immediate_results.values()
            )
            recovery_inspection_observed = any(
                registry.risk_of(call.tool) == "readonly"
                and tool_result.status == "ok"
                and not (tool_result.data or {}).get("duplicate")
                for call, tool_result in immediate_results.values()
            )
            if recovery_inspection_required and recovery_inspection_observed:
                recovery_inspection_required = False
                recovery_refusals = 0
                emit_trace(
                    "恢复阶段已取得新的只读证据，解除临时写入保护",
                    phase="planning",
                    code="recovery_inspection_passed",
                    detail={
                        "turn": turn,
                        "tools": [
                            call.tool
                            for call, tool_result in immediate_results.values()
                            if registry.risk_of(call.tool) == "readonly"
                            and tool_result.status == "ok"
                            and not (tool_result.data or {}).get("duplicate")
                        ],
                    },
                )
            if successful_writes:
                # Any cached read may now be stale, including a path the
                # model did not explicitly mention in the same response.
                # A write therefore starts the next evidence phase clean.
                tool_result_cache.clear()
                verification_required = True
                verification_retries = 0
                emit_trace(
                    "检测到工作区已修改，下一轮将检查 diff 并运行针对性验证",
                    phase="planning",
                    code="verification_required",
                    detail={
                        "turn": turn,
                        "writes": [
                            call.tool
                            for call, tool_result in immediate_results.values()
                            if is_workspace_write(call.tool, call.arguments, tool_result.status)
                        ],
                    },
                )
                messages.append({
                    "role": "user",
                    "content": POST_WRITE_VERIFICATION_NUDGE,
                })
            elif verification_required and successful_verification:
                verification_required = False
                verification_retries = 0
                emit_trace(
                    "已收到修改后的验证证据，继续评估是否满足原始目标",
                    phase="planning",
                    code="verification_observed",
                    detail={
                        "turn": turn,
                        "tools": [
                            call.tool
                            for call, tool_result in immediate_results.values()
                            if is_verification_evidence(call.tool, call.arguments, tool_result.status)
                        ],
                    },
                )

            round_signature = _signature([
                {
                    "tool": item[0].tool,
                    "arguments": item[0].arguments,
                }
                for item in (immediate_results[index] for index in sorted(immediate_results))
            ])
            # The call plan itself is the strongest stagnation signal.  A
            # changing timestamp or nondeterministic output must not disguise
            # an unchanged tool path as progress.
            if round_signature == last_round_signature:
                repeated_rounds += 1
            else:
                repeated_rounds = 0
            last_round_signature = round_signature

            round_unproductive = bool(immediate_results) and all(
                _is_unproductive_result(tool_result)
                for _call, tool_result in immediate_results.values()
            )
            unproductive_rounds = unproductive_rounds + 1 if round_unproductive else 0
            recent_observations.extend(
                _signature({
                    "tool": call.tool,
                    "arguments": call.arguments,
                    "status": tool_result.status,
                    "summary": tool_result.summary,
                    "data": tool_result.data,
                })
                for call, tool_result in (immediate_results[index] for index in sorted(immediate_results))
            )
            recent_observations = recent_observations[-(STAGNATION_CYCLE_LENGTH * 2):]
            repeated_cycle = (
                len(recent_observations) >= STAGNATION_CYCLE_LENGTH * 2
                and recent_observations[-STAGNATION_CYCLE_LENGTH:]
                == recent_observations[-STAGNATION_CYCLE_LENGTH * 2:-STAGNATION_CYCLE_LENGTH]
            )
            last_round_feedback = round_feedback
            failed_tools = [
                str(item.get("tool") or "tool")
                for item in round_feedback
                if str(item.get("status") or "") in {"error", "failed", "denied", "timed_out"}
            ]
            feedback_constraints = _replan_constraints(
                verification_required=verification_required,
                feedback=round_feedback,
            )
            new_information = [
                f"{item.get('tool')}: {item.get('observation')}"
                for item in round_feedback
                if str(item.get("observation") or "").strip()
            ][:8]
            if failed_tools:
                last_replan_trigger = "上一轮工具失败或被阻止，需要处理错误"
            elif verification_required:
                last_replan_trigger = "上一轮修改了工作区，需要先完成验证"
            elif round_unproductive:
                last_replan_trigger = "上一轮没有产生新信息，需要换路检查"
            else:
                last_replan_trigger = "上一轮工具结果已合并"
            next_action = (
                "先检查修改后的 diff 并运行直接相关验证"
                if verification_required
                else "根据新观察继续定位、修复、验证或结束任务"
            )
            emit_trace(
                "工具结果已合并，继续检查是否需要修复或验证",
                phase="planning",
                status="error" if failed_tools else "ok",
                code="tool_round_finished",
                detail={
                    "turn": turn,
                    "tool_count": len(immediate_results),
                    "statuses": [
                        f"{call.tool}:{tool_result.status}"
                        for call, tool_result in (
                            immediate_results[index]
                            for index in sorted(immediate_results)
                        )
                    ],
                    "results": round_feedback,
                    "new_information": new_information,
                    "failed_tools": failed_tools,
                    "needs_repair": bool(failed_tools),
                    "verification_required": verification_required,
                    "basis": "工具状态、受控输出、结构化结果以及修改/验证状态",
                    "next_action": next_action,
                },
            )
            emit_trace(
                "自反馈已记录：观察结果已转成下一步约束",
                phase="planning",
                status="error" if round_unproductive or failed_tools else "ok",
                code="feedback_observed",
                detail={
                    "turn": turn,
                    "assessment": "本轮产生了新信息" if not round_unproductive else "本轮未产生新信息",
                    "observations": new_information,
                    "constraints": feedback_constraints,
                    "basis": "将本轮工具反馈压缩为观察、失败项和必须遵守的运行时约束",
                    "next_action": next_action,
                    "replan_trigger": last_replan_trigger,
                },
            )
            if repeated_rounds >= STAGNATION_REPEAT_LIMIT or unproductive_rounds >= STAGNATION_REPEAT_LIMIT or repeated_cycle:
                if stagnation_replans < STAGNATION_REPLAN_LIMIT:
                    stagnation_replans += 1
                    repeated_rounds = 0
                    unproductive_rounds = 0
                    recent_observations.clear()
                    recovery_inspection_required = True
                    probe_feedback = await run_recovery_probe(stagnation_replans)
                    if result.error:
                        break
                    messages.append({
                        "role": "user",
                        "content": (
                            f"[执行器恢复第 {stagnation_replans} 次] 最近几轮工具调用没有产生新信息，"
                            "当前路径可能判断错误。请回到最近一次有证据的状态，先核对恢复诊断和当前 diff，"
                            "再重新选择不同的工具、路径或参数；不要重复刚才的调用。"
                            "如果之前的修改造成偏差，只修复本任务产生的改动，不要覆盖用户已有改动。"
                            + (
                                "恢复诊断已经提供了新证据，可以基于它继续。"
                                if probe_feedback
                                else "恢复诊断工具不可用，下一轮必须先用现有只读工具取得证据。"
                            )
                        ),
                    })
                    emit_trace(
                        "检测到重复或无效工具结果，已触发恢复诊断和重新规划",
                        phase="planning",
                        code="stagnation_replan",
                        detail={
                            "attempt": stagnation_replans,
                            "limit": STAGNATION_REPLAN_LIMIT,
                            "recovery_guard": recovery_inspection_required,
                            "probe_tools": [item.get("tool") for item in probe_feedback],
                        },
                    )
                    continue
                result.error = "Agent 停滞保护触发：恢复诊断后仍连续重复工具调用"
                result.answer = (
                    "任务未完成：连续工具调用没有产生新信息。执行器已经完成多次状态诊断和重新规划，"
                    "为避免无限循环暂时停止，且没有自动覆盖或回滚用户已有改动。"
                )
                emit_trace(
                    result.error,
                    phase="failed",
                    status="error",
                    code="stagnation_guard",
                )
                break
            continue

        # --- plain text answer ---
        finish_reason = str(getattr(response, "finish_reason", "stop") or "stop")
        if finish_reason not in TERMINAL_FINISH_REASONS:
            # A failed/truncated/refused turn must never masquerade as a
            # delivered answer (M1-T4).
            if nonterminal_repairs < STAGNATION_REPLAN_LIMIT:
                nonterminal_repairs += 1
                emit_trace(
                    f"模型轮次非正常结束（finish_reason={finish_reason}），不作为最终答案，要求重新作答",
                    phase="planning",
                    status="error",
                    code="nonterminal_turn",
                    detail={"turn": turn, "finish_reason": finish_reason, "attempt": nonterminal_repairs},
                )
                messages.append({
                    "role": "user",
                    "content": (
                        f"[执行器保护] 上一轮模型以 {finish_reason} 结束，不是正常完成，之前的输出不作为结果。"
                        "请基于现有证据重新给出完整的最终回答，或继续必要的工具调用。"
                    ),
                })
                continue
            result.error = f"模型连续以非正常 finish_reason 结束（{finish_reason}），任务未完成"
            result.answer = f"任务未完成：{result.error}"
            emit_trace(
                result.error,
                phase="failed",
                status="error",
                code="nonterminal_turn_limit",
                detail={"finish_reason": finish_reason, "retry_limit": STAGNATION_REPLAN_LIMIT},
            )
            break
        text = response.text.strip()
        if not text and response.reasoning_content:
            text = response.reasoning_content.strip()

        if recovery_inspection_required:
            if recovery_refusals < STAGNATION_REPLAN_LIMIT:
                recovery_refusals += 1
                messages.append(assistant_msg(content=text or None))
                messages.append({
                    "role": "user",
                    "content": (
                        "[执行器恢复保护] 当前仍在错误路径恢复阶段，不能先结束或继续写入。"
                        "请先使用只读工具核对当前工作区、相关文件和 diff，取得新的事实后再决定下一步。"
                    ),
                })
                emit_trace(
                    "模型尝试在恢复诊断完成前结束，已要求先取得只读证据",
                    phase="planning",
                    status="error",
                    code="recovery_required_before_finish",
                    detail={"turn": turn, "attempt": recovery_refusals},
                )
                continue
            result.error = "Agent 在错误路径恢复阶段没有取得新的工作区证据"
            result.answer = f"任务未完成：{result.error}"
            emit_trace(
                result.error,
                phase="failed",
                status="error",
                code="recovery_guard",
                detail={"turn": turn, "retry_limit": STAGNATION_REPLAN_LIMIT},
            )
            break

        if runtime_budget.soft_limit_hit() and not soft_wrap_issued:
            messages.append(assistant_msg(content=text or None))
            continue
        if runtime_budget.soft_limit_hit() and soft_wrap_issued:
            if not text:
                result.error = "软预算收束后模型返回空答案，没有可交付内容"
                result.answer = f"任务未完成：{result.error}"
                emit_trace(
                    result.error,
                    phase="failed",
                    status="error",
                    code="empty_answer",
                    detail={"turn": turn, "tokens": runtime_budget.tokens},
                )
                messages.append(assistant_msg(content=result.answer))
                break
            result.answer = text
            messages.append(assistant_msg(content=result.answer))
            emit_trace(
                "软预算收束轮次后仍超限，已停止",
                phase="summarize",
                code="soft_budget_stopped",
                detail={
                    "tokens": runtime_budget.tokens,
                    "elapsed_seconds": round(runtime_budget.elapsed_seconds(), 3),
                },
            )
            break

        if verification_required:
            if verification_retries < VERIFICATION_RETRY_LIMIT:
                verification_retries += 1
                messages.append(assistant_msg(content=text or None))
                messages.append({
                    "role": "user",
                    "content": PRE_FINISH_VERIFICATION_NUDGE,
                })
                emit_trace(
                    "模型尝试提前结束，已要求先完成修改后的验证",
                    phase="planning",
                    status="error",
                    code="verification_required_before_finish",
                    detail={"turn": turn, "retry": verification_retries},
                )
                continue
            result.error = "Agent 在修改工作区后没有完成验证"
            result.answer = (
                "任务未完成：修改工作区后没有完成验证，已停止提前交付。"
                + (f"\n\n模型最后输出：{text}" if text else "")
            )
            emit_trace(
                result.error,
                phase="failed",
                status="error",
                code="verification_guard",
                detail={"turn": turn, "retry_limit": VERIFICATION_RETRY_LIMIT},
            )
            break

        if not text:
            result.error = "模型以空答案结束本轮，没有可交付内容"
            result.answer = f"任务未完成：{result.error}"
            emit_trace(
                result.error,
                phase="failed",
                status="error",
                code="empty_answer",
                detail={"turn": turn, "finish_reason": finish_reason},
            )
            messages.append(assistant_msg(content=result.answer))
            break

        result.answer = text
        messages.append(assistant_msg(content=result.answer))
        emit_trace(
            "执行结束，待验收",
            phase="review",
            code="run_finished",
            detail={
                "turn": turn,
                "answer_chars": len(result.answer),
                "tool_count": result.tool_calls_total,
                "compactions": len(result.compaction_events),
            },
        )
        break
    else:
        result.error = f"Agent 达到最大执行轮次 {max_turns}，任务未完成"
        result.answer = f"任务未完成：{result.error}"
        emit_trace("已达到最大执行轮次，停止继续调用工具", phase="failed", status="error", code="max_turns")

    result.metrics = {
        "turns": result.turns,
        "tool_calls": result.tool_calls_total,
        "trace_events": len(result.trace_events),
        "tokens": dict(result.tokens_used),
        "budget": runtime_budget.snapshot(),
    }
    if hooks_enabled:
        run_hook("Stop", {
            "event": "Stop",
            "answer": redact_text((result.answer or "")[:4000])[0],
            "error": result.error or "",
            "metrics": dict(result.metrics),
        })
    result.metrics.update(cache_summary(result.tokens_used))
    if runtime_state is not None:
        runtime_state.outputs["answer"] = result.answer
        runtime_state.outputs["error"] = result.error
        result.metrics.update(runtime_state.metrics())
    return result


def _always_allow(name: str, call: ToolCall) -> bool:
    return True


def _signature(value: Any) -> str:
    """Stable, compact fingerprint for loop-progress detection."""
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _is_unproductive_result(result: ToolResult) -> bool:
    """Identify tool feedback that should not be repeated indefinitely."""
    if result.status in {"error", "denied", "cancelled", "timed_out"}:
        return True
    text = f"{result.summary}\n{result.head}\n{result.tail}".lower()
    return any(marker in text for marker in (
        "无匹配",
        "命中 0",
        "扫描 0 文件",
        "窗口为空",
        "窗口越界",
        "duplicate_tool_call",
        "重复调用",
        "recovery_guard",
    ))


# M6-T3: parallel write phase -------------------------------------------------

PARALLEL_SAFE_WRITE_TOOLS = {"write_file", "edit_file"}


def _parallel_write_key(tool: str, arguments: Any) -> str | None:
    """Serialization key for a write tool call, or None if it must stay serial.

    Only path-scoped file writes qualify: the key is the target path alone, so
    a write and an edit on the same file share one ordered group while
    different paths run concurrently. bash/todo_write/worktree/MCP tools return
    None and join the deterministic serial group.
    """
    if tool not in PARALLEL_SAFE_WRITE_TOOLS or not isinstance(arguments, dict):
        return None
    path = str(arguments.get("path") or "").strip()
    if not path:
        return None
    return f"write:{path}"


async def _execute_and_store(
    registry: ToolRegistry,
    index: int,
    tc: ToolCall,
    immediate_results: dict[int, tuple[ToolCall, ToolResult]],
    cancel_event: threading.Event | None,
) -> None:
    try:
        tool_result = await asyncio.to_thread(registry.execute, tc, cancel_event=cancel_event)
    except Exception as exc:  # a failing sibling must not lose the other results
        tool_result = ToolResult(
            status="error",
            summary=f"[TOOL_ERROR] {tc.tool} 执行异常: {exc}",
            output=str(exc),
            security_tags=["untrusted"],
        )
    immediate_results[index] = (tc, tool_result)


async def _run_serial_group(
    registry: ToolRegistry,
    group: list[tuple[int, ToolCall]],
    immediate_results: dict[int, tuple[ToolCall, ToolResult]],
    cancel_event: threading.Event | None,
) -> None:
    for index, tc in sorted(group, key=lambda item: item[0]):
        await _execute_and_store(registry, index, tc, immediate_results, cancel_event)


async def _run_write_phase(
    *,
    registry: ToolRegistry,
    pending_writes: list[tuple[int, ToolCall, str]],
    serial_writes: list[tuple[int, ToolCall]],
    immediate_results: dict[int, tuple[ToolCall, ToolResult]],
    cancel_event: threading.Event | None,
) -> None:
    """Run the non-readonly part of one tool round.

    Groups keyed by target path execute concurrently; inside a group calls run
    in index order so a second edit observes the first. All other non-readonly
    tools form a single deterministic serial group.
    """
    if not pending_writes and not serial_writes:
        return
    groups: dict[str, list[tuple[int, ToolCall]]] = {}
    for index, tc, key in pending_writes:
        groups.setdefault(key, []).append((index, tc))
    if serial_writes:
        groups.setdefault("_serial", []).extend(serial_writes)
    await asyncio.gather(
        *(
            _run_serial_group(registry, group, immediate_results, cancel_event)
            for group in groups.values()
        )
    )
