"""M8-T164 的行为见证：规划器调用的 USD 必须记入运行预算的成本账。

2026-10-08 实测缺陷（P0 探针，进程内、minicc.__file__ 已核）：运行预算的
``max_cost_usd`` 正是 planning 路线（规划器骑的那条路）的 ``cost_limits_usd``，
但规划器只 ``record_usage``（token），从不 ``record_cost`` —— 定价 $1000/1M 的
模型下这单花 $0.2，``metrics.budget.cost_usd`` 却恒为 0.0；$0.05 的上限被越过
且全程无声。修前 token 侧越限的形态也量过（P1 探针）：``record_usage`` 直接抛
``BudgetExceeded`` 逃出 ``_chat_locked``（生产里对应 TaskManager 的崩溃形状），
没有任何具名事件。

本门用定价 $1000/1M 的 custom model：规划器一单 200 token ⇒ $0.2；上限 $0.05
时应由规划器这一单自己撞线，发具名 planner budget_exceeded（detail.stage=planning），
随后主循环入口的 record_turn 把它转成受控停止——不再有未具名逃逸。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from minicc.agent.loop import TurnResult
from minicc.llm.base import LLMResponse
from minicc.web import AgentService

PLANNER_PROMPT_TOKENS = 100
PLANNER_COMPLETION_TOKENS = 100
PRICE_USD_PER_1M = 1000.0
EXPECTED_PLANNER_COST = (
    PLANNER_PROMPT_TOKENS + PLANNER_COMPLETION_TOKENS
) * PRICE_USD_PER_1M / 1_000_000
NODE_AGENT_MAX_TURNS = 12  # 节点预算的标记值；本门不跑 DAG，守卫只防误伤


def _priced_routing(planning_limit: float) -> dict:
    return {
        "enabled": True,
        "tiers": {
            "balanced": ["priced-model"],
            "fast": ["priced-model"],
            "reasoning": ["priced-model"],
        },
        "stage_map": {
            "planning": "balanced",
            "inspect": "fast",
            "verify": "fast",
            "repair": "balanced",
            "review": "balanced",
        },
        "cost_limits_usd": {
            "planning": planning_limit,
            "inspect": 1000.0,
            "verify": 1000.0,
            "repair": 1000.0,
            "review": 1000.0,
        },
        "custom_models": {
            "priced-model": {
                "provider": "openai",
                "tier": "balanced",
                "cost_usd_per_1m": [PRICE_USD_PER_1M, PRICE_USD_PER_1M, 0.0, 0.0],
                "max_tokens": 8192,
            },
        },
    }


def _completion_evidence_ids(messages) -> list[str]:
    """Fake reviewers must cite actual IDs from the review evidence packet."""
    return list(dict.fromkeys(re.findall(r'"id":"((?:event|verification)-\d+)"', str(messages))))[-8:]


def _run_priced_planner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    planning_limit: float,
    stub_main_agent: bool,
    arm_main_budget=None,
):
    (tmp_path / "notes.md").write_text("# 现状\n前后端分离。\n", encoding="utf-8")
    counts = {"planner": 0, "main": 0, "judge": 0}

    class FakeProvider:
        def __init__(self, *args, **kwargs) -> None:
            self.model = str(kwargs.get("model") or "")

        @classmethod
        def is_transient_failure(cls, error: object) -> bool:
            return False

        def protocol(self) -> str:
            return "chat_completions"

        def protocol_status(self) -> dict[str, str]:
            return {"requested": "chat_completions", "active": "chat_completions"}

        async def chat(self, messages, tools, on_delta=None):  # noqa: ANN001, ANN201
            rendered = json.dumps(messages, ensure_ascii=False)
            if "受约束任务规划器" in rendered:
                counts["planner"] += 1
                return LLMResponse(
                    content=json.dumps({
                        "name": "readonly-review",
                        "tasks": [
                            {"id": "inspect", "kind": "readonly", "allowed_tools": ["read_file", "grep"]},
                        ],
                    }, ensure_ascii=False),
                    usage={
                        "prompt_tokens": PLANNER_PROMPT_TOKENS,
                        "completion_tokens": PLANNER_COMPLETION_TOKENS,
                        "total_tokens": PLANNER_PROMPT_TOKENS + PLANNER_COMPLETION_TOKENS,
                    },
                )
            if tools is None:
                counts["judge"] += 1
                return LLMResponse(content=json.dumps({
                    "status": "complete",
                    "confidence": 0.9,
                    "rationale": "只读检查完成。",
                    "missing": [],
                    "next_action": "",
                    "evidence": _completion_evidence_ids(messages) or ["event-1"],
                }, ensure_ascii=False))
            counts["main"] += 1
            return LLMResponse(content="主智能体由捕获桩接管。")

        async def close(self) -> None:
            return None

    monkeypatch.setattr("minicc.web.OpenAICompatibleProvider", FakeProvider)
    if stub_main_agent:
        async def capturing_run_agent(provider, registry, messages, *, budget=None, max_turns=None, **kwargs):
            return TurnResult(answer="主智能体完成")

        monkeypatch.setattr("minicc.web.run_agent", capturing_run_agent)
    if arm_main_budget is not None:
        import minicc.web as web_module

        real_stage_route_budget = web_module._stage_route_budget

        def armed(route, **kwargs):
            budget = real_stage_route_budget(route, **kwargs)
            if kwargs.get("default_max_turns") != NODE_AGENT_MAX_TURNS:
                arm_main_budget(budget)
            return budget

        monkeypatch.setattr("minicc.web._stage_route_budget", armed)

    config = SimpleNamespace(
        yolo=False,
        max_concurrent_tasks=2,
        sandbox_mode="host",
        sandbox_image="python:3.11-slim",
        base_url="https://example.test/v1",
        api_key="test-key",
        model="test-model",
        timeout=10,
        tool_mode="auto",
        reasoning_effort="high",
        max_turns=4,
        compact_threshold=300_000,
        context_window_tokens=300_000,
        soft_max_tokens=5000,
        soft_max_duration_seconds=120.0,
        stage_routing=_priced_routing(planning_limit),
    )
    service = AgentService(tmp_path, config)
    try:
        result = service._chat_locked(
            {
                "message": "分析 src/app.py 和 web/app.js 的现状，运行验证并总结风险。",
                "session_id": "planner-cost-door",
                "allow_changes": True,
                "planner_requested": True,
                "workspace_path": str(tmp_path),
            },
            workspace=tmp_path,
        )
    finally:
        service.shutdown()
    return result, counts


def _planner_trips(result) -> list:
    return [
        event for event in result["events"]
        if event.get("code") == "budget_exceeded" and event.get("name") == "planner"
    ]


def test_planner_spend_lands_in_the_run_budget_cost(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, counts = _run_priced_planner(
        tmp_path, monkeypatch, planning_limit=1000.0, stub_main_agent=True
    )
    assert counts["planner"] == 1, f"规划器必须真跑过一单，实际 {counts['planner']} 次"
    budget = result["metrics"]["budget"]
    assert budget["cost_usd"] == pytest.approx(EXPECTED_PLANNER_COST), (
        "规划器骑 planning 路线，运行预算的成本上限就是这条路线配置的："
        f"这单 200 token × ${PRICE_USD_PER_1M}/1M 必须记 ${EXPECTED_PLANNER_COST} 进成本账；"
        f"实测 cost_usd={budget['cost_usd']!r}（修复前实测：恒为 0.0，规划器的钱不进任何成本账）"
    )
    assert budget["tokens"] == PLANNER_PROMPT_TOKENS + PLANNER_COMPLETION_TOKENS, (
        f"token 侧只应记规划器这一单 200：实测 {budget['tokens']}"
    )
    assert budget["tokens"] == result["tokens_used"]["total_tokens"], (
        "同一份载荷的两个 token 账必须同源："
        f"metrics.budget.tokens={budget['tokens']} vs "
        f"tokens_used.total_tokens={result['tokens_used']['total_tokens']}"
    )
    rows = [row for row in result["usage_by_turn"] if row.get("stage") == "planner"]
    assert len(rows) == 1 and rows[0].get("total_tokens") == PLANNER_PROMPT_TOKENS + PLANNER_COMPLETION_TOKENS, (
        f"用量表里必须恰有一行 stage=planner 且带完整细分：{rows!r}"
    )
    assert not _planner_trips(result) and not any(
        event.get("code") == "budget_exceeded" for event in result["events"]
    ), "未越限的一次记账不得伪造预算超限事件"


def test_planner_cost_trip_emits_named_event_and_stops_the_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """$0.05 上限撞上规划器这单 $0.2：具名事件 + 主循环受控停止。"""
    result, counts = _run_priced_planner(
        tmp_path, monkeypatch, planning_limit=0.05, stub_main_agent=False
    )
    assert counts["planner"] == 1, f"规划器必须真跑过一单，实际 {counts['planner']} 次"
    trips = _planner_trips(result)
    assert len(trips) == 1, (
        "规划器这单 $0.2 撞上 $0.05 上限时必须发且只发一条具名 planner budget_exceeded；"
        f"实测 {len(trips)} 条（事件里的预算超限集合："
        + "; ".join(
            f"name={event.get('name')!r} code={event.get('code')!r}"
            for event in result["events"] if event.get("code") == "budget_exceeded"
        ) + "）"
    )
    assert trips[0].get("detail", {}).get("stage") == "planning", (
        f"事件 detail 必须点名阶段是 planning（与 planner_dag 折叠区分）：{trips[0].get('detail')!r}"
    )
    assert "阶段成本上限已用尽" in str(trips[0].get("summary")), (
        f"事件自己的话必须点出成本上限：{trips[0].get('summary')!r}"
    )
    assert counts["main"] == 0, (
        "预算已在规划阶段耗尽：主循环入口的 record_turn 必须把它转成受控停止，"
        f"不得再发动模型请求；实测主 agent 调用 {counts['main']} 次"
    )
    assert any(
        "阶段成本上限已用尽" in json.dumps(event, ensure_ascii=False) for event in result["events"]
    ), "受控停止必须点名原因（与 test_stage_route_enforcement 的主循环触顶同款判据）"


def test_planner_token_trip_gets_the_same_named_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """token 侧（150 < 200）同款处理：具名事件，而不是修前的未具名逃逸。"""
    result, counts = _run_priced_planner(
        tmp_path,
        monkeypatch,
        planning_limit=1000.0,
        stub_main_agent=False,
        arm_main_budget=lambda budget: setattr(budget, "max_tokens", 150),
    )
    assert counts["planner"] == 1, f"规划器必须真跑过一单，实际 {counts['planner']} 次"
    trips = _planner_trips(result)
    assert len(trips) == 1, (
        "规划器 200 token 撞上运行预算的 150 token 上限时必须发具名 planner "
        "budget_exceeded；修前实测：BudgetExceeded 从规划器记账点直接逃出 "
        f"_chat_locked（崩溃形状）。实测 {len(trips)} 条"
    )
    assert trips[0].get("detail", {}).get("stage") == "planning", (
        f"事件 detail 必须点名阶段是 planning：{trips[0].get('detail')!r}"
    )
    assert "最大 token 预算已用尽" in str(trips[0].get("summary")), (
        f"事件自己的话必须点出 token 上限：{trips[0].get('summary')!r}"
    )
    assert counts["main"] == 0, (
        f"预算已在规划阶段耗尽，主 agent 不得再发动请求；实测 {counts['main']} 次"
    )
    assert any(
        "最大 token 预算已用尽" in json.dumps(event, ensure_ascii=False) for event in result["events"]
    ), "受控停止必须点名原因"
