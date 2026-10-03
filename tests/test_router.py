"""M11 stage router: tier resolution, cost ceilings, failover, and wiring.

The router is the only place that decides which model a stage runs on, so
these gates pin every decision a misread config would silently change: which
tier a stage maps to, which model that tier resolves to, whether a cost
ceiling / turn cap / reasoning effort actually reaches the route, how the
failover chain is built, and that all of it stays inert until
``stage_routing.enabled`` is set. The last section proves the config surface
(``stage_routing`` object -> ``Config`` -> ``web.AgentService``) is wired, not
just declared - a router nobody hands the config to is dead code.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from minicc.agent.router import ModelTier, StageRouter
from minicc.config import ConfigError, load_config


# The documented shape from StageRouter's docstring, verbatim: if this ever
# stops routing the way the docstring promises, the docstring is the bug.
FULL_ROUTING: dict[str, object] = {
    "enabled": True,
    "tiers": {
        "fast": ["gpt-4o-mini", "claude-3-haiku"],
        "balanced": ["gpt-4o", "claude-3.5-sonnet"],
        "reasoning": ["o1", "claude-3.7-sonnet"],
    },
    "stage_map": {
        "planning": "balanced",
        "inspect": "fast",
        "implement": "balanced",
        "verify": "fast",
        "repair": "reasoning",
        "review": "balanced",
    },
    "cost_limits_usd": {"planning": 0.05, "implement": 0.50, "verify": 0.10, "repair": 1.00},
    "max_turns": {"implement": 12},
    "reasoning_effort": {"repair": "xhigh"},
    "failover": {
        "enabled": True,
        "max_retries_per_model": 1,
        "fallback_tiers": ["balanced", "fast"],
    },
}


def _router(overrides: dict[str, object] | None = None) -> StageRouter:
    """A router with the documented config, optionally overridden per test."""
    config = json.loads(json.dumps(FULL_ROUTING))
    if overrides:
        config.update(overrides)
    return StageRouter(
        "gateway-main",
        100.0,
        fallback_models=("backup-1",),
        stage_routing_config=config,
    )


# -- routing is opt-in ------------------------------------------------------


@pytest.mark.parametrize(
    "config",
    [
        None,
        {},
        {"enabled": False},
        # Every other knob present, but the gate itself is off: none of it may
        # leak into the route, because that would silently change the model
        # every existing (routing-less) deployment runs on.
        json.loads(json.dumps({**FULL_ROUTING, "enabled": False})),
    ],
    ids=["none", "empty", "explicit-false", "fully-configured-but-disabled"],
)
def test_routing_stays_inert_until_enabled(config: dict[str, object] | None) -> None:
    for stage in ("planning", "inspect", "implement", "verify", "repair", "review"):
        route = StageRouter("terra", 100.0, stage_routing_config=config).route(stage)
        assert route.model == "terra", stage
        assert route.model_tier is ModelTier.BALANCED, stage
        assert route.max_cost_usd is None, stage
        assert route.max_turns is None, stage
        assert route.reasoning_effort is None, stage
        assert route.provider == "openai_compatible", stage


def test_a_disabled_router_still_carries_the_configured_fallback_models() -> None:
    """Disabling stage routing must not drop the plain fallback rotation."""
    router = StageRouter("primary", 100.0, fallback_models=("backup-1", "backup-2"))
    route = router.route("implement")
    assert route.fallback_models == ("backup-1", "backup-2")
    assert route.to_dict()["fallback_models"] == ["backup-1", "backup-2"]


# -- stage -> tier -> model -------------------------------------------------


@pytest.mark.parametrize(
    "stage,tier,model",
    [
        ("planning", ModelTier.BALANCED, "gpt-4o"),
        ("inspect", ModelTier.FAST, "gpt-4o-mini"),
        ("implement", ModelTier.BALANCED, "gpt-4o"),
        ("verify", ModelTier.FAST, "gpt-4o-mini"),
        ("repair", ModelTier.REASONING, "o1"),
        ("review", ModelTier.BALANCED, "gpt-4o"),
    ],
)
def test_the_documented_stage_map_resolves_to_the_tier_model(
    stage: str, tier: ModelTier, model: str
) -> None:
    route = _router().route(stage)
    assert route.stage == stage
    assert route.model_tier is tier
    assert route.model == model


def test_provider_comes_from_the_model_registry_not_the_tier_name() -> None:
    """A tier says nothing about the vendor; only the resolved model does."""
    router = _router({"tiers": {"fast": ["claude-3-haiku"]}})
    route = router.route("inspect")
    assert route.model == "claude-3-haiku"
    assert route.provider == "anthropic"


def test_a_tier_configured_with_an_unknown_model_falls_back_to_the_primary() -> None:
    """No gateway error mid-stage: an unregistered name degrades to the main model."""
    router = _router({"tiers": {"fast": ["not-a-registered-model"]}})
    route = router.route("inspect")
    assert route.model == "gateway-main"
    # The tier is still reported honestly even though the model degraded.
    assert route.model_tier is ModelTier.FAST


def test_a_custom_stage_map_reaches_a_tier_and_an_unknown_stage_defaults_to_balanced() -> None:
    router = _router({"stage_map": {"telemetry": "fast"}})
    assert router.route("telemetry").model == "gpt-4o-mini"
    # A stage nobody mapped falls back to the built-in default map, then to
    # "balanced" for a stage that is not in the built-in map either.
    assert router.route("deploy").model == "gpt-4o"
    assert router.route("deploy").model_tier is ModelTier.BALANCED


def test_an_enabled_router_without_tier_lists_uses_the_builtin_registry() -> None:
    """``enabled: true`` alone must be enough to get real routing."""
    router = StageRouter("gateway-main", 100.0, stage_routing_config={"enabled": True})
    assert router.route("repair").model == "o1"
    assert router.route("verify").model == "gpt-4o-mini"


def test_blank_and_missing_stage_names_normalize_to_planning() -> None:
    router = _router()
    assert router.route("").stage == "planning"
    assert router.route(None).stage == "planning"  # type: ignore[arg-type]


# -- ceilings, turn caps, reasoning effort ----------------------------------


def test_cost_ceiling_and_turn_cap_reach_the_route_only_where_configured() -> None:
    router = _router()
    capped = router.route("implement")
    assert capped.max_cost_usd == pytest.approx(0.50)
    assert capped.max_turns == 12
    payload = capped.to_dict()
    assert payload["max_cost_usd"] == pytest.approx(0.50)
    assert payload["max_turns"] == 12

    # inspect has neither a ceiling nor a cap configured - and to_dict must
    # omit them, because the stage_route event doubles as the UI's contract.
    open_route = router.route("inspect")
    assert open_route.max_cost_usd is None
    assert open_route.max_turns is None
    payload = open_route.to_dict()
    assert "max_cost_usd" not in payload
    assert "max_turns" not in payload


def test_reasoning_effort_is_set_only_on_the_reasoning_tier() -> None:
    router = _router()
    assert router.route("repair").reasoning_effort == "xhigh"
    assert router.route("implement").reasoning_effort is None
    # Default when the tier is reasoning but no per-stage override exists.
    default = _router({"stage_map": {"review": "reasoning"}})
    assert default.route("review").reasoning_effort == "high"
    assert "reasoning_effort" not in router.route("implement").to_dict()
    assert router.route("repair").to_dict()["reasoning_effort"] == "xhigh"


# -- failover chain ---------------------------------------------------------


def test_failover_chain_is_tier_models_then_configured_fallbacks_deduplicated() -> None:
    router = StageRouter(
        "gateway-main",
        100.0,
        fallback_models=("gpt-4o", "backup-1"),
        stage_routing_config=json.loads(json.dumps(FULL_ROUTING)),
    )
    route = router.route("repair")
    assert route.fallback_models == (
        "gpt-4o",
        "claude-3.5-sonnet",
        "gpt-4o-mini",
        "claude-3-haiku",
        "backup-1",
    )


def test_failover_without_tier_configuration_is_still_the_configured_fallbacks() -> None:
    router = StageRouter(
        "gateway-main",
        100.0,
        fallback_models=("backup-1",),
        stage_routing_config={"enabled": True},
    )
    assert router.route("planning").fallback_models == ("backup-1",)


def test_empty_fallback_models_are_filtered_out_at_construction() -> None:
    router = StageRouter(
        "gateway-main", 100.0, fallback_models=("", "  ", "backup-1")
    )
    assert router.fallback_models == ("backup-1",)


# -- custom models ----------------------------------------------------------


def test_custom_models_join_the_registry_with_their_endpoint_and_price() -> None:
    router = StageRouter(
        "gateway-main",
        100.0,
        stage_routing_config={
            "enabled": True,
            "tiers": {"fast": ["local-qwen"]},
            "custom_models": {
                "local-qwen": {
                    "tier": "fast",
                    "provider": "openai_compatible",
                    "base_url": "http://127.0.0.1:8000/v1",
                    "api_key_env": "LOCAL_QWEN_KEY",
                    "cost_usd_per_1m": [0.10, 0.20, 0.0, 0.0],
                    "max_tokens": 4096,
                    "supports_vision": False,
                }
            },
        },
    )
    route = router.route("inspect")
    assert route.model == "local-qwen"
    assert route.provider == "openai_compatible"
    assert router._models["local-qwen"].max_tokens == 4096
    assert router._models["local-qwen"].base_url == "http://127.0.0.1:8000/v1"
    # The custom price, not a registry default, drives the estimate.
    assert router.estimate_cost("inspect", 1_000_000, 0) == pytest.approx(0.10)


def test_custom_model_registry_does_not_leak_between_routers() -> None:
    """The registry is copied per router; one task's config must not mutate another's."""
    config = {
        "enabled": True,
        "custom_models": {"only-here": {"tier": "fast"}},
    }
    first = StageRouter("gateway-main", 100.0, stage_routing_config=config)
    second = StageRouter("gateway-main", 100.0, stage_routing_config={"enabled": True})
    assert "only-here" in first._models
    assert "only-here" not in second._models


# -- estimate_cost ----------------------------------------------------------


def test_estimate_cost_uses_the_routed_models_price() -> None:
    """gpt-4o is (2.50, 10.00, 1.25, 0.00) per 1M tokens, cache channels included."""
    cost = _router().estimate_cost(
        "planning", input_tokens=1_000_000, output_tokens=100_000, cache_read=2_000_000
    )
    assert cost == pytest.approx(2.5 + 1.0 + 2.5)


def test_estimate_cost_scales_with_the_stage_route_not_the_primary_model() -> None:
    """repair routes to o1 (15.00 in / 1M): the same million input tokens costs
    6x what the balanced tier costs, which is exactly why the repair stage has
    its own ceiling."""
    cheap = _router().estimate_cost("implement", 1_000_000, 0)
    expensive = _router().estimate_cost("repair", 1_000_000, 0)
    assert cheap == pytest.approx(2.5)
    assert expensive == pytest.approx(15.0)


def test_estimate_cost_of_a_model_outside_the_registry_is_zero_not_a_guess() -> None:
    """Zero means 'unknown price', and must never read as 'free model' in a
    cost report: the caller decides how to render it, the router just refuses
    to invent a price."""
    assert _router().estimate_cost("implement", 1, 0) == pytest.approx(2.5 / 1_000_000)
    assert (
        StageRouter("gateway-main", 100.0).estimate_cost("implement", 1_000_000, 0)
        == 0.0
    )


# -- the timeout surface web.py actually consumes -----------------------------


def test_route_timeouts_scale_the_configured_timeout_per_stage() -> None:
    """web.py passes route.timeout straight into the provider, so the factor
    table here is load-bearing: these numbers are the request deadlines."""
    router = _router()
    assert router.route("planning").timeout == 90.0
    assert router.route("inspect").timeout == 75.0
    assert router.route("implement").timeout == 100.0
    assert router.route("verify").timeout == 70.0
    assert router.route("repair").timeout == 100.0
    assert router.route("review").timeout == 80.0


def test_minimum_timeout_floor() -> None:
    assert StageRouter("gateway-main", 1.0).timeout == 10.0




# -- config surface: stage_routing -> Config ----------------------------------


@pytest.fixture()
def routing_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Isolated cwd + MINICC_HOME + workspace; MINICC_* never leaks in or out."""
    cwd = tmp_path / "cwd"
    home = tmp_path / "home"
    workspace = tmp_path / "ws"
    for directory in (cwd, home, workspace):
        directory.mkdir()
    monkeypatch.setenv("MINICC_HOME", str(home))
    monkeypatch.setenv("MINICC_API_KEY", "sk-test-key")
    monkeypatch.chdir(cwd)
    for key in [
        k
        for k in os.environ
        if k.startswith("MINICC_") and k not in {"MINICC_HOME", "MINICC_API_KEY"}
    ]:
        monkeypatch.delenv(key, raising=False)
    yield cwd, home, workspace
    # load_config exports .env MINICC_* keys into os.environ for subprocesses;
    # pop the routing key so it cannot leak into a later test's resolution.
    os.environ.pop("MINICC_STAGE_ROUTING", None)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_stage_routing_reads_a_nested_object_from_config_json(routing_env) -> None:
    """The object form is what real users write; it must arrive as a dict."""
    _cwd, home, workspace = routing_env
    payload = {"enabled": True, "tiers": {"balanced": ["claude-3.5-sonnet"]}}
    _write_json(home / "config.json", {"stage_routing": payload})
    config = load_config(workspace=workspace)
    assert config.stage_routing == payload
    # Recognized: no stray-key warning may fire for a key we own.
    assert config.unrecognized_config_keys == ()


