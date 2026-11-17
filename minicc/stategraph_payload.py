"""Live StateGraph payload for the web panel — one source of truth, read live.

The panel used to carry a hand-typed replica of
``minicc/agent/graph.py::build_coding_workflow()``. This module is the seam that
makes the panel show the runtime's own objects instead:

- nodes, edges, entry and guard limits are read off the actual classes
  (``inspect`` reads the live defaults — if the guards ever move, the panel
  moves with them, no edit required);
- per-stage routing is resolved by the same ``StageRouter`` the request path
  builds, from the same config object, so what the panel shows is what a run
  would actually do.

Nothing here hand-copies a constant; tests in
``tests/test_stategraph_payload.py`` compare against the live objects.
"""

from __future__ import annotations

import inspect
from typing import Any

from .agent.graph import DAGPlan, StateGraph, build_coding_workflow, execute_dag
from .agent.router import StageRouter
from .config import (
    STAGE_IMPLEMENT,
    STAGE_INSPECT,
    STAGE_PLANNING,
    STAGE_REPAIR,
    STAGE_VERIFY,
)

#: The stages a run actually carries, in phase-axis order — the same order the
#: fixed workflow declares them, minus intake/summarize which are not routed.
_ROUTED_STAGES = (
    STAGE_PLANNING,
    STAGE_INSPECT,
    STAGE_IMPLEMENT,
    STAGE_VERIFY,
    STAGE_REPAIR,
)


def _default(fn: Any, param: str) -> Any:
    """Read one *keyword* default straight off the function the runtime uses."""
    return inspect.signature(fn).parameters[param].default


def _guards() -> dict[str, int]:
    return {
        "max_nodes": int(_default(StateGraph.validate, "max_nodes")),
        "max_depth": int(_default(DAGPlan.validate, "max_depth")),
        "max_parallel": int(_default(execute_dag, "max_concurrency")),
        "max_steps": int(_default(StateGraph.run, "max_steps")),
    }


def _routing_payload(config: Any) -> dict[str, Any]:
    model = str(getattr(config, "model", "") or "")
    timeout = float(getattr(config, "timeout", 180.0) or 180.0)
    fallback_models = tuple(getattr(config, "fallback_models", ()) or ())
    stage_routing = getattr(config, "stage_routing", None)
    routing_cfg = stage_routing if isinstance(stage_routing, dict) else {}

    router = StageRouter(
        model,
        timeout,
        fallback_models=fallback_models,
        stage_routing_config=routing_cfg or None,
    )
    stages = []
    for stage in _ROUTED_STAGES:
        route = router.route(stage)
        stages.append(
            {
                "stage": stage,
                "tier": route.model_tier.value,
                "model": route.model,
                "timeout": route.timeout,
                "max_turns": route.max_turns,
                "reasoning_effort": route.reasoning_effort,
                "max_cost_usd": route.max_cost_usd,
                "fallback_models": list(route.fallback_models),
                "provider": route.provider,
            }
        )
    cost_limits = routing_cfg.get("cost_limits_usd", {})
    return {
        "enabled": router.routing_enabled(),
        "default_model": model,
        "stage_routing_present": bool(routing_cfg),
        "stages": stages,
        "cost_limits_usd": dict(cost_limits) if isinstance(cost_limits, dict) else {},
    }


def stategraph_payload(config: Any) -> dict[str, Any]:
    """Serialize the runtime's own coding workflow and stage routing.

    Never raises for a well-formed config; anything unreadable is reported in
    the payload's ``routing`` block by the router's own answers, not by this
    function guessing. The route handler still guards against surprises so the
    panel never 500s.
    """
    graph = build_coding_workflow()
    graph.validate()
    return {
        "name": graph.name,
        "entry": graph.entry,
        "nodes": [
            {"id": node.name, "phase": node.phase, "max_retries": node.max_retries}
            for node in graph.nodes.values()
        ],
        "edges": [
            {"from": edge.source, "to": edge.target, "on": edge.condition}
            for edge in graph.edges
        ],
        "guards": _guards(),
        "routing": _routing_payload(config),
    }
