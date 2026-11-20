"""M8-T1271 — the verify→{repair, summarize} fork is a *decision*, not a reflex.

T1267 gave the StateGraph an opt-in LLM edge decider; its own E2E showed the
real model choosing ``repair`` over ``summarize`` from stage evidence.  But the
production run path (web.py) is imperative: a failed verification unconditionally
enters repair while attempts remain — the model never gets asked whether the
failure is even actionable.  A blind repair on a dead environment or a pre-existing
breakage can damage a tree that was fine; an honest early summarize with a reason
is the better exit there, and only the model can tell the two apart from the
failure text.

``repair_fork_decision`` wraps :func:`choose_transition` for exactly this fork:
bounded context (command + failure output + attempts + objective), candidates
``("repair", "summarize")``, static target ``"repair"`` (today's behavior).
Fail-closed: a provider error, an unparsable answer or an out-of-set target all
return the static route, so enabling the call can only *skip a repair with a
recorded reason* — never widen the graph.
"""

from __future__ import annotations

import asyncio

import pytest

from minicc.agent.llm_router import (
    ROUTE_SOURCE_FALLBACK,
    ROUTE_SOURCE_LLM,
    ROUTE_SOURCE_STATIC,
    Decision,
    repair_fork_decision,
)


class _FakeResponse:
    def __init__(self, text: str, usage: dict | None = None) -> None:
        self.text = text
        self.usage = usage


class _FakeProvider:
    """Records the decision prompt it was handed; answers from a script."""

    def __init__(self, text: str = "", exc: Exception | None = None,
                 usage: dict | None = None) -> None:
        self.text = text
        self.exc = exc
        self.usage = usage
        self.calls: list[list[dict]] = []

    async def chat(self, messages, tools=None, on_delta=None):
        self.calls.append(list(messages))
        if self.exc is not None:
            raise self.exc
        return _FakeResponse(self.text, usage=self.usage)


def _run(coro):
    return asyncio.run(coro)


def _decision(provider, **kwargs) -> Decision:
    defaults = dict(
        objective="修复 tests/test_sums.py 中的两处断言失败",
        verification_command="python -m pytest tests/test_sums.py",
        verification_output="AssertionError: expected 3, got 4",
        repair_attempts=0,
        max_repairs=2,
    )
    defaults.update(kwargs)
    return _run(repair_fork_decision(provider, **defaults))


def test_model_picking_repair_is_accepted_and_matches_static():
    provider = _FakeProvider('{"target": "repair", "reason": "断言差异可由代码修改修复"}')
    decision = _decision(provider)
    assert decision.accepted and decision.target == "repair"
    assert decision.source == ROUTE_SOURCE_LLM
    # The model saw the failure text and the fork policy, not the whole run.
    system, user = provider.calls[0][0]["content"], provider.calls[0][1]["content"]
    assert "AssertionError: expected 3, got 4" in user
    assert "repair" in user and "summarize" in user


def test_model_choosing_summarize_is_accepted_with_reason():
    provider = _FakeProvider('{"target": "summarize", "reason": "测试环境缺 docker，失败与本次改动无关"}')
    decision = _decision(provider)
    assert decision.accepted and decision.target == "summarize"
    assert "docker" in decision.reason


def test_provider_error_falls_back_to_repair():
    provider = _FakeProvider(exc=RuntimeError("gateway 500"))
    decision = _decision(provider)
    assert decision.target == "repair" and not decision.accepted
    assert decision.source == ROUTE_SOURCE_FALLBACK


def test_unparsable_answer_falls_back_to_repair():
    provider = _FakeProvider("我觉得应该修一下")
    decision = _decision(provider)
    assert decision.target == "repair" and not decision.accepted


def test_out_of_set_target_falls_back_to_repair():
    provider = _FakeProvider('{"target": "deploy", "reason": "直接上线"}')
    decision = _decision(provider)
    assert decision.target == "repair" and not decision.accepted


def test_exhausted_attempts_never_calls_the_model():
    """No attempts left = nothing to decide; the static give-up must stand alone."""
    provider = _FakeProvider('{"target": "repair", "reason": "还能修"}')
    decision = _decision(provider, repair_attempts=2, max_repairs=2)
    assert decision.target == "repair" and decision.source == ROUTE_SOURCE_STATIC
    assert provider.calls == []


def test_no_provider_is_static_repair():
    decision = _run(
        repair_fork_decision(
            None,
            objective="x",
            verification_command="pytest -q",
            verification_output="failed",
            repair_attempts=0,
            max_repairs=2,
        )
    )
    assert decision.target == "repair" and decision.source == ROUTE_SOURCE_STATIC


def test_decision_call_usage_rides_the_decision_for_the_ledger():
    provider = _FakeProvider(
        '{"target": "repair", "reason": "r"}',
        usage={"prompt_tokens": 120, "completion_tokens": 18, "total_tokens": 138},
    )
    decision = _decision(provider)
    assert decision.usage == {"prompt_tokens": 120, "completion_tokens": 18, "total_tokens": 138}
    # The decision's *shape* stays the routing record; the spend is a rider.
    assert "usage" not in decision.to_dict()


def test_decision_without_reported_usage_leaves_the_rider_none():
    provider = _FakeProvider('{"target": "summarize", "reason": "环境坏了"}')
    decision = _decision(provider)
    assert decision.usage is None


def test_context_is_bounded_even_for_a_huge_failure_dump():
    provider = _FakeProvider('{"target": "repair", "reason": "r"}')
    _decision(
        provider,
        verification_output="x" * 200_000,
        objective="y" * 200_000,
    )
    user = provider.calls[0][1]["content"]
    assert len(user) < 8_000, f"decision prompt ballooned to {len(user)} chars"
