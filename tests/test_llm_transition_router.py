"""M8-T1267: the LLM transition router is opt-in, token-frugal and fail-closed.

The operator's standing request is to put the model's analysis *inside* the
state flow, not just as an after-the-fact reviewer.  These tests pin the three
properties that make that safe to ship:

1. the model can only choose among the current node's legal edges (never a
   hallucinated target), and any failure falls back to the old static route;
2. the model sees a bounded snapshot, so a long run cannot blow the budget;
3. ``StateGraph.run`` is byte-for-byte unchanged unless a decider is supplied.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from minicc.agent.graph import GraphNode, NodeResult, StateGraph
from minicc.agent.llm_router import (
    ROUTE_SOURCE_FALLBACK,
    ROUTE_SOURCE_LLM,
    ROUTE_SOURCE_STATIC,
    TransitionContext,
    build_context,
    build_decision_prompt,
    choose_transition,
    parse_decision,
)
from minicc.agent.state import AgentState


# ---------------------------------------------------------------------------
# parse_decision — fail-closed
# ---------------------------------------------------------------------------

def test_parse_accepts_a_legal_target():
    d = parse_decision('{"target": "repair", "reason": "verify failed"}', ["verify", "repair"])
    assert d.accepted
    assert d.target == "repair"
    assert d.source == ROUTE_SOURCE_LLM
    assert d.reason == "verify failed"


def test_parse_rejects_a_hallucinated_target():
    d = parse_decision('{"target": "delete_everything"}', ["verify", "repair"])
    assert not d.accepted
    assert d.target is None
    assert d.source == ROUTE_SOURCE_FALLBACK


@pytest.mark.parametrize("raw", ["", "not json", '{"reason": "no target"}', "```text\nplain\n```"])
def test_parse_falls_back_on_unparsable(raw):
    d = parse_decision(raw, ["a", "b"])
    assert not d.accepted and d.target is None


def test_parse_reads_fenced_json():
    d = parse_decision('```json\n{"target":"summarize","reason":"ok"}\n```', ["summarize"])
    assert d.accepted and d.target == "summarize"


# ---------------------------------------------------------------------------
# choose_transition — opt-in and bounded
# ---------------------------------------------------------------------------

def test_single_successor_skips_the_model():
    called = []

    def model(system, user):
        called.append((system, user))
        return '{"target": "anything"}'

    d = asyncio.run(choose_transition(
        state=SimpleNamespace(), candidates=["only"], static_target="only", call_model=model,
    ))
    assert d.source == ROUTE_SOURCE_STATIC and d.target == "only"
    assert called == [], "no model call when there is nothing to decide"


def test_no_decider_returns_static_without_calling():
    d = asyncio.run(choose_transition(
        state=SimpleNamespace(), candidates=["a", "b"], static_target="a", call_model=None,
    ))
    assert d.source == ROUTE_SOURCE_STATIC and d.target == "a"


def test_model_failure_falls_back_to_static():
    def boom(system, user):
        raise RuntimeError("gateway down")

    d = asyncio.run(choose_transition(
        state=SimpleNamespace(), candidates=["a", "b"], static_target="a", call_model=boom,
    ))
    assert d.source == ROUTE_SOURCE_FALLBACK and d.target == "a"
    assert "RuntimeError" in d.reason


def test_awaitable_model_result_is_supported():
    async def model(system, user):
        return '{"target": "b", "reason": "pick b"}'

    d = asyncio.run(choose_transition(
        state=SimpleNamespace(), candidates=["a", "b"], static_target="a", call_model=model,
    ))
    assert d.accepted and d.target == "b"


def test_context_is_bounded_even_for_a_long_run():
    state = SimpleNamespace(
        phase="verify", status="running",
        errors=[f"error {i}" for i in range(50)],
        outputs={f"node{i}": {"status": "ok", "blob": "x" * 5000} for i in range(40)},
        evidence=[{"ref": i} for i in range(30)],
        prompt="a" * 5000,
    )
    ctx = build_context(state)
    assert len(ctx.errors) <= 6
    assert len(ctx.outputs) <= 6
    assert ctx.evidence_count == 30
    assert len(ctx.objective) <= 240
    system, user = build_decision_prompt(ctx, ["a", "b"])
    assert "legal_next_nodes" in user and "a" in user and "b" in user
    assert len(user) < 6000, "decision prompt must stay small"


def test_transition_context_roundtrip():
    ctx = TransitionContext(phase="verify", status="running", errors=["x"], objective="do")
    d = ctx.to_dict()
    assert d["phase"] == "verify" and d["errors"] == ["x"] and d["objective"] == "do"


# ---------------------------------------------------------------------------
# StateGraph.run wiring — zero regression + opt-in LLM routing
# ---------------------------------------------------------------------------

def _graph():
    g = StateGraph(name="t", entry="a")
    g.add_node(GraphNode("a", "a"))
    g.add_node(GraphNode("plan", "plan"))
    g.add_node(GraphNode("repair", "repair"))
    g.add_edge("a", "plan", condition="ok")     # static first edge
    g.add_edge("a", "repair", condition="ok")   # alternate legal edge, same status
    return g


def _state():
    return AgentState(task_id="t1", prompt="do the thing", workspace_path=".")


def test_run_without_decider_is_unchanged():
    # static route picks the first matching edge: "plan"
    result = asyncio.run(_graph().run(_state(), {}, max_steps=4))
    assert result.status == "completed"
    assert result.node == "plan", "no decider -> the original first-edge choice"


def test_run_with_decider_can_choose_the_alternate_edge():
    chosen = []

    def decider(state, source, candidates, condition, static_target):
        chosen.append(list(candidates))
        # choose the last legal successor, i.e. NOT the static one
        return '{"target": "repair", "reason": "analysis says repair"}'

    g = _graph()
    g.nodes["repair"] = GraphNode("repair", "repair")
    result = asyncio.run(g.run(_state(), {}, max_steps=4, route_decider=lambda s, src, c, cond, st: parse_decision(decider(s, src, c, cond, st), c)))
    assert result.node == "repair", "LLM decision routed to the alternate legal edge"
    assert chosen and set(chosen[0]) == {"plan", "repair"}


def test_run_decider_cannot_choose_an_illegal_edge():
    g = _graph()

    def bad_decider(state, source, candidates, condition, static_target):
        return '{"target": "escape", "reason": "nope"}'

    result = asyncio.run(g.run(
        _state(), {}, max_steps=4,
        route_decider=lambda s, src, c, cond, st: parse_decision(bad_decider(s, src, c, cond, st), c),
    ))
    assert result.node == "plan", "illegal target rejected -> static edge survives"


def test_run_records_the_decision_in_trace():
    g = _graph()
    result = asyncio.run(g.run(
        _state(), {}, max_steps=4,
        route_decider=lambda s, src, c, cond, st: parse_decision('{"target":"plan","reason":"why"}', c),
    ))
    decisions = [e for e in result.trace_events if e.get("kind") == "llm_route_decision"]
    assert len(decisions) == 1
    assert decisions[0]["chosen"] == "plan"
    assert decisions[0]["decision"]["source"] == ROUTE_SOURCE_LLM


def test_make_decider_adapts_a_provider_into_a_graph_callback():
    from minicc.agent.llm_router import make_decider
    from minicc.llm.base import system_msg, user_msg

    class FakeProvider:
        async def chat(self, *, messages, tools, on_delta):
            assert messages[0]["role"] == "system"
            assert "legal_next_nodes" in messages[1]["content"]
            assert tools is None and on_delta is None
            return SimpleNamespace(text='{"target": "repair", "reason": "evidence"}')

    decider = make_decider(FakeProvider(), system_msg=system_msg, user_msg=user_msg)
    d = asyncio.run(decider(
        SimpleNamespace(phase="verify", status="failed", errors=[], outputs={}, evidence=(), prompt="x"),
        "verify", ["repair", "summarize"], "failed", "summarize",
    ))
    assert d.accepted and d.target == "repair"


def test_full_graph_run_with_provider_backed_decider():
    from minicc.agent.llm_router import make_decider
    from minicc.llm.base import system_msg, user_msg

    class FakeProvider:
        async def chat(self, *, messages, tools, on_delta):
            return SimpleNamespace(text='{"target": "repair", "reason": "llm says so"}')

    decider = make_decider(FakeProvider(), system_msg=system_msg, user_msg=user_msg)
    result = asyncio.run(_graph().run(_state(), {}, max_steps=4, route_decider=decider))
    assert result.node == "repair"


def test_decision_trace_never_records_a_bare_coroutine():
    """Regression: an async decider must be awaited, not traced as a coroutine."""
    from minicc.agent.llm_router import make_decider
    from minicc.llm.base import system_msg, user_msg

    class FakeProvider:
        async def chat(self, *, messages, tools, on_delta):
            return SimpleNamespace(text='{"target": "plan", "reason": "async"}')

    decider = make_decider(FakeProvider(), system_msg=system_msg, user_msg=user_msg)
    result = asyncio.run(_graph().run(_state(), {}, max_steps=4, route_decider=decider))
    traces = [e for e in result.trace_events if e.get("kind") == "llm_route_decision"]
    assert len(traces) == 1
    assert traces[0]["decision"].get("source") == ROUTE_SOURCE_LLM
    assert "coroutine" not in str(traces[0]["decision"])
