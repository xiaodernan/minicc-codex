"""M11-T2 stage-route enforcement: the ceiling stops the run, not just the event.

T1 landed the wiring (route reaches the provider) and recorded the boundary
that ``max_cost_usd`` / ``max_turns`` reached only the ``stage_route`` event.
This file pins the enforcement half: the route that picked the model caps its
use. The decisive cells are behavioral - a run whose first charged turn crosses
the configured ceiling stops with a named budget error, and the same run
without the knob completes exactly as before.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from minicc.agent.loop import run_agent
from minicc.agent.router import ModelTier, StageRoute, StageRouter
from minicc.agent.state import Budget, BudgetExceeded
from minicc.llm.base import LLMResponse
from minicc.web import _stage_cost_estimator, _stage_route_budget


# -- Budget.record_cost -------------------------------------------------------


def test_record_cost_accumulates_and_trips_the_ceiling_by_name() -> None:
    budget = Budget(max_cost_usd=0.10)
    budget.record_cost(0.06)
    budget.record_cost(0.03)
    assert budget.cost_usd == pytest.approx(0.09)
    # The charge that crosses the line is refused at record time (add, then
    # check): the fourth slice lands on the ledger but the ceiling raises.
    with pytest.raises(BudgetExceeded) as excinfo:
        budget.record_cost(0.02)
    assert "阶段成本上限" in str(excinfo.value)
    assert budget.cost_usd == pytest.approx(0.11)


def test_a_negative_estimate_never_widens_the_remaining_budget() -> None:
    budget = Budget(max_cost_usd=0.10)
    budget.record_cost(-5.0)
    assert budget.cost_usd == 0.0


def test_budget_snapshot_carries_the_cost_fields() -> None:
    snapshot = Budget(max_cost_usd=0.5).snapshot()
    assert snapshot["max_cost_usd"] == 0.5
    assert snapshot["cost_usd"] == 0.0


# -- run_agent charges the estimator and stops past the ceiling ---------------


class _AnsweringProvider:
    """Answers every chat instantly; records how many times it was entered."""

    def __init__(self) -> None:
        self.entered = 0

    async def chat(self, messages, tools, on_delta=None):  # noqa: ANN001, ANN201
        self.entered += 1
        return LLMResponse(content="答案", usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})

    async def close(self) -> None:
        return None

    @staticmethod
    def is_transient_failure(error: object) -> bool:
        return False

    def protocol(self) -> str:
        return "chat_completions"

    def protocol_status(self) -> dict[str, str]:
        return {"requested": "chat_completions", "active": "chat_completions"}


def _min_registry(tmp_path: Path):
    from minicc.tools import Editor, build_registry

    return build_registry(Editor(tmp_path))


def test_a_charged_turn_past_the_ceiling_stops_the_loop_before_the_next_request(
    tmp_path: Path,
) -> None:
    provider = _AnsweringProvider()
    result = asyncio.run(
        run_agent(
            provider,  # type: ignore[arg-type]
            _min_registry(tmp_path),
            [{"role": "user", "content": "检查任务"}],
            budget=Budget(max_cost_usd=0.001),
            cost_estimator=lambda usage: 1.0,  # every turn is already over the ceiling
            should_allow=lambda _name, _call: True,
        )
    )
    assert provider.entered == 1, "the run must stop after the charged turn, not start another"
    assert result.error and "阶段成本上限已用尽" in result.error, result.error
    assert any(event.get("code") == "budget_exceeded" for event in result.trace_events)


def test_a_ceiling_without_an_estimator_never_trips_and_that_is_the_documented_shape(
    tmp_path: Path,
) -> None:
    """A ceiling alone enforces nothing: charging needs a price.

    This cell pins the boundary as behavior, so no one mistakes
    ``max_cost_usd`` for enforcement on a path that never charges. The web
    layer is the one that must always pair them, which the integration cells
    below prove.
    """
    provider = _AnsweringProvider()
    result = asyncio.run(
        run_agent(
            provider,  # type: ignore[arg-type]
            _min_registry(tmp_path),
            [{"role": "user", "content": "检查任务"}],
            budget=Budget(max_cost_usd=1e-9),
            should_allow=lambda _name, _call: True,
        )
    )
    assert result.error is None, result.error
    assert result.answer == "答案"
    assert provider.entered == 1


# -- _stage_route_budget: route caps govern, defaults fill the gap ------------


def _route(**overrides: object) -> StageRoute:
    values: dict[str, object] = {
        "stage": "planning",
        "model": "gateway-main",
        "model_tier": ModelTier.BALANCED,
        "timeout": 90.0,
    }
    values.update(overrides)
    return StageRoute(**values)  # type: ignore[arg-type]


def test_explicit_route_caps_override_the_builtin_defaults() -> None:
    budget = _stage_route_budget(
        _route(max_turns=3, max_cost_usd=0.25),
        default_max_turns=12,
        default_max_duration_seconds=300.0,
        soft_max_tokens=1000,
        soft_max_duration_seconds=None,
    )
    assert budget.max_turns == 3
    assert budget.max_cost_usd == pytest.approx(0.25)
    # The route says nothing about wall-clock or soft budgets: those stay
    # exactly what the caller configured.
    assert budget.max_duration_seconds == 300.0
    assert budget.soft_max_tokens == 1000


def test_a_legacy_route_reproduces_the_pre_routing_budget_exactly() -> None:
    """Routing off -> route caps absent -> byte-identical legacy behavior."""
    legacy = StageRouter("gateway-main", 100.0).route("planning")
    budget = _stage_route_budget(
        legacy,
        default_max_turns=12,
        default_max_duration_seconds=300.0,
        soft_max_tokens=1000,
        soft_max_duration_seconds=60.0,
    )
    assert budget.max_turns == 12
    assert budget.max_cost_usd is None
    assert budget.max_duration_seconds == 300.0
    assert budget.soft_max_tokens == 1000
    assert budget.soft_max_duration_seconds == 60.0
    assert budget.max_retries is None


def test_the_estimator_prices_at_the_routed_model_not_the_primary() -> None:
    router = StageRouter(
        "primary-model",
        100.0,
        stage_routing_config={
            "enabled": True,
            "tiers": {"balanced": ["gpt-4o"]},
            "stage_map": {"planning": "balanced"},
        },
    )
    estimate = _stage_cost_estimator(router, "planning")
    # gpt-4o input is 2.50 USD / 1M tokens: 1M prompt tokens -> 2.50.
    assert estimate({"prompt_tokens": 1_000_000, "completion_tokens": 0}) == pytest.approx(2.5)
    # Missing/None fields count as zero, never as a guess.
    assert estimate({}) == 0.0


# -- web wiring: the ceiling reaches the run through AgentService -------------


_ROUTING = {
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
}


class _EchoProvider:
    instances: list["_EchoProvider"] = []
    calls = 0

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
        _EchoProvider.calls += 1
        return LLMResponse(content="zhi-du-jian-cha-wan-cheng")

    async def close(self) -> None:
        return None


class _ToolLoopProvider:
    """Answers every agent turn with one readonly tool call, never with text.

    The completion judge rides the same provider with ``tools=None``; it gets
    the JSON decision shape, exactly like the shipped FakeProvider does.
    """

    instances: list["_ToolLoopProvider"] = []
    calls = 0

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.model = str(kwargs.get("model") or "")
        _ToolLoopProvider.instances.append(self)

    @classmethod
    def is_transient_failure(cls, error: object) -> bool:
        return False

    def protocol(self) -> str:
        return "chat_completions"

    def protocol_status(self) -> dict[str, str]:
        return {"requested": "chat_completions", "active": "chat_completions"}

    async def chat(self, messages: object, tools: object, on_delta=None):  # noqa: ANN001, ANN201
        _ToolLoopProvider.calls += 1
        if tools is None:
            return LLMResponse(
                content=json.dumps(
                    {
                        "status": "unknown",
                        "confidence": 0.1,
                        "rationale": "tool loop",
                        "missing": [],
                        "next_action": "",
                        "evidence": [],
                    }
                )
            )
        return LLMResponse(
            content="",
            tool_calls=[
                {
                    "id": "loop-1",
                    "type": "function",
                    "function": {"name": "tree", "arguments": "{}"},
                }
            ],
            finish_reason="tool_calls",
        )

    async def close(self) -> None:
        return None


def _wired_service(tmp_path: Path, stage_routing: object, *, max_turns: int = 4, **extra: object):
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
            max_turns=max_turns,
            compact_threshold=300_000,
            context_window_tokens=300_000,
            fallback_models=("backup-1", "backup-2"),
            stage_routing=stage_routing,
            **extra,
        ),
    )


def _run_task(service: Any, tmp_path: Path) -> dict[str, Any]:
    try:
        return service._chat_locked(
            {
                "message": "zhi-du-jian-cha-ben-xiang-mu",
                "allow_changes": False,
                "workspace_path": str(tmp_path),
            },
            workspace=tmp_path,
        )
    finally:
        service.shutdown()


def test_a_configured_planning_cost_ceiling_stops_the_run(tmp_path: Path) -> None:
    """End to end: ceiling 1e-6 with a 1000 USD/1M model trips on turn one."""
    _EchoProvider.instances.clear()
    _EchoProvider.calls = 0
    import minicc.web as web_module

    original = web_module.OpenAICompatibleProvider
    web_module.OpenAICompatibleProvider = _EchoProvider  # type: ignore[assignment]
    try:
        service = _wired_service(
            tmp_path,
            {**_ROUTING, "cost_limits_usd": {"planning": 0.000001}},
        )
        result = _run_task(service, tmp_path)
    finally:
        web_module.OpenAICompatibleProvider = original  # type: ignore[assignment]
    events = result.get("events") or []
    assert any("阶段成本上限已用尽" in json.dumps(event, ensure_ascii=False) for event in events), (
        "the ceiling must surface as a named budget error, not a generic failure"
    )
    assert any(event.get("code") == "budget_exceeded" for event in events)
    assert _EchoProvider.calls == 1, (
        "the run must not start another provider request after the charged turn"
    )


def test_without_the_knob_the_same_task_completes_exactly_as_before(tmp_path: Path) -> None:
    _EchoProvider.instances.clear()
    _EchoProvider.calls = 0
    import minicc.web as web_module

    original = web_module.OpenAICompatibleProvider
    web_module.OpenAICompatibleProvider = _EchoProvider  # type: ignore[assignment]
    try:
        service = _wired_service(tmp_path, None)
        result = _run_task(service, tmp_path)
    finally:
        web_module.OpenAICompatibleProvider = original  # type: ignore[assignment]
    events = result.get("events") or []
    assert not any(event.get("code") == "budget_exceeded" for event in events)
    assert _EchoProvider.calls >= 1


def test_a_configured_planning_turn_cap_tightens_the_run(tmp_path: Path) -> None:
    """max_turns: {planning: 1} - the route cap, not the config default, governs."""
    _ToolLoopProvider.instances.clear()
    _ToolLoopProvider.calls = 0
    import minicc.web as web_module

    original = web_module.OpenAICompatibleProvider
    web_module.OpenAICompatibleProvider = _ToolLoopProvider  # type: ignore[assignment]
    try:
        service = _wired_service(
            tmp_path,
            {**_ROUTING, "max_turns": {"planning": 1}},
        )
        result = _run_task(service, tmp_path)
    finally:
        web_module.OpenAICompatibleProvider = original  # type: ignore[assignment]
    events = result.get("events") or []
    assert any("最大模型轮次已用尽" in json.dumps(event, ensure_ascii=False) for event in events)
    assert _ToolLoopProvider.calls == 1, (
        "turn 2 must be refused by the budget before another request starts"
    )


def test_without_the_knob_the_tool_loop_runs_on_the_configured_default(tmp_path: Path) -> None:
    """Routing off -> config.max_turns (4) governs: 4 requests, then it stops."""
    _ToolLoopProvider.instances.clear()
    _ToolLoopProvider.calls = 0
    import minicc.web as web_module

    original = web_module.OpenAICompatibleProvider
    web_module.OpenAICompatibleProvider = _ToolLoopProvider  # type: ignore[assignment]
    try:
        service = _wired_service(tmp_path, None)
        result = _run_task(service, tmp_path)
    finally:
        web_module.OpenAICompatibleProvider = original  # type: ignore[assignment]
    assert _ToolLoopProvider.calls == 4, (
        f"the config default (4 turns) must still govern when routing is off: "
        f"{_ToolLoopProvider.calls}"
    )


# -- M11-T3: the review stage is a consumer, not a label ----------------------


def test_the_route_turn_cap_overrides_the_default_and_clamps_negatives() -> None:
    from minicc.web import _route_turn_cap

    assert _route_turn_cap(_route(max_turns=1), default=3) == 1
    assert _route_turn_cap(_route(max_turns=None), default=3) == 3
    # A misread must never widen the cap; 0 itself is meaningful
    # ("one attempt, then stop") and passes through.
    assert _route_turn_cap(_route(max_turns=-4), default=3) == 0
    assert _route_turn_cap(_route(max_turns=0), default=3) == 0


class _JudgeProbeProvider:
    """Tool-loop provider whose per-stage ledgers make the judge split real.

    Agent turns (first one only) emit one readonly tool call and then plain
    text, so ``run_agent`` converges without error and the completion judge
    actually runs. Every chat records which model served it: agent calls on
    one ledger, judge calls (``tools=None``) on another. The judge response
    carries the FakeProvider-shaped usage so the review-stage pricing has
    something real to charge.
    """

    instances: list["_JudgeProbeProvider"] = []
    agent_models: list[str] = []
    judge_models: list[str] = []

    @classmethod
    def reset(cls) -> None:
        cls.instances.clear()
        cls.agent_models.clear()
        cls.judge_models.clear()

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.model = str(kwargs.get("model") or "")
        self._turn = 0
        _JudgeProbeProvider.instances.append(self)

    @classmethod
    def is_transient_failure(cls, error: object) -> bool:
        return False

    def protocol(self) -> str:
        return "chat_completions"

    def protocol_status(self) -> dict[str, str]:
        return {"requested": "chat_completions", "active": "chat_completions"}

    async def chat(self, messages: object, tools: object, on_delta=None):  # noqa: ANN001, ANN201
        if tools is None:
            _JudgeProbeProvider.judge_models.append(self.model)
            return LLMResponse(
                content=json.dumps(
                    {
                        "status": "unknown",
                        "confidence": 0.1,
                        "rationale": "probe",
                        "missing": [],
                        "next_action": "",
                        "evidence": [],
                    }
                ),
                usage={"prompt_tokens": 200, "completion_tokens": 25, "total_tokens": 225},
            )
        _JudgeProbeProvider.agent_models.append(self.model)
        self._turn += 1
        if self._turn == 1:
            return LLMResponse(
                content="",
                tool_calls=[
                    {
                        "id": "probe-1",
                        "type": "function",
                        "function": {"name": "tree", "arguments": "{}"},
                    }
                ],
                finish_reason="tool_calls",
            )
        return LLMResponse(content="probe-answer")

    async def close(self) -> None:
        return None


_T3_ROUTING = {
    "enabled": True,
    "tiers": {"balanced": ["planning-one"], "fast": ["review-one"]},
    "custom_models": {
        "planning-one": {
            "tier": "balanced",
            "provider": "openai_compatible",
            "cost_usd_per_1m": [0.0, 0.0, 0.0, 0.0],
        },
        "review-one": {
            "tier": "fast",
            "provider": "openai_compatible",
            "cost_usd_per_1m": [0.0, 0.0, 0.0, 0.0],
        },
    },
    "stage_map": {"planning": "balanced", "review": "fast"},
}


def _run_with_probe(tmp_path: Path, stage_routing: object):
    import minicc.web as web_module

    _JudgeProbeProvider.reset()
    original = web_module.OpenAICompatibleProvider
    web_module.OpenAICompatibleProvider = _JudgeProbeProvider  # type: ignore[assignment]
    try:
        service = _wired_service(tmp_path, stage_routing)
        result = _run_task(service, tmp_path)
    finally:
        web_module.OpenAICompatibleProvider = original  # type: ignore[assignment]
    return result


def test_the_judge_serves_requests_on_the_review_model_not_the_planning_one(
    tmp_path: Path,
) -> None:
    """The review stage gets its own provider, built from the review route."""
    _run_with_probe(tmp_path, _T3_ROUTING)
    assert _JudgeProbeProvider.judge_models, "the judge must have served at least one review"
    assert set(_JudgeProbeProvider.judge_models) == {"review-one"}, (
        f"every judge request must ride the review-stage model: "
        f"{_JudgeProbeProvider.judge_models}"
    )
    assert _JudgeProbeProvider.agent_models, "the agent must have served at least one turn"
    assert set(_JudgeProbeProvider.agent_models) == {"planning-one"}, (
        f"agent turns stay on the planning model: {_JudgeProbeProvider.agent_models}"
    )
    # The probe judge answers "unknown", so the run ends with the reviewer
    # unavailable - that shape is asserted elsewhere. This cell is only about
    # which model served which call.


def test_review_spend_is_priced_at_the_review_model_and_trips_the_run_ceiling(
    tmp_path: Path,
) -> None:
    """The judge's usage is charged at review prices against the run ceiling.

    planning prices at 0, so only a review-priced charge can cross a 0.02
    ceiling; 25 completion tokens at 4000 USD/1M = 0.025. If the judge were
    still priced as planning, the run would complete - which is exactly the
    bug this cell forbids.
    """
    routing = {
        **_T3_ROUTING,
        "custom_models": {
            "planning-one": {"tier": "balanced", "provider": "openai_compatible",
                             "cost_usd_per_1m": [0.0, 0.0, 0.0, 0.0]},
            "review-one": {"tier": "fast", "provider": "openai_compatible",
                           "cost_usd_per_1m": [0.0, 4000.0, 0.0, 0.0]},
        },
        "cost_limits_usd": {"planning": 0.02},
    }
    result = _run_with_probe(tmp_path, routing)
    events = result.get("events") or []
    assert any("阶段成本上限已用尽" in json.dumps(event, ensure_ascii=False) for event in events), (
        "the judge-side charge crossing the run ceiling must surface as a named error"
    )
    assert any(event.get("code") == "budget_exceeded" for event in events)
    assert len(_JudgeProbeProvider.judge_models) == 1, (
        "the charged review must stop the run before a second judge call"
    )


def test_with_routing_off_the_judge_still_runs_on_the_configured_model(
    tmp_path: Path,
) -> None:
    """Legacy shape: one provider model everywhere, judge included."""
    result = _run_with_probe(tmp_path, None)
    assert _JudgeProbeProvider.judge_models, "the judge must still have run"
    assert set(_JudgeProbeProvider.judge_models) == {"primary"}, (
        f"routing off -> the configured model serves the judge too: "
        f"{_JudgeProbeProvider.judge_models}"
    )


# -- M11-T4: the repair stage is a consumer, not a relabel --------------------


class _RepairProbeProvider:
    """Writes, verifies green, then text - recording each turn's model.

    Scripted per instance, because the stage switch replaces the provider:

    - first instance (planning): write ``out.txt``, run the *passing* check
      (``run_agent``'s pre-finish guard only releases a text answer once a
      **passing** verification is on record), then answer;
    - later instances (repair): the recovery guard demands fresh readonly
      evidence before the run may end, so they alternate ``tree`` and text.

    The web-level verifier then runs the *failing* rule command, which is
    what triggers the repair stage in the first place.
    """

    agent_models: list[str] = []
    instance_count = 0
    probe_command = ""

    @classmethod
    def reset(cls) -> None:
        cls.agent_models.clear()
        cls.instance_count = 0

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.model = str(kwargs.get("model") or "")
        self._turn = 0
        _RepairProbeProvider.instance_count += 1
        self._seq = _RepairProbeProvider.instance_count

    @classmethod
    def is_transient_failure(cls, error: object) -> bool:
        return False

    def protocol(self) -> str:
        return "chat_completions"

    def protocol_status(self) -> dict[str, str]:
        return {"requested": "chat_completions", "active": "chat_completions"}

    def _tool(self, name: str, arguments: dict[str, Any], turn: int) -> LLMResponse:
        return LLMResponse(
            content="",
            tool_calls=[
                {
                    "id": f"repair-probe-{self._seq}-{turn}",
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(arguments)},
                }
            ],
            finish_reason="tool_calls",
        )

    async def chat(self, messages: object, tools: object, on_delta=None):  # noqa: ANN001, ANN201
        usage = {"prompt_tokens": 100, "completion_tokens": 25, "total_tokens": 125}
        if tools is None:
            return LLMResponse(
                content=json.dumps(
                    {"status": "unknown", "confidence": 0.1, "rationale": "probe",
                     "missing": [], "next_action": "", "evidence": []}
                ),
                usage=usage,
            )
        _RepairProbeProvider.agent_models.append(self.model)
        self._turn += 1
        if self._seq == 1:
            if self._turn == 1:
                return self._tool("write_file", {"path": "out.txt", "content": "probe"}, self._turn)
            if self._turn == 2:
                return self._tool("bash", {"command": _RepairProbeProvider.probe_command}, self._turn)
            return LLMResponse(content="planning-answer", usage=usage)
        # Repair-stage instances: alternate readonly evidence and text, as
        # the recovery guard requires, until the run stops for any reason.
        self._turn -= 1
        if self._turn % 2 == 1:
            return self._tool("tree", {}, self._turn)
        return LLMResponse(content="repair-answer", usage=usage)

    async def close(self) -> None:
        return None


def _failing_verification_workspace(tmp_path: Path, suite_python_bin: str) -> None:
    """A write-matching rule whose check always exits non-zero.

    ``passing_check.py`` exists only for the in-loop pre-finish guard (the
    probe runs it via bash); the *rule* runs ``failing_check.py`` so the
    web-level verifier fails and the repair stage engages.
    """
    (tmp_path / ".minicc").mkdir(exist_ok=True)
    (tmp_path / "passing_check.py").write_text("def test_pass():\n    assert True\n", encoding="utf-8")
    (tmp_path / "failing_check.py").write_text("def test_probe():\n    assert False\n", encoding="utf-8")
    (tmp_path / ".minicc" / "verification.json").write_text(
        json.dumps(
            {
                "rules": [
                    {
                        "paths": ["out.txt"],
                        "commands": [f"{suite_python_bin} -m pytest -q failing_check.py"],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


_REPAIR_ROUTING = {
    "enabled": True,
    "tiers": {"balanced": ["planning-one"], "fast": ["repair-one"]},
    "custom_models": {
        "planning-one": {
            "tier": "balanced",
            "provider": "openai_compatible",
            "cost_usd_per_1m": [0.0, 0.0, 0.0, 0.0],
        },
        "repair-one": {
            "tier": "fast",
            "provider": "openai_compatible",
            "cost_usd_per_1m": [0.0, 0.0, 0.0, 0.0],
        },
    },
    "stage_map": {"planning": "balanced", "repair": "fast"},
}


def _run_repair_probe(tmp_path: Path, suite_python_bin: str, stage_routing: object, **extra: object):
    import minicc.web as web_module

    _RepairProbeProvider.reset()
    _RepairProbeProvider.probe_command = f"{suite_python_bin} -m pytest -q passing_check.py"
    _failing_verification_workspace(tmp_path, suite_python_bin)
    original = web_module.OpenAICompatibleProvider
    web_module.OpenAICompatibleProvider = _RepairProbeProvider  # type: ignore[assignment]
    try:
        service = _wired_service(
            tmp_path, stage_routing, max_turns=8, max_repair_attempts=1, **extra
        )
        result = service._chat_locked(
            {
                "message": "zhi-du-jian-cha-ben-xiang-mu",
                "allow_changes": True,
                "workspace_path": str(tmp_path),
            },
            workspace=tmp_path,
        )
    finally:
        web_module.OpenAICompatibleProvider = original  # type: ignore[assignment]
        service.shutdown()
    return result


def test_the_repair_stage_serves_requests_on_the_repair_model(
    tmp_path: Path,
    suite_python_bin: str,
) -> None:
    """Verification failure flips the run onto the repair route's model."""
    result = _run_repair_probe(tmp_path, suite_python_bin, _REPAIR_ROUTING)
    events = result.get("events") or []
    assert any(event.get("code") == "repair_stage_provider" for event in events), (
        "the stage switch must be observable, not silent"
    )
    models = _RepairProbeProvider.agent_models
    # The planning instance served the write, the green check and the answer.
    assert models[:3] == ["planning-one"] * 3, f"planning turns first: {models}"
    assert "repair-one" in models, (
        f"the repair stage must serve at least one turn after the switch: {models}"
    )
    assert set(models) <= {"planning-one", "repair-one"}
    # Everything after the switch is repair-stage: the run is sticky.
    first_repair = models.index("repair-one")
    assert set(models[first_repair:]) == {"repair-one"}, (
        f"after the switch no planning turn may appear again: {models}"
    )


