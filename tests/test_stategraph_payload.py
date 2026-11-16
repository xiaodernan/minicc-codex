"""M8-T1112: the live StateGraph panel read must not drift from the runtime.

Everything the panel renders is derived from these objects; if the graph or
the router changes shape, the payload must move with it. These tests fail the
moment either side hand-copies a constant again.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace

from minicc.agent.graph import (
    DAGPlan,
    StateGraph,
    build_coding_workflow,
    execute_dag,
)
from minicc.config import (
    STAGE_IMPLEMENT,
    STAGE_INSPECT,
    STAGE_PLANNING,
    STAGE_REPAIR,
    STAGE_VERIFY,
)
from minicc.stategraph_payload import stategraph_payload


def _config(**overrides):
    base = dict(model="test-model-1", timeout=120.0, fallback_models=(), stage_routing=None)
    base.update(overrides)
    return SimpleNamespace(**base)


def test_nodes_are_the_live_workflow_in_order() -> None:
    payload = stategraph_payload(_config())
    live = build_coding_workflow()
    assert [n["id"] for n in payload["nodes"]] == list(live.nodes)
    assert [n["id"] for n in payload["nodes"]] == [
        "intake", "plan", STAGE_INSPECT, STAGE_IMPLEMENT, STAGE_VERIFY, STAGE_REPAIR, "summarize",
    ]
    for want, got in zip(live.nodes.values(), payload["nodes"]):
        assert got["phase"] == want.phase
        assert got["max_retries"] == want.max_retries


def test_edges_are_the_live_workflow_edges() -> None:
    payload = stategraph_payload(_config())
    live = build_coding_workflow()
    assert [(e["from"], e["to"], e["on"]) for e in payload["edges"]] == [
        (e.source, e.target, e.condition) for e in live.edges
    ]
    assert len(payload["edges"]) == 8


def test_guards_are_the_live_defaults_not_retyped_numbers() -> None:
    payload = stategraph_payload(_config())
    guards = payload["guards"]
    assert guards["max_nodes"] == inspect.signature(StateGraph.validate).parameters["max_nodes"].default
    assert guards["max_depth"] == inspect.signature(DAGPlan.validate).parameters["max_depth"].default
    assert guards["max_parallel"] == inspect.signature(execute_dag).parameters["max_concurrency"].default
    assert guards["max_steps"] == inspect.signature(StateGraph.run).parameters["max_steps"].default
    assert guards == {"max_nodes": 32, "max_depth": 16, "max_parallel": 4, "max_steps": 64}


def test_entry_matches_the_live_graph() -> None:
    payload = stategraph_payload(_config())
    assert payload["entry"] == build_coding_workflow().entry == "intake"
    assert payload["name"] == "coding"


def test_routing_disabled_keeps_every_stage_on_the_default_model() -> None:
    payload = stategraph_payload(_config(model="gpt-6.1-terra"))
    routing = payload["routing"]
    assert routing["enabled"] is False
    assert routing["stage_routing_present"] is False
    assert routing["default_model"] == "gpt-6.1-terra"
    assert [s["stage"] for s in routing["stages"]] == [
        STAGE_PLANNING, STAGE_INSPECT, STAGE_IMPLEMENT, STAGE_VERIFY, STAGE_REPAIR,
    ]
    for stage in routing["stages"]:
        assert stage["model"] == "gpt-6.1-terra"
        assert stage["tier"] == "balanced"
    assert routing["cost_limits_usd"] == {}


def test_routing_enabled_dispatches_per_stage() -> None:
    cfg = _config(
        model="gpt-6.1-terra",
        stage_routing={
            "enabled": True,
            "tiers": {
                "fast": ["gpt-4o-mini"],
                "balanced": ["gpt-4o"],
                "reasoning": ["o1"],
            },
            "stage_map": {
                STAGE_PLANNING: "balanced",
                STAGE_INSPECT: "fast",
                STAGE_IMPLEMENT: "balanced",
                STAGE_VERIFY: "fast",
                STAGE_REPAIR: "reasoning",
            },
            "cost_limits_usd": {STAGE_REPAIR: 1.5},
            "max_turns": {STAGE_INSPECT: 6},
            "reasoning_effort": {STAGE_REPAIR: "high"},
        },
    )
    payload = stategraph_payload(cfg)
    routing = payload["routing"]
    assert routing["enabled"] is True
    assert routing["stage_routing_present"] is True
    by_stage = {s["stage"]: s for s in routing["stages"]}
    assert by_stage[STAGE_PLANNING]["model"] == "gpt-4o"
    assert by_stage[STAGE_INSPECT]["model"] == "gpt-4o-mini"
    assert by_stage[STAGE_REPAIR]["model"] == "o1"
    assert by_stage[STAGE_VERIFY]["tier"] == "fast"
    assert by_stage[STAGE_REPAIR]["tier"] == "reasoning"
    assert routing["cost_limits_usd"] == {STAGE_REPAIR: 1.5}
    assert by_stage[STAGE_REPAIR]["max_cost_usd"] == 1.5
    assert by_stage[STAGE_INSPECT]["max_turns"] == 6


def test_reasoning_effort_reaches_the_payload() -> None:
    cfg = _config(
        stage_routing={
            "enabled": True,
            "tiers": {"reasoning": ["o1"]},
            "stage_map": {STAGE_REPAIR: "reasoning"},
            "reasoning_effort": {STAGE_REPAIR: "max"},
        },
    )
    payload = stategraph_payload(cfg)
    by_stage = {s["stage"]: s for s in payload["routing"]["stages"]}
    assert by_stage[STAGE_REPAIR]["reasoning_effort"] == "max"
