"""Per-stage model router with cost limits and cross-vendor failover (M11).

Routes model requests by execution stage with configurable model tiers,
cost ceilings, and automatic failover across providers.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ModelTier(str, Enum):
    """Model capability tiers for stage routing."""
    FAST = "fast"           # Low latency, low cost (e.g., gpt-4o-mini, claude-3-haiku)
    BALANCED = "balanced"   # Good quality/latency (e.g., gpt-4o, claude-3.5-sonnet)
    REASONING = "reasoning" # High reasoning (e.g., o1, o3, claude-3.7-sonnet)


@dataclass(frozen=True)
class ModelConfig:
    """Single model configuration with pricing and capabilities."""
    name: str
    tier: ModelTier
    provider: str  # "openai" | "anthropic" | "openai_compatible"
    base_url: str | None = None
    api_key_env: str | None = None
    # Cost per 1M tokens (input, output, cache_read, cache_write)
    cost_usd_per_1m: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    max_tokens: int = 8192
    supports_tools: bool = True
    supports_vision: bool = False
    supports_reasoning_effort: bool = False


@dataclass(frozen=True)
class StageRoute:
    """Resolved route for a stage."""
    stage: str
    model: str
    model_tier: ModelTier
    timeout: float
    fallback_models: tuple[str, ...] = ()
    max_cost_usd: float | None = None
    max_turns: int | None = None
    provider: str = "openai_compatible"
    reasoning_effort: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "stage": self.stage,
            "model": self.model,
            "model_tier": self.model_tier.value,
            "timeout": self.timeout,
            "fallback_models": list(self.fallback_models),
            "provider": self.provider,
        }
        if self.max_cost_usd is not None:
            payload["max_cost_usd"] = self.max_cost_usd
        if self.max_turns is not None:
            payload["max_turns"] = self.max_turns
        if self.reasoning_effort is not None:
            payload["reasoning_effort"] = self.reasoning_effort
        return payload


# Default model registry (module-level, not a dataclass field)
_DEFAULT_MODELS: dict[str, ModelConfig] = {
    # OpenAI models
    "gpt-4o-mini": ModelConfig("gpt-4o-mini", ModelTier.FAST, "openai",
        cost_usd_per_1m=(0.15, 0.60, 0.075, 0.0), max_tokens=16384),
    "gpt-4o": ModelConfig("gpt-4o", ModelTier.BALANCED, "openai",
        cost_usd_per_1m=(2.50, 10.00, 1.25, 0.0), max_tokens=16384),
    "gpt-4.1": ModelConfig("gpt-4.1", ModelTier.BALANCED, "openai",
        cost_usd_per_1m=(2.00, 8.00, 1.00, 0.0), max_tokens=32768),
    "o1": ModelConfig("o1", ModelTier.REASONING, "openai",
        cost_usd_per_1m=(15.00, 60.00, 7.50, 0.0), max_tokens=32768, supports_reasoning_effort=True),
    "o3": ModelConfig("o3", ModelTier.REASONING, "openai",
        cost_usd_per_1m=(20.00, 80.00, 10.00, 0.0), max_tokens=32768, supports_reasoning_effort=True),
    # Anthropic models
    "claude-3-haiku": ModelConfig("claude-3-haiku", ModelTier.FAST, "anthropic",
        cost_usd_per_1m=(0.25, 1.25, 0.125, 0.0), max_tokens=4096),
    "claude-3.5-sonnet": ModelConfig("claude-3.5-sonnet", ModelTier.BALANCED, "anthropic",
        cost_usd_per_1m=(3.00, 15.00, 1.50, 0.0), max_tokens=8192),
    "claude-3.7-sonnet": ModelConfig("claude-3.7-sonnet", ModelTier.REASONING, "anthropic",
        cost_usd_per_1m=(3.00, 15.00, 1.50, 0.0), max_tokens=8192, supports_reasoning_effort=True),
}


class StageRouter:
    """Route stages with per-stage model selection, cost limits, and failover.

    Configuration via config.json:
    {
      "stage_routing": {
        "enabled": true,
        "tiers": {
          "fast": ["gpt-4o-mini", "claude-3-haiku"],
          "balanced": ["gpt-4o", "claude-3.5-sonnet"],
          "reasoning": ["o1", "claude-3.7-sonnet"]
        },
        "stage_map": {
          "planning": "balanced",
          "inspect": "fast",
          "implement": "balanced",
          "verify": "fast",
          "repair": "reasoning",
          "review": "balanced"
        },
        "cost_limits_usd": {
          "planning": 0.05,
          "implement": 0.50,
          "verify": 0.10,
          "repair": 1.00
        },
        "failover": {
          "enabled": true,
          "max_retries_per_model": 1,
          "fallback_tiers": ["balanced", "fast"]
        }
      }
    }
    """

    def __init__(
        self,
        model: str,
        timeout: float = 180.0,
        fallback_models: tuple[str, ...] = (),
        *,
        stage_routing_config: dict[str, Any] | None = None,
    ) -> None:
        self.default_model = str(model)
        self.timeout = max(10.0, float(timeout))
        self.fallback_models = tuple(str(item) for item in fallback_models if str(item).strip())
        self.stage_routing_config = stage_routing_config or {}
        self._models: dict[str, ModelConfig] = dict(_DEFAULT_MODELS)
        self._register_custom_models()

    def _register_custom_models(self) -> None:
        """Register custom models from stage_routing_config."""
        custom = self.stage_routing_config.get("custom_models", {})
        for name, cfg in custom.items():
            self._models[name] = ModelConfig(
                name=name,
                tier=ModelTier(cfg.get("tier", "balanced")),
                provider=cfg.get("provider", "openai_compatible"),
                base_url=cfg.get("base_url"),
                api_key_env=cfg.get("api_key_env"),
                cost_usd_per_1m=tuple(cfg.get("cost_usd_per_1m", [0.0, 0.0, 0.0, 0.0])),
                max_tokens=cfg.get("max_tokens", 8192),
                supports_tools=cfg.get("supports_tools", True),
                supports_vision=cfg.get("supports_vision", False),
                supports_reasoning_effort=cfg.get("supports_reasoning_effort", False),
            )

    def route(self, stage: str) -> StageRoute:
        """Resolve the route for a given stage."""
        if not self._is_stage_routing_enabled():
            return self._legacy_route(stage)

        stage = str(stage or "planning")
        tier_name = self._get_stage_tier(stage)
        model = self._select_model_for_tier(tier_name)
        cost_limit = self._get_cost_limit(stage)
        reasoning_effort = self._get_reasoning_effort(stage, tier_name)
        provider = self._models.get(model, ModelConfig(model, ModelTier.BALANCED, "openai_compatible")).provider

        return StageRoute(
            stage=stage,
            model=model,
            model_tier=ModelTier(tier_name),
            timeout=self._get_stage_timeout(stage),
            fallback_models=self._get_fallback_models(tier_name),
            max_cost_usd=cost_limit,
            max_turns=self._get_stage_max_turns(stage),
            provider=provider,
            reasoning_effort=reasoning_effort,
        )

    def _is_stage_routing_enabled(self) -> bool:
        return bool(self.stage_routing_config.get("enabled", False))

    def _legacy_route(self, stage: str) -> StageRoute:
        """Original behavior: same model, adjusted timeout."""
        stage = str(stage or "planning")
        factors = {"inspect": 0.75, "planning": 0.9, "implement": 1.0, "verify": 0.7, "repair": 1.0, "review": 0.8}
        factor = factors.get(stage, 1.0)
        return StageRoute(
            stage=stage,
            model=self.default_model,
            model_tier=ModelTier.BALANCED,
            timeout=round(self.timeout * factor, 1),
            fallback_models=self.fallback_models,
        )

    def _get_stage_tier(self, stage: str) -> str:
        stage_map = self.stage_routing_config.get("stage_map", {})
        default_map = {
            "planning": "balanced",
            "inspect": "fast",
            "implement": "balanced",
            "verify": "fast",
            "repair": "reasoning",
            "review": "balanced",
        }
        return stage_map.get(stage, default_map.get(stage, "balanced"))

    def _select_model_for_tier(self, tier: str) -> str:
        """Select the best available model for a tier."""
        tier_models = self.stage_routing_config.get("tiers", {}).get(tier, [])
        if not tier_models:
            # Fallback to default models by tier
            defaults = {
                "fast": ["gpt-4o-mini", "claude-3-haiku"],
                "balanced": ["gpt-4o", "claude-3.5-sonnet"],
                "reasoning": ["o1", "claude-3.7-sonnet"],
            }
            tier_models = defaults.get(tier, [self.default_model])

        # Return first available model (could check API availability here)
        for m in tier_models:
            if m in self._models or m == self.default_model:
                return m
        return self.default_model

    def _get_fallback_models(self, tier: str) -> tuple[str, ...]:
        """Get fallback models for failover."""
        fallback_tiers = self.stage_routing_config.get("failover", {}).get("fallback_tiers", [])
        fallbacks: list[str] = []
        for fallback_tier in fallback_tiers:
            tier_models = self.stage_routing_config.get("tiers", {}).get(fallback_tier, [])
            fallbacks.extend(tier_models)
        # Add configured fallback_models
        fallbacks.extend(self.fallback_models)
        # Deduplicate while preserving order
        seen = set()
        unique = []
        for m in fallbacks:
            if m not in seen:
                seen.add(m)
                unique.append(m)
        return tuple(unique)

    def _get_cost_limit(self, stage: str) -> float | None:
        cost_limits = self.stage_routing_config.get("cost_limits_usd", {})
        return cost_limits.get(stage)

    def _get_stage_timeout(self, stage: str) -> float:
        factors = {"inspect": 0.75, "planning": 0.9, "implement": 1.0, "verify": 0.7, "repair": 1.0, "review": 0.8}
        factor = factors.get(stage, 1.0)
        return round(self.timeout * factor, 1)

    def _get_stage_max_turns(self, stage: str) -> int | None:
        return self.stage_routing_config.get("max_turns", {}).get(stage)

    def _get_reasoning_effort(self, stage: str, tier: str) -> str | None:
        if tier == "reasoning":
            return self.stage_routing_config.get("reasoning_effort", {}).get(stage, "high")
        return None

    def estimate_cost(self, stage: str, input_tokens: int, output_tokens: int, cache_read: int = 0, cache_write: int = 0) -> float:
        """Estimate cost for a stage in USD."""
        route = self.route(stage)
        model = self._models.get(route.model)
        if not model:
            return 0.0
        input_cost, output_cost, cache_read_cost, cache_write_cost = model.cost_usd_per_1m
        return (
            (input_tokens * input_cost) +
            (output_tokens * output_cost) +
            (cache_read * cache_read_cost) +
            (cache_write * cache_write_cost)
        ) / 1_000_000


__all__ = ["ModelTier", "ModelConfig", "StageRoute", "StageRouter"]