def test_repair_turns_are_priced_at_the_repair_model(tmp_path: Path, suite_python_bin: str) -> None:
    """A repair-priced charge crossing the run ceiling stops the run.

    planning prices at 0, so only repair-priced charges can cross 0.02;
    turn usage of 25 completion tokens at 4000 USD/1M = 0.1. If the repair
    turns were still priced as planning, the run would ride on to the
    recovery guard instead of stopping with a named budget error.
    """
    routing = {
        **_REPAIR_ROUTING,
        "custom_models": {
            "planning-one": {"tier": "balanced", "provider": "openai_compatible",
                             "cost_usd_per_1m": [0.0, 0.0, 0.0, 0.0]},
            "repair-one": {"tier": "fast", "provider": "openai_compatible",
                           "cost_usd_per_1m": [0.0, 4000.0, 0.0, 0.0]},
        },
        "cost_limits_usd": {"planning": 0.02},
    }
    result = _run_repair_probe(tmp_path, suite_python_bin, routing)
    events = result.get("events") or []
    assert any("阶段成本上限已用尽" in json.dumps(event, ensure_ascii=False) for event in events), (
        "the repair-priced charge must trip the ceiling by name"
    )
    assert any(event.get("code") == "budget_exceeded" for event in events)
    models = _RepairProbeProvider.agent_models
    assert models[:3] == ["planning-one"] * 3, f"planning turns first: {models}"
    assert models[-1] == "repair-one", (
        f"the charged turn ran on the repair model: {models}"
    )
    assert models.count("repair-one") == 1, (
        f"the charged repair turn must be the last request: {models}"
    )
