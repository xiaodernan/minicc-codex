"""M11-T7 CLI stage routing: the parsed knob drives the CLI's provider too.

``MINICC_STAGE_ROUTING`` was parsed by ``load_config`` and advertised by the
README, but ``minicc.main`` built its provider from raw config - an entire
surface where the knob was silently inert. These gates pin the wiring on the
CLI surface with the same lazy guarantees the web surface already has:
routing off keeps the legacy construction call byte-for-byte, and every
routed change is visible (model, wire family, credential, budget) or refused
(unknown provider, missing credential) before anything runs.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from minicc.llm.base import LLMResponse
from minicc.main import main


@pytest.fixture()
def cli_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated MINICC_HOME + workspace, like the project-config gates."""
    home = tmp_path / "home"
    workspace = tmp_path / "ws"
    home.mkdir()
    workspace.mkdir()
    monkeypatch.setenv("MINICC_HOME", str(home))
    monkeypatch.setenv("MINICC_API_KEY", "sk-deploy-key")
    monkeypatch.setenv("MINICC_BASE_URL", "https://deploy-gateway.test/v1")
    monkeypatch.setenv("MINICC_MODEL", "terra-main")
    monkeypatch.setenv("MINICC_REASONING_EFFORT", "high")
    monkeypatch.setenv("MINICC_TIMEOUT", "180")
    keep = {
        "MINICC_HOME",
        "MINICC_API_KEY",
        "MINICC_BASE_URL",
        "MINICC_MODEL",
        "MINICC_REASONING_EFFORT",
        "MINICC_TIMEOUT",
    }
    for key in [k for k in os.environ if k.startswith("MINICC_") and k not in keep]:
        monkeypatch.delenv(key)
    return workspace


class _OpenAISentinel:
    """Stands in for the deployment's openai-compatible provider."""

    instances: list["_OpenAISentinel"] = []
    init_kwargs: dict[str, Any] = {}

    def __init__(self, **kwargs: Any) -> None:
        type(self).init_kwargs = dict(kwargs)
        type(self).instances.append(self)

    @classmethod
    def reset(cls) -> None:
        cls.instances = []
        cls.init_kwargs = {}

    @classmethod
    def is_transient_failure(cls, error: object) -> bool:
        return False

    def protocol(self) -> str:
        return "chat_completions"

    def protocol_status(self) -> dict[str, str]:
        return {"requested": "chat_completions", "active": "chat_completions"}

    async def chat(self, messages: object, tools: object, on_delta=None):  # noqa: ANN001, ANN201
        return LLMResponse(content="cli-ok", usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})

    async def close(self) -> None:
        return None


class _AnthroSentinel(_OpenAISentinel):
    """Stands in for AnthropicProvider; records construction separately."""

    instances: list["_AnthroSentinel"] = []  # type: ignore[assignment]
    init_kwargs: dict[str, Any] = {}  # type: ignore[assignment]


@pytest.fixture()
def sentinels(monkeypatch: pytest.MonkeyPatch):
    _OpenAISentinel.reset()
    _AnthroSentinel.reset()
    import minicc.main as cli

    monkeypatch.setattr(cli, "OpenAICompatibleProvider", _OpenAISentinel)
    # main.py imports AnthropicProvider inside the branch, so the patch must
    # sit on the source module for the local import to resolve the sentinel.
    monkeypatch.setattr(
        "minicc.llm.anthropic_provider.AnthropicProvider", _AnthroSentinel, raising=False
    )
    logged: list[dict[str, Any]] = []
    monkeypatch.setattr(cli, "log_task_event", lambda event, **_: logged.append(event))
    return logged


def _enable_routing(workspace: Path, config: dict[str, Any]) -> None:
    (workspace / ".minicc").mkdir(exist_ok=True)
    (workspace / ".minicc" / "config.json").write_text(
        json.dumps({"stage_routing": config}), encoding="utf-8"
    )


def _run_cli(workspace: Path) -> None:
    exit_code = main(["--workspace", str(workspace), "--no-stream", "你好"])
    assert exit_code == 0


def test_routing_off_builds_the_deployment_provider_byte_for_byte(cli_env: Path, sentinels) -> None:
    _run_cli(cli_env)
    kwargs = _OpenAISentinel.init_kwargs
    assert kwargs["model"] == "terra-main"
    assert kwargs["base_url"] == "https://deploy-gateway.test/v1"
    assert kwargs["api_key"] == "sk-deploy-key"
    assert kwargs["reasoning_effort"] == "high"
    assert kwargs["timeout"] == 180.0
    assert _AnthroSentinel.instances == []
    assert not [e for e in sentinels if e.get("code") == "stage_route"], (
        "a routing-less run must not pretend a route was applied"
    )


