"""Stage-route wiring shared by the web and CLI surfaces (M11-T7).

The route that picks a run's model must also govern how that model is
reached and how its use is capped. Those rules lived as private helpers in
``web.py`` while the CLI built its provider from raw config - so
``MINICC_STAGE_ROUTING`` was parsed, advertised, and then silently ignored
by an entire surface. The helpers move here (a narrow extraction, not a
rewrite) so both surfaces consume one implementation; duplicating them
would recreate the two-copies defect class ``stream_merge`` already paid
for. Nothing in this module imports the web stack: the CLI entry point
stays lightweight.
"""

from __future__ import annotations

import os
from typing import Any, Callable

from .agent.router import StageRoute, StageRouter
from .agent.state import Budget
from .config import ConfigError


def _stage_route_budget(
    route: StageRoute,
    *,
    default_max_turns: int | None,
    default_max_duration_seconds: float | None,
    soft_max_tokens: int | None,
    soft_max_duration_seconds: float | None,
) -> Budget:
    """Build the run budget a stage route governs (M11 enforcement).

    The route that picked the model also caps its use: an explicitly
    configured ``max_turns`` / ``max_cost_usd`` wins over the built-in
    default, and an absent one falls back to it. A legacy route (routing
    disabled) sets neither, so the result is exactly the pre-routing
    budget - enforcement is opt-in with the routing itself.
    """
    return Budget(
        max_turns=route.max_turns if route.max_turns is not None else default_max_turns,
        max_tool_calls=None,
        max_duration_seconds=default_max_duration_seconds,
        # Retry/recovery policy is tracked separately by the callers. It is
        # not a task budget and must not raise BudgetExceeded during a
        # long-running coding session.
        max_retries=None,
        max_cost_usd=route.max_cost_usd,
        soft_max_tokens=soft_max_tokens,
        soft_max_duration_seconds=soft_max_duration_seconds,
    )


def _stage_cost_estimator(router: StageRouter, stage: str) -> Callable[[dict[str, Any]], float]:
    """Price one usage dict at the routed model (M11 cost ceilings).

    Cache discounts are deliberately ignored: with the per-1M price applied
    to the full prompt/completion counts the estimate can only be too HIGH,
    so a misread never widens the ceiling - it trips early instead. An
    model no price table knows prices at 0.0 by ``estimate_cost`` contract,
    which degrades the ceiling to "not enforced" honestly (it is also how the
    router reports an unknown price everywhere else). A routed model the registry
    never heard of but ``minicc.pricing`` did is priced now, which can only ever
    make a ceiling trip earlier, never later.
    """

    def estimate(usage: dict[str, Any]) -> float:
        return router.estimate_cost(
            stage,
            int(usage.get("prompt_tokens") or 0),
            int(usage.get("completion_tokens") or 0),
        )

    return estimate


def _route_turn_cap(route: StageRoute, *, default: int) -> int:
    """A route's ``max_turns``, when configured, overrides the caller's cap.

    Used where a stage's turn budget is a loop count rather than an
    ``run_agent`` budget (repair cycles, completion-review continues): the
    route value replaces the config default outright, and a negative value is
    clamped to 0 - a misread must never widen the cap. 0 is meaningful for
    these loops ("one attempt, then stop").
    """
    if route.max_turns is None:
        return default
    return max(0, int(route.max_turns))


_PROVIDER_FAMILY = {
    "anthropic": "anthropic",
    "openai": "openai",
    "openai_compatible": "openai",
}


def _route_provider_spec(stage_router: Any, model_name: Any, config: Any) -> dict[str, Any] | None:
    """Resolve the wire family, endpoint and credentials a routed model demands.

    route.provider reached only the event - the factory kept building
    whatever ``provider_type`` the deployment declares, so a registry
    entry that names another family was reported but never served a
    request. Now a registered model reaches the factory with its own
    card:

    - ``base_url`` comes from the registry entry, falling back to the
      family-appropriate config field (M11-T6: also within the same
      family - a per-model endpoint override is honored, not just a
      cross-vendor one);
    - the credential comes from the env var ``api_key_env`` names. Naming
      an env var that is unset is a ConfigError: the deployment key must
      never be silently POSTed to another vendor's endpoint. Without
      ``api_key_env`` the deployment key is used as-is - correct for
      multi-protocol gateways that share one key.

    Returns None (build exactly as deployed) when the model is
    unregistered, when routing is off, or when the card is silent - a
    registered model that declares neither base_url nor api_key_env
    changes nothing, so every existing deployment keeps its shape. An
    unknown provider value in the registry is a ConfigError, not a
    silent deployment fallback: a typoed family must not quietly rewire
    a run.
    """
    if stage_router is None or not stage_router.routing_enabled():
        return None
    entry = stage_router.model_config(str(model_name))
    if entry is None:
        return None
    family = _PROVIDER_FAMILY.get(str(entry.provider))
    if family is None:
        raise ConfigError(
            f"custom_models 里的 {entry.name} 声明了未知 provider {entry.provider!r}；"
            "可用值：openai / openai_compatible / anthropic"
        )
    deployment = _PROVIDER_FAMILY.get(str(getattr(config, "provider_type", "openai") or "openai"))
    if entry.api_key_env:
        value = os.environ.get(entry.api_key_env, "")
        if not value.strip():
            raise ConfigError(
                f"路由的模型 {entry.name} 指定 api_key_env={entry.api_key_env}，"
                "但该环境变量未设置——拒绝把部署密钥发给另一家厂商的端点"
            )
        api_key = value
    else:
        api_key = str(config.api_key)
    if family == "anthropic":
        base_url = str(entry.base_url or getattr(config, "anthropic_base_url", "") or config.base_url)
    else:
        base_url = str(entry.base_url or config.base_url)
    if family == deployment and entry.base_url is None and not entry.api_key_env:
        # Same family and a silent card: nothing to override, keep the
        # deployment's construction call for granted.
        return None
    return {"family": family, "base_url": base_url, "api_key": api_key}
