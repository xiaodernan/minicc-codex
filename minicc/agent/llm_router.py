"""LLM-driven transition selection for StateGraph — an *opt-in* decision layer.

The graph's edges are the authority on **where a node may legally go**.  This
module never widens that set: given the outgoing edges of the current node it
asks the model to pick one and explain why, then validates the answer against
the same edge set before it is honored.  A hallucinated target, an unparsable
answer, a disabled flag or a provider error all fall back to the deterministic
``next_node(source, condition)`` choice — the route the runtime already used
before this module existed.  So enabling it can improve a decision, and can
never invent an illegal transition or break a graph that did not opt in.

Design constraints (from the operator's standing goals):

* **Deep, not shallow** — the model reasons over a compact but real snapshot
  of the run (phase, errors, node outputs, evidence), not a decorative call.
* **Token-frugal** — the snapshot is bounded and summarized; the decision is
  one short non-streaming call, and it is skipped entirely when there is only
  one legal successor (nothing to decide) or when no provider is supplied.
* **Fail-closed** — see above; every acceptance path re-checks membership in
  the legal target set, so a model cannot route outside the declared graph.
* **Observable** — every decision (accepted or rejected) returns a structured
  record so the UI/ledger can show *why* the run took a branch.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence

# Bounded snapshot budgets — keep the decision call small even on long runs.
_MAX_ERRORS = 6
_MAX_OUTPUTS = 6
_MAX_EVIDENCE = 4
_MAX_TEXT_CHARS = 600

#: The status the router uses when it has nothing to say.  Distinct from the
#: graph's node statuses on purpose — this is a routing provenance word.
ROUTE_SOURCE_STATIC = "static"
ROUTE_SOURCE_LLM = "llm"
ROUTE_SOURCE_FALLBACK = "fallback"


@dataclass(frozen=True)
class TransitionContext:
    """Compact, model-facing view of a run. Built from AgentState, never live state."""

    phase: str
    status: str
    errors: tuple[str, ...] = ()
    outputs: tuple[tuple[str, str], ...] = ()  # (node, short summary)
    evidence_count: int = 0
    objective: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "status": self.status,
            "errors": list(self.errors),
            "outputs": [{"node": n, "summary": s} for n, s in self.outputs],
            "evidence_count": self.evidence_count,
            "objective": self.objective,
        }


def _short(value: Any, limit: int = _MAX_TEXT_CHARS) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= limit:
        return text
    # Reserve one char for the ellipsis so the result never exceeds ``limit``.
    return text[: max(0, limit - 1)] + "…"


def build_context(state: Any, *, objective_chars: int = 240) -> TransitionContext:
    """Summarize an AgentState (duck-typed) into a bounded, JSON-safe context."""
    errors = tuple(_short(e, 200) for e in list(getattr(state, "errors", ()) or ())[:_MAX_ERRORS])
    raw_outputs = getattr(state, "outputs", {}) or {}
    outputs: list[tuple[str, str]] = []
    for key, value in list(raw_outputs.items())[:_MAX_OUTPUTS]:
        status = value.get("status") if isinstance(value, Mapping) else None
        summary = _short(value, 320)
        outputs.append((str(key), f"[{status}] {summary}" if status else summary))
    evidence = getattr(state, "evidence", ()) or ()
    return TransitionContext(
        phase=str(getattr(state, "phase", "") or ""),
        status=str(getattr(state, "status", "") or ""),
        errors=errors,
        outputs=tuple(outputs),
        evidence_count=len(evidence),
        objective=_short(str(getattr(state, "prompt", "") or ""), objective_chars),
    )


def build_decision_prompt(
    context: TransitionContext,
    candidates: Sequence[str],
    *,
    reason: str = "",
) -> tuple[str, str]:
    """Return (system, user) messages asking for one legal target, JSON only.

    ``reason`` is why a decision is needed (e.g. several edges share the same
    status); it is informational and never widens ``candidates``.
    """
    system = (
        "你是一个工作流的路由决策器。只能从给定的合法后继节点中选择一个，"
        "用一句话说明理由。输出严格 JSON：{\"target\": \"节点名\", \"reason\": \"理由\"}。"
        "不要输出集合之外的节点，不要输出解释性前后缀。"
    )
    user = json.dumps(
        {
            "why": reason,
            "state": context.to_dict(),
            "legal_next_nodes": list(candidates),
        },
        ensure_ascii=False,
    )
    return system, user


def _extract_json(raw: str) -> dict[str, Any] | None:
    if not raw:
        return None
    decoder = json.JSONDecoder()
    for part in [raw] + [p.strip() for p in raw.split("```") if p.strip()]:
        part = part.removeprefix("json").strip()
        try:
            value, _ = decoder.raw_decode(part)
        except json.JSONDecodeError:
            value = None
        if isinstance(value, dict):
            return value
        for index, char in enumerate(part):
            if char != "{":
                continue
            try:
                value, _ = decoder.raw_decode(part[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return value
    return None


@dataclass
class Decision:
    """The outcome of one routing decision, accepted or rejected."""

    target: str | None
    source: str
    reason: str = ""
    candidates: tuple[str, ...] = ()
    raw: str = ""
    # M8-T1271: the decision call's own token usage, when the caller's adapter
    # captured it.  Deliberately outside ``to_dict`` — the decision's *shape*
    # is the routing record; the spend rides the trace detail instead.
    usage: dict[str, Any] | None = None

    @property
    def accepted(self) -> bool:
        return self.target is not None and self.source == ROUTE_SOURCE_LLM

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "source": self.source,
            "reason": self.reason,
            "candidates": list(self.candidates),
            "accepted": self.accepted,
        }


def parse_decision(text: str, candidates: Iterable[str]) -> Decision:
    """Parse a model answer; accept a target only if it is a legal successor."""
    legal = tuple(candidates)
    raw = text or ""
    data = _extract_json(raw)
    if not data:
        return Decision(None, ROUTE_SOURCE_FALLBACK, "模型输出无法解析为 JSON", legal, raw)
    target = data.get("target")
    reason = str(data.get("reason") or "")[:240]
    if not isinstance(target, str) or target not in legal:
        return Decision(None, ROUTE_SOURCE_FALLBACK, "模型选择了非法后继节点", legal, raw)
    return Decision(target, ROUTE_SOURCE_LLM, reason, legal, raw)


async def choose_transition(
    *,
    state: Any,
    candidates: Sequence[str],
    static_target: str | None,
    call_model: Callable[[str, str], Any] | None,
    reason: str = "",
) -> Decision:
    """Choose the next node. Never raises on model failure — falls back.

    ``call_model(system, user)`` may return a value or an awaitable; it should
    produce a string (an ``LLMResponse.text`` is accepted too).  With no
    callable, or with fewer than two legal successors, the static route wins.
    """
    legal = tuple(candidates)
    if len(legal) < 2:
        return Decision(static_target, ROUTE_SOURCE_STATIC, "只有一个合法后继，无需决策", legal)
    if call_model is None:
        return Decision(static_target, ROUTE_SOURCE_STATIC, "未启用 LLM 决策", legal)
    system, user = build_decision_prompt(build_context(state), legal, reason=reason)
    try:
        result = call_model(system, user)
        if hasattr(result, "__await__"):
            result = await result
    except Exception as exc:  # noqa: BLE001 - a routing call must not kill a run
        return Decision(static_target, ROUTE_SOURCE_FALLBACK, f"决策调用失败: {type(exc).__name__}", legal)
    text = getattr(result, "text", None)
    if text is None:
        text = result if isinstance(result, str) else str(result)
    decision = parse_decision(str(text), legal)
    if not decision.accepted:
        decision.target = static_target
    return decision


#: The two legal successors of a failed verification that still has repair
#: budget.  ``repair`` is today's unconditional behavior; ``summarize`` is the
#: honest early exit when the failure is not actionable by a code change.
REPAIR_FORK_CANDIDATES = ("repair", "summarize")

_REPAIR_FORK_REASON = (
    "verify 失败且仍有修复预算。repair：失败可由修改代码修复（默认路径）；"
    "summarize：失败明显与本次改动无关（环境缺失、基础设施故障、既有损坏），"
    "盲目修复可能损伤原本完好的工作区。除非失败明确不可由代码修改修复，否则选 repair。"
)


def build_repair_fork_context(
    *,
    objective: str,
    verification_command: str,
    verification_output: str,
    repair_attempts: int,
    max_repairs: int,
    recent_errors: Sequence[str] = (),
    evidence_count: int = 0,
) -> TransitionContext:
    """Bounded snapshot for the verify→{repair,summarize} fork (M8-T1271).

    The decision-relevant datum is the failure itself, so it rides as the head
    error with its own (larger) budget; the objective and the remaining repair
    budget frame it.  Everything is capped, so a 200k-char failure dump cannot
    balloon the decision call.
    """
    head = _short(
        f"verify[{_short(verification_command, 200)}] 失败（第 {repair_attempts + 1} 次，"
        f"上限 {max_repairs}）：{verification_output}",
        1_600,
    )
    errors = (head,) + tuple(
        _short(e, 200) for e in list(recent_errors or ())[: _MAX_ERRORS - 1]
    )
    return TransitionContext(
        phase="verify",
        status="failed",
        errors=errors,
        outputs=(),
        evidence_count=evidence_count,
        objective=_short(objective, 240),
    )


async def repair_fork_decision(
    provider: Any,
    *,
    objective: str,
    verification_command: str,
    verification_output: str,
    repair_attempts: int,
    max_repairs: int,
    recent_errors: Sequence[str] = (),
    evidence_count: int = 0,
    system_msg: Callable[[str], Any] | None = None,
    user_msg: Callable[[str], Any] | None = None,
) -> Decision:
    """Ask the model whether a failed verification deserves repair at all.

    Fail-closed and frugal: with no provider, or no remaining repair budget,
    the answer is the static ``repair`` route without any model call.  A
    provider error or an illegal answer falls back to the static route too, so
    wiring this in can only *skip a repair with a recorded reason* — never
    widen the graph or turn a failed verify into a claimed success (the
    caller still ends the run with the failure spelled out).
    """
    if provider is None:
        return Decision("repair", ROUTE_SOURCE_STATIC, "静态路径：验证失败进入修复", REPAIR_FORK_CANDIDATES)
    if repair_attempts >= max_repairs:
        return Decision("repair", ROUTE_SOURCE_STATIC, "修复预算已用尽，无可决策", REPAIR_FORK_CANDIDATES)
    if system_msg is None or user_msg is None:
        from ..llm.base import system_msg as _sys, user_msg as _user

        system_msg = system_msg or _sys
        user_msg = user_msg or _user

    context = build_repair_fork_context(
        objective=objective,
        verification_command=verification_command,
        verification_output=verification_output,
        repair_attempts=repair_attempts,
        max_repairs=max_repairs,
        recent_errors=recent_errors,
        evidence_count=evidence_count,
    )

    async def call(system: str, user: str) -> str:
        response = await provider.chat(
            messages=[system_msg(system), user_msg(user)],  # type: ignore[misc]
            tools=None,
            on_delta=None,
        )
        usage = getattr(response, "usage", None)
        if usage is not None:
            usage_seen.append(usage)
        return response.text

    usage_seen: list[Any] = []
    decision = await choose_transition(
        state=context,
        candidates=REPAIR_FORK_CANDIDATES,
        static_target="repair",
        call_model=call,
        reason=_REPAIR_FORK_REASON,
    )
    if usage_seen:
        decision.usage = usage_seen[0]
    return decision


def make_decider(provider: Any, *, system_msg: Callable[[str], Any] | None = None,
                 user_msg: Callable[[str], Any] | None = None) -> Callable[..., Any]:
    """Adapt an LLM provider into a ``StateGraph.run(route_decider=...)`` callback.

    Uses the project's message helpers when supplied (avoids an import cycle);
    otherwise falls back to the provider's raw-message protocol.  The returned
    callback has the exact signature ``run`` calls with and always returns a
    :class:`Decision`, so the graph's fail-closed check stays authoritative.
    """
    if system_msg is None or user_msg is None:
        # Imported lazily to keep this module free of llm-package import cycles.
        from ..llm.base import system_msg as _sys, user_msg as _user
        system_msg = system_msg or _sys
        user_msg = user_msg or _user

    async def decider(state: Any, source: str, candidates: Sequence[str],
                      condition: str, static_target: str | None) -> Decision:
        async def call(system: str, user: str) -> str:
            response = await provider.chat(
                messages=[system_msg(system), user_msg(user)],  # type: ignore[misc]
                tools=None,
                on_delta=None,
            )
            return response.text
        return await choose_transition(
            state=state,
            candidates=candidates,
            static_target=static_target,
            call_model=call,
            reason=f"节点 {source} 在状态 {condition} 下有多条合法后继",
        )

    return decider


__all__ = [
    "REPAIR_FORK_CANDIDATES",
    "ROUTE_SOURCE_FALLBACK",
    "ROUTE_SOURCE_LLM",
    "ROUTE_SOURCE_STATIC",
    "Decision",
    "TransitionContext",
    "build_context",
    "build_decision_prompt",
    "build_repair_fork_context",
    "choose_transition",
    "make_decider",
    "parse_decision",
    "repair_fork_decision",
]