def test_stage_routing_is_absent_by_default_and_routing_stays_inert(
    routing_env,
) -> None:
    """Nothing configured -> None -> the router keeps the primary model."""
    _cwd, _home, workspace = routing_env
    config = load_config(workspace=workspace)
    assert config.stage_routing is None
    router = StageRouter(
        config.model, config.timeout, stage_routing_config=config.stage_routing
    )
    for stage in ("planning", "inspect", "implement", "verify", "repair", "review"):
        assert router.route(stage).model == config.model, stage


def test_stage_routing_env_spelling_wins_over_the_file(
    routing_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Precedence parity with every other knob: environment beats the file."""
    _cwd, home, workspace = routing_env
    _write_json(
        workspace / ".minicc" / "config.json",
        {"stage_routing": {"enabled": False}},
    )
    monkeypatch.setenv("MINICC_STAGE_ROUTING", '{"enabled": true}')
    config = load_config(workspace=workspace)
    assert config.stage_routing == {"enabled": True}
    assert config.unrecognized_config_keys == ()


def test_stage_routing_env_spelling_inside_config_json_is_recognized(
    routing_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both spellings must work in config.json: MINICC_X like the env var."""
    _cwd, home, workspace = routing_env
    monkeypatch.delenv("MINICC_STAGE_ROUTING", raising=False)
    _write_json(
        home / "config.json",
        {"MINICC_STAGE_ROUTING": '{"enabled": true}'},
    )
    config = load_config(workspace=workspace)
    assert config.stage_routing == {"enabled": True}
    assert config.unrecognized_config_keys == ()


def test_stage_routing_dotenv_value_is_parsed_as_json(routing_env) -> None:
    """MINICC_STAGE_ROUTING={"enabled": true} in .env means the object."""
    cwd, _home, workspace = routing_env
    (cwd / ".env").write_text(
        'MINICC_STAGE_ROUTING={"enabled": true}\n', encoding="utf-8"
    )
    config = load_config(workspace=workspace)
    assert config.stage_routing == {"enabled": True}


@pytest.mark.parametrize("raw", ['{"enabled": true', "[42]", '"nope"'])
def test_broken_env_stage_routing_is_a_config_error_not_a_silent_default(
    routing_env, monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    """A typo here decides which model burns money: fail loudly at startup."""
    _cwd, _home, workspace = routing_env
    monkeypatch.setenv("MINICC_STAGE_ROUTING", raw)
    with pytest.raises(ConfigError):
        load_config(workspace=workspace)


@pytest.mark.parametrize("value", ["enabled", ["balanced"], 42, True])
def test_non_object_config_json_stage_routing_is_a_config_error(
    routing_env, value: object
) -> None:
    """A string/list/number/bool where the object belongs cannot mean anything.

    (An explicit null is different: the loader treats None as 'not
    configured', exactly like every other knob, so it stays routing-off.)"""
    _cwd, home, workspace = routing_env
    _write_json(home / "config.json", {"stage_routing": value})
    with pytest.raises(ConfigError):
        load_config(workspace=workspace)


def test_explicit_null_stage_routing_means_not_configured(routing_env) -> None:
    _cwd, home, workspace = routing_env
    _write_json(home / "config.json", {"stage_routing": None})
    config = load_config(workspace=workspace)
    assert config.stage_routing is None



# -- runtime wiring: AgentService hands Config.stage_routing to the router ----


class _EchoProvider:
    """Answers every chat instantly: enough for a read-only task to finish."""

    instances: list["_EchoProvider"] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.model = str(kwargs.get("model") or "")
        _EchoProvider.instances.append(self)

    @classmethod
    def is_transient_failure(cls, error: object) -> bool:
        return False

    def protocol(self) -> str:
        return "chat_completions"

    def protocol_status(self) -> dict[str, str]:
        return {"requested": "chat_completions", "active": "chat_completions"}

    async def chat(self, messages: object, tools: object, on_delta=None):  # noqa: ANN001, ANN201
        from minicc.llm.base import LLMResponse

        return LLMResponse(content="zhi-du-jian-cha-wan-cheng")

    async def close(self) -> None:
        return None


def _wired_service(tmp_path: Path, stage_routing: object):
    from minicc.web import AgentService

    return AgentService(
        tmp_path,
        SimpleNamespace(
            yolo=False,
            max_concurrent_tasks=2,
            sandbox_mode="host",
            sandbox_image="python:3.11-slim",
            base_url="https://example.test/v1",
            api_key="test-key",
            model="primary",
            timeout=10,
            tool_mode="auto",
            reasoning_effort="high",
            max_turns=4,
            compact_threshold=300_000,
            context_window_tokens=300_000,
            fallback_models=("backup-1", "backup-2"),
            stage_routing=stage_routing,
        ),
    )


def test_the_workbench_hands_config_stage_routing_to_the_router(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end: config object set by the operator reaches StageRouter.

    The tiers name a model that is nothing like the primary one, so any
    broken wiring shows up as the primary model in the emitted stage_route
    event. M11-T5: ``claude-3.5-sonnet`` is registered in the default
    registry with ``provider="anthropic"``, and the factory now honors the
    routed family - so the provider that must be constructed is the
    anthropic one, built with the routed model.
    """
    _EchoProvider.instances.clear()
    monkeypatch.setattr("minicc.web.AnthropicProvider", _EchoProvider)
    service = _wired_service(
        tmp_path,
        {
            "enabled": True,
            "tiers": {"balanced": ["claude-3.5-sonnet"]},
            "stage_map": {"planning": "balanced"},
        },
    )
    try:
        result = service._chat_locked(
            {
                "message": "zhi-du-jian-cha-ben-xiang-mu",
                "allow_changes": False,
                "workspace_path": str(tmp_path),
            },
            workspace=tmp_path,
        )
    finally:
        service.shutdown()
    events = result.get("events") or []
    route_events = [event for event in events if event.get("code") == "stage_route"]
    assert route_events, "expected a stage_route trace event"
    detail = route_events[0]["detail"]
    assert detail["model"] == "claude-3.5-sonnet"
    assert detail["model_tier"] == "balanced"
    assert detail["provider"] == "anthropic"
    # The event is a claim about the run: the provider must actually be built
    # with the routed model AND the routed family, otherwise enabling routing
    # changes nothing (or changes only the event stream).
    assert _EchoProvider.instances, "no provider was constructed for the task"
    assert _EchoProvider.instances[0].model == "claude-3.5-sonnet"


def test_the_workbench_uses_the_primary_model_when_stage_routing_is_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same path without the knob: legacy behavior, primary model everywhere."""
    _EchoProvider.instances.clear()
    monkeypatch.setattr("minicc.web.OpenAICompatibleProvider", _EchoProvider)
    service = _wired_service(tmp_path, None)
    try:
        result = service._chat_locked(
            {
                "message": "zhi-du-jian-cha-ben-xiang-mu",
                "allow_changes": False,
                "workspace_path": str(tmp_path),
            },
            workspace=tmp_path,
        )
    finally:
        service.shutdown()
    events = result.get("events") or []
    route_events = [event for event in events if event.get("code") == "stage_route"]
    assert route_events, "expected a stage_route trace event"
    assert route_events[0]["detail"]["model"] == "primary"
    assert _EchoProvider.instances, "no provider was constructed for the task"
    assert all(instance.model == "primary" for instance in _EchoProvider.instances)
    assert _EchoProvider.instances, "no provider was constructed"
    assert _EchoProvider.instances[0].model == "primary"