def test_the_planning_route_drives_the_cli_provider(cli_env: Path, sentinels) -> None:
    _enable_routing(
        cli_env,
        {
            "enabled": True,
            "tiers": {"balanced": ["cheap-one"]},
            "custom_models": {
                "cheap-one": {"tier": "balanced", "provider": "openai_compatible"}
            },
            "stage_map": {"planning": "balanced"},
        },
    )
    _run_cli(cli_env)
    kwargs = _OpenAISentinel.init_kwargs
    assert kwargs["model"] == "cheap-one", "the routed model must be the one built"
    assert kwargs["api_key"] == "sk-deploy-key"
    route_events = [e for e in sentinels if e.get("code") == "stage_route"]
    assert route_events and route_events[0]["detail"]["model"] == "cheap-one"


def test_a_cross_family_card_serves_the_cli_run(cli_env: Path, sentinels, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINICC_T7_CLAUDE_KEY", "vendor-key")
    _enable_routing(
        cli_env,
        {
            "enabled": True,
            "tiers": {"balanced": ["claude-side"]},
            "custom_models": {
                "claude-side": {
                    "tier": "balanced",
                    "provider": "anthropic",
                    "base_url": "https://claude-gateway.test/v1",
                    "api_key_env": "MINICC_T7_CLAUDE_KEY",
                }
            },
            "stage_map": {"planning": "balanced"},
        },
    )
    _run_cli(cli_env)
    kwargs = _AnthroSentinel.init_kwargs
    assert kwargs["model"] == "claude-side"
    assert kwargs["base_url"] == "https://claude-gateway.test/v1"
    assert kwargs["api_key"] == "vendor-key"
    assert _OpenAISentinel.instances == [], "the deployment wire must not be built for another family"


def test_a_missing_card_credential_refuses_the_cli_run_before_any_provider(
    cli_env: Path, sentinels, capsys: pytest.CaptureFixture[str]
) -> None:
    _enable_routing(
        cli_env,
        {
            "enabled": True,
            "tiers": {"balanced": ["claude-side"]},
            "custom_models": {
                "claude-side": {
                    "tier": "balanced",
                    "provider": "anthropic",
                    "api_key_env": "MINICC_T7_MISSING_KEY",
                }
            },
            "stage_map": {"planning": "balanced"},
        },
    )
    with pytest.raises(SystemExit) as excinfo:
        main(["--workspace", str(cli_env), "--no-stream", "你好"])
    assert excinfo.value.code == 2
    assert "MINICC_T7_MISSING_KEY" in capsys.readouterr().err
    assert _OpenAISentinel.instances == [] and _AnthroSentinel.instances == [], (
        "the refusal must happen before any provider exists"
    )


def test_the_planning_turn_cap_and_ceiling_reach_the_cli_budget(
    cli_env: Path, sentinels, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}

    async def _stub_run_agent(provider, registry, messages, **kwargs):  # noqa: ANN001, ANN202
        captured["budget"] = kwargs.get("budget")
        captured["cost_estimator"] = kwargs.get("cost_estimator")
        from minicc.agent.loop import TurnResult

        return TurnResult(answer="cli-ok")

    import minicc.main as cli

    monkeypatch.setattr(cli, "run_agent", _stub_run_agent)
    _enable_routing(
        cli_env,
        {
            "enabled": True,
            "tiers": {"balanced": ["pricey-one"]},
            "custom_models": {
                "pricey-one": {
                    "tier": "balanced",
                    "provider": "openai_compatible",
                    "cost_usd_per_1m": [1000.0, 1000.0, 0.0, 0.0],
                }
            },
            "stage_map": {"planning": "balanced"},
            "max_turns": {"planning": 3},
            "cost_limits_usd": {"planning": 0.25},
        },
    )
    _run_cli(cli_env)
    budget = captured["budget"]
    assert budget.max_turns == 3
    assert budget.max_cost_usd == pytest.approx(0.25)
    assert callable(captured["cost_estimator"])
    # The estimator prices at the routed model, not the primary.
    assert captured["cost_estimator"]({"prompt_tokens": 1_000_000, "completion_tokens": 0}) == pytest.approx(1000.0)


def test_the_legacy_turn_budget_survives_when_routing_is_off(
    cli_env: Path, sentinels, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}

    async def _stub_run_agent(provider, registry, messages, **kwargs):  # noqa: ANN001, ANN202
        captured["budget"] = kwargs.get("budget")
        captured["cost_estimator"] = kwargs.get("cost_estimator")
        from minicc.agent.loop import TurnResult

        return TurnResult(answer="cli-ok")

    import minicc.main as cli

    monkeypatch.setattr(cli, "run_agent", _stub_run_agent)
    _run_cli(cli_env)
    budget = captured["budget"]
    assert budget.max_turns is None
    assert budget.max_tool_calls is None
    assert budget.max_cost_usd is None
    assert captured["cost_estimator"] is None


def test_an_unknown_tier_model_degrades_to_the_primary_on_the_cli(cli_env: Path, sentinels) -> None:
    _enable_routing(
        cli_env,
        {
            "enabled": True,
            "tiers": {"fast": ["not-a-registered-model"]},
            "stage_map": {"planning": "fast"},
        },
    )
    _run_cli(cli_env)
    assert _OpenAISentinel.init_kwargs["model"] == "terra-main", (
        "the router's degrade-to-primary semantics must hold on the CLI surface too"
    )
