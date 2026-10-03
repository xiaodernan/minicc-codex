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


# -- M11-T8: the task subagent rides the inspect route -------------------------


class _TaskRoutingSentinel:
    """Serves the parent loop, and a second instance the task subagent.

    Per-instance init kwargs and chat ledger - the class-level
    ``init_kwargs`` of the sentinels above cannot tell two constructions
    apart. The parent answers its first agent turn with a ``task`` tool
    call and text afterwards; an instance built for the inspect model
    answers text immediately, so the subagent converges in one turn.
    """

    instances: list["_TaskRoutingSentinel"] = []

    @classmethod
    def reset(cls) -> None:
        cls.instances.clear()

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = dict(kwargs)
        self.model = str(kwargs.get("model") or "")
        self.chats = 0
        self.agent_turns = 0
        type(self).instances.append(self)

    @classmethod
    def is_transient_failure(cls, error: object) -> bool:
        return False

    def protocol(self) -> str:
        return "chat_completions"

    def protocol_status(self) -> dict[str, str]:
        return {"requested": "chat_completions", "active": "chat_completions"}

    async def chat(self, messages: object, tools: object, on_delta=None):  # noqa: ANN001, ANN201
        self.chats += 1
        usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        if self.model == "scout-one":
            return LLMResponse(content="侦察结论：README 描述了一个本地 coding agent。", usage=usage)
        self.agent_turns += 1
        if self.agent_turns == 1:
            return LLMResponse(
                tool_calls=[{
                    "id": "task-probe-1",
                    "type": "function",
                    "function": {"name": "task", "arguments": json.dumps({
                        "description": "调研项目结构说明",
                        "prompt": "读取 README.md 并总结项目用途。",
                    })},
                }],
                finish_reason="tool_calls",
                usage=usage,
            )
        return LLMResponse(content="cli-done", usage=usage)

    async def close(self) -> None:
        return None


_T8_INSPECT_ROUTING = {
    "enabled": True,
    "tiers": {"balanced": ["cheap-one"], "fast": ["scout-one"]},
    "custom_models": {
        "cheap-one": {"tier": "balanced", "provider": "openai_compatible"},
        "scout-one": {
            "tier": "fast",
            "provider": "openai_compatible",
            "base_url": "https://scout-gateway.test/v1",
            "api_key_env": "MINICC_T8_SCOUT_KEY",
        },
    },
    "stage_map": {"planning": "balanced", "inspect": "fast"},
}


