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
7. An optional *max_turns* cap can bound a run; by default the loop continues
   until the model returns an answer or another runtime guard stops it.

Permission: the *should_allow* callback is consulted before every
write/exec tool call. It receives the tool name and parsed ToolCall;
returning False produces a 'denied' result.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from ..llm.base import LLMResponse, assistant_msg, tool_result_msg
from ..llm.openai_provider import OpenAICompatibleProvider
from ..tools.schemas import ToolCall, ToolResult
from ..tools.registry import ToolRegistry, redact_text
from .context import compact, estimate_tokens, message_chars
from .state import AgentState, Budget, BudgetExceeded


STAGNATION_REPLAN_LIMIT = 1
STAGNATION_REPEAT_LIMIT = 2
STAGNATION_CYCLE_LENGTH = 4
VERIFICATION_RETRY_LIMIT = 1
SEARCH_FAILURE_LIMIT = 2
MAX_VISIBLE_MODEL_UPDATE_CHARS = 1200
MAX_PUBLIC_TOOL_OBSERVATION_CHARS = 900
MAX_PUBLIC_TOOL_DATA_CHARS = 2400
WRITE_TOOL_NAMES = frozenset({"write_file", "edit_file", "worktree_create", "worktree_remove"})
VERIFY_TOOL_NAMES = frozenset({"bash", "git_diff", "git_status", "read_file", "grep"})


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
        "write": call.tool in WRITE_TOOL_NAMES and result.status == "ok",
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
    context_limit_tokens: int = 300_000,
    budget: Budget | None = None,
    runtime_state: AgentState | None = None,
) -> TurnResult:
    """Run the agent loop until a final text answer or an explicit max_turns cap.

    *messages* is mutated in place (tool calls/results are appended).
    The caller is responsible for injecting the initial system prompt
    and the first user message before calling this function.
    """
    if max_turns is not None and max_turns <= 0:
        max_turns = None
    result = TurnResult(answer="")
    allow = should_allow or _always_allow
    runtime_budget = budget or (runtime_state.budget if runtime_state is not None else Budget(max_turns=max_turns))
    if runtime_budget.max_turns is None:
        runtime_budget.max_turns = max_turns
    tools_schemas = registry.openai_schemas()
    streamed_text: list[str] = []
    last_round_signature = ""
    last_round_result_signature = ""
    repeated_rounds = 0
    unproductive_rounds = 0
    stagnation_replans = 0
    recent_observations: list[str] = []
    search_failures = 0
    last_reasoning_status: tuple[str, str] | None = None
    verification_required = False
    verification_retries = 0
    last_round_feedback: list[dict[str, Any]] = []
    last_replan_trigger = "初始任务上下文"

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
        if runtime_state is not None:
            runtime_state.add_trace(event)
        if on_trace is not None:
            on_trace(event)

    def emit_stream(delta: str) -> None:
        if delta:
            streamed_text.append(str(delta))
            if on_stream is not None:
                on_stream(str(delta))

    emit_trace(
        "正在界定任务范围，准备检查工作区",
        phase="planning",
        code="run_started",
        detail={
            "max_turns": max_turns,
            "turn_policy": "默认不限模型轮次；仅由取消、停滞、验证和资源保护结束",
            "tool_count": len(tools_schemas),
        },
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
                f"已启用{effort_label}推理预算；界面展示阶段摘要，不展示模型私有思维链",
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
        if should_cancel is not None and should_cancel():
            result.cancelled = True
            result.error = "任务已取消"
            result.answer = "任务已取消。"
            break

        # Possibly compact before the (expensive) API call.
        before_chars = message_chars(messages)
        compacted = compact(messages, threshold=compact_threshold)
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
            }
            result.compaction_events.append(compaction)
            if on_compaction is not None:
                on_compaction(compaction)
            emit_trace(
                f"上下文接近上限，已压缩 {compaction['estimated_before_tokens']} → {compaction['estimated_after_tokens']} tokens",
                phase="planning",
                code="context_compacted",
            )

        result.context = {
            "chars": message_chars(messages),
            "tokens": estimate_tokens(messages),
            "limit_tokens": max(1, int(context_limit_tokens)),
            "ratio": round(estimate_tokens(messages) / max(1, int(context_limit_tokens)), 4),
            "compacted": bool(result.compaction_events),
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
            response = await provider.chat(
                messages=messages,
                tools=tools_schemas,
                on_delta=emit_stream if on_stream is not None else None,
            )
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

        if should_cancel is not None and should_cancel():
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
        result.usage_by_turn.append(dict(usage))
        for key in ("prompt_tokens", "completion_tokens", "total_tokens", "reasoning_tokens"):
            value = usage.get(key, 0)
            if isinstance(value, (int, float)):
                result.tokens_used[key] = result.tokens_used.get(key, 0) + int(value)
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
            visible_update = _visible_model_update(response.content)
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
            immediate_results: dict[int, tuple[ToolCall, ToolResult]] = {}
            for index, raw_tc in enumerate(response.tool_calls):
                if should_cancel is not None and should_cancel():
                    result.cancelled = True
                    result.error = "任务已取消"
                    result.answer = "任务已取消。"
                    break
                tc = ToolCall.from_openai(raw_tc)
                result.tool_calls_total += 1

                # Permission gate.
                risk = registry.risk_of(tc.tool)
                if (risk in ("write", "exec") or tc.tool == "web_search") and not allow(tc.tool, tc):
                    result.denied_tools.append(tc.tool)
                    denied = ToolResult(
                        status="denied",
                        summary=f"[DENIED] 用户拒绝了此操作 ({tc.tool})",
                        security_tags=["untrusted"],
                    )
                    immediate_results[index] = (tc, denied)
                    continue
                if risk == "readonly":
                    if tc.tool == "web_search" and search_failures >= SEARCH_FAILURE_LIMIT:
                        immediate_results[index] = (
                            tc,
                            ToolResult(
                                status="error",
                                summary="联网搜索熔断：连续失败后已停止重复请求",
                                output="请改换更具体的关键词，或基于已经取得的项目证据继续；不要重复相同搜索。",
                                data={"circuit_open": True, "failures": search_failures},
                                security_tags=["untrusted", "network"],
                            ),
                        )
                    else:
                        pending_readonly.append((index, raw_tc, tc))
                else:
                    immediate_results[index] = (tc, registry.execute(tc))
            if result.cancelled:
                break

            # Independent inspection calls do not need to serialize. This is
            # the executor part of the runtime and keeps broad repo scans fast.
            if pending_readonly:
                readonly_results = await asyncio.gather(
                    *(asyncio.to_thread(registry.execute, tc) for _, _, tc in pending_readonly)
                )
                for (index, _raw_tc, tc), tool_result in zip(pending_readonly, readonly_results):
                    immediate_results[index] = (tc, tool_result)

            for index, raw_tc in enumerate(response.tool_calls):
                item = immediate_results.get(index)
                if item is None:
                    continue
                tc, tool_result = item
                if on_tool is not None:
                    on_tool(tc, tool_result)
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
                if search_call.tool != "web_search":
                    continue
                if search_result.status == "error":
                    search_failures += 1
                    if search_failures == SEARCH_FAILURE_LIMIT:
                        emit_trace(
                            "联网搜索连续失败，已打开熔断；后续将改换策略而不是原地重试",
                            phase="planning",
                            status="error",
                            code="search_circuit_open",
                        )
                else:
                    search_failures = 0

            successful_writes = any(
                call.tool in WRITE_TOOL_NAMES and tool_result.status == "ok"
                for call, tool_result in immediate_results.values()
            )
            successful_verification = any(
                call.tool in VERIFY_TOOL_NAMES and tool_result.status == "ok"
                for call, tool_result in immediate_results.values()
            )
            if successful_writes:
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
                            if call.tool in WRITE_TOOL_NAMES and tool_result.status == "ok"
                        ],
                    },
                )
                messages.append({
                    "role": "user",
                    "content": (
                        "[执行器提示] 本轮已经修改工作区。下一轮必须先检查相关 diff，"
                        "再运行最小且直接相关的测试或验证；如果验证失败，继续修复。"
                    ),
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
                            if call.tool in VERIFY_TOOL_NAMES and tool_result.status == "ok"
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
            round_result_signature = _signature([
                {
                    "tool": immediate_results[index][0].tool,
                    "status": immediate_results[index][1].status,
                    "summary": immediate_results[index][1].summary,
                    "data": immediate_results[index][1].data,
                }
                for index in sorted(immediate_results)
            ])
            if round_signature == last_round_signature and round_result_signature == last_round_result_signature:
                repeated_rounds += 1
            else:
                repeated_rounds = 0
            last_round_signature = round_signature
            last_round_result_signature = round_result_signature

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
                    messages.append({
                        "role": "user",
                        "content": (
                            "[执行器提示] 最近几轮工具调用没有产生新信息，可能陷入重复。"
                            "请重新检查任务目标，改用不同的路径、参数或实现方案；"
                            "不要重复刚才已经得到的结果。"
                        ),
                    })
                    emit_trace(
                        "检测到重复或无效工具结果，已触发一次重新规划",
                        phase="planning",
                        code="stagnation_replan",
                    )
                    continue
                result.error = "Agent 停滞保护触发：连续工具调用没有产生新信息"
                result.answer = (
                    "任务已暂停：连续几轮工具调用返回相同或无效结果，"
                    "为避免无限循环已停止。请缩小目标、提供明确文件路径，或重新运行任务。"
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
        text = response.text.strip()
        if not text and response.reasoning_content:
            text = response.reasoning_content.strip()

        if verification_required:
            if verification_retries < VERIFICATION_RETRY_LIMIT:
                verification_retries += 1
                messages.append(assistant_msg(content=text or None))
                messages.append({
                    "role": "user",
                    "content": (
                        "[执行器提示] 你已经修改了工作区，但还没有收到修改后的验证证据。"
                        "不能先结束任务；请先检查相关 diff，并运行最小且直接相关的测试或验证，"
                        "然后再总结结果。"
                    ),
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

        result.answer = text or "(模型返回空回复)"
        messages.append(assistant_msg(content=result.answer))
        emit_trace(
            "任务已完成，正在整理交付摘要和剩余风险",
            phase="completed",
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
    return any(marker in text for marker in ("无匹配", "命中 0", "扫描 0 文件", "窗口为空", "窗口越界"))
