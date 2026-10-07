"""M6-T2 回填的行为见证：DAG 节点的花费必须落回运行预算。

2026-10-08 实测缺陷（probe，进程内、minicc.__file__ 已核）：同一份载荷里
``metrics.budget.tokens`` 只有规划器的 18，而 ``tokens_used.total_tokens``
是 1400018 —— 两个数字相差的正好是两个 DAG 节点的花费，运行预算从不知道
节点花了钱，软上限也永远不响。

本门用捕获桩把每节点花费固定为 700k：节点预算与主运行预算都由
``_stage_route_budget`` 产出，桩按 ``max_turns == 12``（NODE_AGENT_MAX_TURNS）
区分节点调用。
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

NODE_TOKENS = 700_000
NODE_TURNS = 12
PLANNER_TOKENS = 18


def _completion_evidence_ids(messages) -> list[str]:
    """Fake reviewers must cite actual IDs from the review evidence packet."""
    return list(dict.fromkeys(re.findall(r'"id":"((?:event|verification)-\d+)"', str(messages))))[-8:]


def _run_readonly_plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, arm_main_budget=None):
    (tmp_path / "notes.md").write_text("# 现状\n前后端分离。\n", encoding="utf-8")
    captured: list[dict[str, object]] = []

    class FakeProvider:
        def __init__(self, **_kwargs) -> None:
            pass

        async def chat(self, messages, tools, on_delta=None):
            rendered = json.dumps(messages, ensure_ascii=False)
            if "受约束任务规划器" in rendered:
                return LLMResponse(
                    content=json.dumps({
                        "name": "readonly-review",
                        "tasks": [
                            {"id": "inspect", "kind": "readonly", "allowed_tools": ["read_file", "grep"]},
                            {"id": "review", "kind": "review", "depends_on": ["inspect"], "allowed_tools": ["git_diff"]},
                        ],
                    }, ensure_ascii=False),
                    usage={"prompt_tokens": 10, "completion_tokens": 8, "total_tokens": PLANNER_TOKENS},
                )
            if tools is None:
                return LLMResponse(content=json.dumps({
                    "status": "complete",
                    "confidence": 0.9,
                    "rationale": "只读检查完成。",
                    "missing": [],
                    "next_action": "",
                    "evidence": _completion_evidence_ids(messages) or ["event-1"],
                }, ensure_ascii=False))
            return LLMResponse(content="主智能体由捕获桩接管。")

        async def close(self) -> None:
            return None

    async def capturing_run_agent(provider, registry, messages, *, budget=None, max_turns=None, **kwargs):
        captured.append({"max_turns": max_turns, "budget": budget})
        if max_turns == NODE_TURNS:
            return TurnResult(answer="节点完成", tokens_used={"total_tokens": NODE_TOKENS})
        return TurnResult(answer="主智能体完成")

    monkeypatch.setattr("minicc.web.OpenAICompatibleProvider", FakeProvider)
    monkeypatch.setattr("minicc.web.run_agent", capturing_run_agent)
    if arm_main_budget is not None:
        import minicc.web as web_module

        real_stage_route_budget = web_module._stage_route_budget

        def armed(route, **kwargs):
            budget = real_stage_route_budget(route, **kwargs)
            if kwargs.get("default_max_turns") != NODE_TURNS:
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
    )
    service = AgentService(tmp_path, config)
    try:
        result = service._chat_locked(
            {
                "message": "分析 src/app.py 和 web/app.js 的现状，运行验证并总结风险。",
                "session_id": "dag-fold-door",
                "allow_changes": False,
                "workspace_path": str(tmp_path),
            },
            workspace=tmp_path,
        )
    finally:
        service.shutdown()
    return result, captured


def test_dag_node_spend_lands_in_the_run_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, captured = _run_readonly_plan(tmp_path, monkeypatch)
    node_calls = [entry for entry in captured if entry["max_turns"] == NODE_TURNS]
    assert len(node_calls) == 2, (
        f"计划的两个节点必须各跑一次 run_agent（各花 {NODE_TOKENS} token）；"
        f"实际捕获 {len(node_calls)} 次节点调用"
    )
    node_spend = 2 * NODE_TOKENS
    budget = result["metrics"]["budget"]
    assert budget["tokens"] == PLANNER_TOKENS + node_spend, (
        "运行预算必须记入 DAG 节点花费："
        f"预算里 tokens={budget['tokens']}，应为规划器 {PLANNER_TOKENS} + 节点 {node_spend}；"
        "（修复前实测：节点花得再多，运行预算也只有规划器那 18）"
    )
    assert budget["tokens"] == result["tokens_used"]["total_tokens"], (
        "同一份载荷里的两个 token 数字必须来自同一次记账："
        f"metrics.budget.tokens={budget['tokens']} vs "
        f"tokens_used.total_tokens={result['tokens_used']['total_tokens']}"
    )
    assert budget["tokens"] >= budget["soft_max_tokens"], (
        "节点花费已越过软上限，运行预算必须知道（软上限驱动收尾提示）："
        f"tokens={budget['tokens']} vs soft_max_tokens={budget['soft_max_tokens']}"
    )
    trips = [
        event for event in result["events"]
        if event.get("code") == "budget_exceeded" and event.get("name") == "planner"
    ]
    assert not trips, (
        "未越硬界的一次折叠不得伪造预算超限事件："
        + "; ".join(str(event.get("summary")) for event in trips[:3])
    )


def test_dag_fold_trip_emits_named_planner_budget_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M6-T2：「超限发 planner budget_exceeded trace 而非静默」。"""
    result, _ = _run_readonly_plan(
        tmp_path,
        monkeypatch,
        arm_main_budget=lambda budget: setattr(budget, "max_tokens", 1000),
    )
    tripped = [
        event for event in result["events"]
        if event.get("code") == "budget_exceeded" and event.get("name") == "planner"
    ]
    assert tripped, (
        "折叠越限必须发具名 planner budget_exceeded 事件，不能静默；"
        "本次事件里的 code 集合："
        + "; ".join(sorted({str(event.get("code")) for event in result["events"]}))
    )
    assert tripped[0].get("detail", {}).get("stage") == "planner_dag", (
        "事件 detail 必须点名阶段是 planner_dag（与规划器自身超限区分）："
        f"{tripped[0].get('detail')!r}"
    )