def test_the_task_subagent_builds_and_serves_its_own_inspect_provider(
    cli_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MINICC_T8_SCOUT_KEY", "scout-key")
    _enable_routing(cli_env, _T8_INSPECT_ROUTING)
    _TaskRoutingSentinel.reset()
    import minicc.main as cli

    monkeypatch.setattr(cli, "OpenAICompatibleProvider", _TaskRoutingSentinel)
    _run_cli(cli_env)
    instances = _TaskRoutingSentinel.instances
    assert len(instances) == 2, (
        f"exactly the parent and one inspect provider must exist: "
        f"{[i.kwargs.get('model') for i in instances]}"
    )
    parent, scout = instances[0], instances[1]
    assert parent.kwargs["model"] == "cheap-one", parent.kwargs
    assert parent.agent_turns == 2, "turn 1 issues the task call, turn 2 the answer"
    assert scout.kwargs["model"] == "scout-one", scout.kwargs
    assert scout.kwargs["base_url"] == "https://scout-gateway.test/v1", scout.kwargs
    assert scout.kwargs["api_key"] == "scout-key", scout.kwargs
    # The inspect factor (0.75 x the 180s config timeout) governs the
    # subagent provider; the planning factor (0.9) governs the parent.
    assert scout.kwargs["timeout"] == pytest.approx(135.0), scout.kwargs
    assert parent.kwargs["timeout"] == pytest.approx(162.0), parent.kwargs
    assert scout.chats >= 1, "the subagent must actually serve on the inspect model"


def test_with_routing_off_the_subagent_reuses_the_parent_provider(
    cli_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _TaskRoutingSentinel.reset()
    import minicc.main as cli

    monkeypatch.setattr(cli, "OpenAICompatibleProvider", _TaskRoutingSentinel)
    _run_cli(cli_env)
    instances = _TaskRoutingSentinel.instances
    assert len(instances) == 1, (
        f"routing off -> the task factory returns the parent instance, never builds: "
        f"{[i.kwargs.get('model') for i in instances]}"
    )
    parent = instances[0]
    # Parent turn 1 (the task call) + the subagent's own turn on the same
    # instance + parent turn 2 (the answer): three chats, one provider.
    assert parent.chats == 3, f"one instance must serve every chat: {parent.chats}"


def test_a_missing_inspect_credential_refuses_the_cli_before_any_provider(
    cli_env: Path, sentinels, capsys: pytest.CaptureFixture[str]
) -> None:
    _enable_routing(
        cli_env,
        {
            **_T8_INSPECT_ROUTING,
            "custom_models": {
                "cheap-one": {"tier": "balanced", "provider": "openai_compatible"},
                "scout-one": {
                    "tier": "fast",
                    "provider": "anthropic",
                    "api_key_env": "MINICC_T8_MISSING_SCOUT_KEY",
                },
            },
        },
    )
    with pytest.raises(SystemExit) as excinfo:
        main(["--workspace", str(cli_env), "--no-stream", "你好"])
    assert excinfo.value.code == 2
    assert "MINICC_T8_MISSING_SCOUT_KEY" in capsys.readouterr().err
    assert _OpenAISentinel.instances == [] and _AnthroSentinel.instances == [], (
        "the refusal must happen before any provider exists - the inspect one included"
    )


# -- M11-T9: the inspect route's caps govern the CLI subagent's budget ---------


class _CeilingCliSentinel:
    """The scout instance issues tool calls with 1M-token usage, never text."""

    instances: list["_CeilingCliSentinel"] = []
    scout_chats = 0

    @classmethod
    def reset(cls) -> None:
        cls.instances.clear()
        cls.scout_chats = 0

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = dict(kwargs)
        self.model = str(kwargs.get("model") or "")
        self.agent_turns = 0
        type(self).instances.append(self)

    @classmethod
    def is_transient_failure(cls, error: object) -> bool:
        return False

    def protocol(self) -> str:
        return "chat_completions"

    def protocol_status(self) -> dict[str, str]:
        return {"requested": "chat_completions", "active": "chat_completions"}

    async def chat(self, messages: object, tools: object, on_delta=None):  # noqa: ANN001, ANN201
        if self.model == "scout-one":
            type(self).scout_chats += 1
            return LLMResponse(
                tool_calls=[{
                    "id": f"cli-ceiling-{type(self).scout_chats}",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path": "README.md"}'},
                }],
                finish_reason="tool_calls",
                usage={"prompt_tokens": 1_000_000, "completion_tokens": 0, "total_tokens": 1_000_000},
            )
        self.agent_turns += 1
        if self.agent_turns == 1:
            return LLMResponse(
                tool_calls=[{
                    "id": "cli-ceiling-parent",
                    "type": "function",
                    "function": {"name": "task", "arguments": json.dumps({
                        "description": "调研项目结构说明",
                        "prompt": "读取 README.md 并总结项目用途。",
                    })},
                }],
                finish_reason="tool_calls",
            )
        return LLMResponse(content="cli-done")

    async def close(self) -> None:
        return None


def test_the_inspect_cost_ceiling_stops_the_cli_subagent(
    cli_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (cli_env / "README.md").write_text("# demo project\n", encoding="utf-8")
    monkeypatch.setenv("MINICC_T8_SCOUT_KEY", "scout-key")
    _enable_routing(
        cli_env,
        {
            **_T8_INSPECT_ROUTING,
            "custom_models": {
                "cheap-one": {"tier": "balanced", "provider": "openai_compatible"},
                # 1M prompt tokens at 1000 USD/1M = 1000 USD per charged turn -
                # the 0.001 inspect ceiling trips on the child's first turn.
                "scout-one": {
                    "tier": "fast",
                    "provider": "openai_compatible",
                    "base_url": "https://scout-gateway.test/v1",
                    "api_key_env": "MINICC_T8_SCOUT_KEY",
                    "cost_usd_per_1m": [1000.0, 1000.0, 0.0, 0.0],
                },
            },
            "cost_limits_usd": {"inspect": 0.001},
        },
    )
    _CeilingCliSentinel.reset()
    import minicc.main as cli

    monkeypatch.setattr(cli, "OpenAICompatibleProvider", _CeilingCliSentinel)
    _run_cli(cli_env)
    models = [i.kwargs.get("model") for i in _CeilingCliSentinel.instances]
    assert "scout-one" in models, f"the inspect provider must be built: {models}"
    assert _CeilingCliSentinel.scout_chats == 1, (
        f"the child's charged turn must be its last: {_CeilingCliSentinel.scout_chats}"
    )


# -- M11-T10: the CLI subagent's lifecycle reaches the structured log ----------


def test_the_subagent_lifecycle_is_logged_on_the_cli(
    cli_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MINICC_T8_SCOUT_KEY", "scout-key")
    _enable_routing(cli_env, _T8_INSPECT_ROUTING)
    _TaskRoutingSentinel.reset()
    import minicc.main as cli

    monkeypatch.setattr(cli, "OpenAICompatibleProvider", _TaskRoutingSentinel)
    logged: list[dict[str, Any]] = []
    monkeypatch.setattr(cli, "log_task_event", lambda event, **_: logged.append(event))
    _run_cli(cli_env)
    subagent_codes = {e.get("code") for e in logged if e.get("name") == "subagent"}
    assert "subagent_started" in subagent_codes, (
        f"the child's start must reach the structured log: {subagent_codes}"
    )
    assert "subagent_finished" in subagent_codes, (
        f"the child's completion must reach the structured log: {subagent_codes}"
    )
