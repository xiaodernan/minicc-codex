"""Independent fence tests for ``minicc.route_wiring`` (M11-T6/T7).

Pins the four wiring helpers that let a stage route govern its own budget,
cost ceiling, turn cap, and provider endpoint/credentials. All pure logic;
``_stage_cost_estimator`` / ``_route_provider_spec`` are exercised with tiny
fakes (no network, no real router).

Run directly or via the repo gate:
    python tests/test_route_wiring_pure.py
    python -m pytest tests/test_route_wiring_pure.py -q -W error
"""

from minicc.agent.router import ModelTier, StageRoute
from minicc.config import ConfigError
from minicc.route_wiring import (
    _route_provider_spec,
    _route_turn_cap,
    _stage_cost_estimator,
    _stage_route_budget,
)


def _route(**kw):
    base = dict(stage="impl", model="gpt-4o", model_tier=ModelTier.BALANCED, timeout=30.0)
    base.update(kw)
    return StageRoute(**base)


# --- _stage_route_budget -----------------------------------------------------

def test_budget_route_max_turns_wins():
    b = _stage_route_budget(
        _route(max_turns=5),
        default_max_turns=10,
        default_max_duration_seconds=60.0,
        soft_max_tokens=1000,
        soft_max_duration_seconds=30.0,
    )
    assert b.max_turns == 5


def test_budget_falls_back_to_default_max_turns():
    b = _stage_route_budget(
        _route(max_turns=None),
        default_max_turns=10,
        default_max_duration_seconds=60.0,
        soft_max_tokens=None,
        soft_max_duration_seconds=None,
    )
    assert b.max_turns == 10


def test_budget_carries_route_cost_and_passthroughs():
    b = _stage_route_budget(
        _route(max_cost_usd=1.5),
        default_max_turns=10,
        default_max_duration_seconds=60.0,
        soft_max_tokens=1000,
        soft_max_duration_seconds=30.0,
    )
    assert b.max_cost_usd == 1.5
    assert b.max_duration_seconds == 60.0
    assert b.soft_max_tokens == 1000
    assert b.soft_max_duration_seconds == 30.0


def test_budget_never_sets_tool_calls_or_retries():
    # retry/recovery policy is tracked separately and must not raise
    # BudgetExceeded during a long coding session.
    b = _stage_route_budget(
        _route(),
        default_max_turns=10,
        default_max_duration_seconds=60.0,
        soft_max_tokens=None,
        soft_max_duration_seconds=None,
    )
    assert b.max_tool_calls is None
    assert b.max_retries is None


# --- _route_turn_cap ---------------------------------------------------------

def test_turn_cap_none_uses_default():
    assert _route_turn_cap(_route(max_turns=None), default=4) == 4


def test_turn_cap_configured_wins():
    assert _route_turn_cap(_route(max_turns=7), default=4) == 7


def test_turn_cap_zero_is_meaningful():
    assert _route_turn_cap(_route(max_turns=0), default=4) == 0


def test_turn_cap_negative_clamped_to_zero():
    # a misread must never widen the cap
    assert _route_turn_cap(_route(max_turns=-3), default=4) == 0


# --- _stage_cost_estimator ---------------------------------------------------

class _FakeRouter:
    def __init__(self, ret=0.25):
        self.calls = []
        self._ret = ret

    def estimate_cost(self, stage, input_tokens, output_tokens):
        self.calls.append((stage, input_tokens, output_tokens))
        return self._ret


def test_cost_estimator_passes_counts():
    router = _FakeRouter(ret=0.5)
    est = _stage_cost_estimator(router, "impl")
    assert est({"prompt_tokens": 100, "completion_tokens": 20}) == 0.5
    assert router.calls == [("impl", 100, 20)]


def test_cost_estimator_missing_keys_become_zero():
    router = _FakeRouter()
    est = _stage_cost_estimator(router, "impl")
    est({})
    assert router.calls == [("impl", 0, 0)]


def test_cost_estimator_none_values_become_zero():
    router = _FakeRouter()
    est = _stage_cost_estimator(router, "impl")
    est({"prompt_tokens": None, "completion_tokens": None})
    assert router.calls == [("impl", 0, 0)]


# --- _route_provider_spec ----------------------------------------------------

class _Entry:
    def __init__(self, name="m", provider="openai", base_url=None, api_key_env=None):
        self.name = name
        self.provider = provider
        self.base_url = base_url
        self.api_key_env = api_key_env


class _StageRouter:
    def __init__(self, *, enabled=True, entry=None):
        self._enabled = enabled
        self._entry = entry

    def routing_enabled(self):
        return self._enabled

    def model_config(self, name):
        return self._entry


class _Config:
    provider_type = "openai"
    api_key = "deploy-key"
    base_url = "https://api.example.com/v1"
    anthropic_base_url = "https://anthropic.example.com"


def test_provider_spec_none_router():
    assert _route_provider_spec(None, "m", _Config()) is None


def test_provider_spec_routing_disabled():
    assert _route_provider_spec(_StageRouter(enabled=False, entry=_Entry()), "m", _Config()) is None


def test_provider_spec_unregistered_model():
    assert _route_provider_spec(_StageRouter(entry=None), "m", _Config()) is None


def test_provider_spec_unknown_provider_raises():
    import pytest
    with pytest.raises(ConfigError):
        _route_provider_spec(_StageRouter(entry=_Entry(provider="bogus")), "m", _Config())


def test_provider_spec_same_family_silent_card_is_none():
    # same family + no base_url + no api_key_env -> build exactly as deployed
    assert _route_provider_spec(_StageRouter(entry=_Entry(provider="openai")), "m", _Config()) is None


def test_provider_spec_same_family_base_url_override():
    spec = _route_provider_spec(
        _StageRouter(entry=_Entry(provider="openai", base_url="https://override/v1")), "m", _Config()
    )
    assert spec == {"family": "openai", "base_url": "https://override/v1", "api_key": "deploy-key"}


def test_provider_spec_cross_family_anthropic_uses_anthropic_base():
    spec = _route_provider_spec(
        _StageRouter(entry=_Entry(provider="anthropic")), "m", _Config()
    )
    assert spec["family"] == "anthropic"
    assert spec["base_url"] == "https://anthropic.example.com"
    assert spec["api_key"] == "deploy-key"


def test_provider_spec_api_key_env_unset_raises(monkeypatch):
    import pytest
    monkeypatch.delenv("MINICC_ROUTE_KEY", raising=False)
    with pytest.raises(ConfigError):
        _route_provider_spec(
            _StageRouter(entry=_Entry(provider="anthropic", api_key_env="MINICC_ROUTE_KEY")),
            "m",
            _Config(),
        )


def test_provider_spec_api_key_env_set_used(monkeypatch):
    monkeypatch.setenv("MINICC_ROUTE_KEY", "vendor-key")
    spec = _route_provider_spec(
        _StageRouter(entry=_Entry(provider="anthropic", api_key_env="MINICC_ROUTE_KEY")),
        "m",
        _Config(),
    )
    assert spec["api_key"] == "vendor-key"


if __name__ == "__main__":
    import sys
    import pytest

    sys.exit(pytest.main([__file__, "-q", "-W", "error"]))
