"""M8-T165 的行为见证：批任务合并器的花费必须记入父任务的运行预算。

2026-10-08 实测缺陷（P0 探针，进程内、minicc.__file__ 已核）：T162/T163/T164
依次把 DAG 节点、task 子代理、规划器三个 LLM 面折叠/记入运行预算后，通查
provider.chat 的全部调用面，只剩 merge_batch（批任务合并器）一个面不碰任何
Budget：2 个子任务的批跑完后，父任务 tokens_used 1315（子树 1090 + 合并 225），
而进程内所有 Budget 实例合计只记过 1090——合并器那一单 225 token 没有任何
预算见过，0 条 budget_exceeded 事件，planning 路线的 max_cost_usd 与 token
上限对它完全失明。

修法（与 T162/T163/T164 同口径）：合并器骑父任务的运行预算（上限取 planning
路线，计价取真正服务这次调用的父任务模型——与 TaskRecord.snapshot 的
cost_usd 同一个定价函数），越限时不吞不抛穿，随载荷回报 budget_exceeded，
由 watcher 发具名事件（name=orchestrator / phase=merging / stage=merge）。

本门三例：
  C1 花费落账：合并器 225 token 的价与量都进父任务预算快照，且总量不重不漏；
  C2 成本越限：max_cost_usd 被合并单越过 ⇒ 恰一条具名事件，合好的答案照付；
  C3 token 越限：max_tokens 被合并单越过 ⇒ 同款具名事件（修前是静默）。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from minicc.task_manager import TERMINAL_TASK_STATUSES
from minicc.task_store import TaskStore
from minicc.web import AgentService

# The fake provider answers the merge's tools=None call with the usage shape
# its judge branch carries, so the merge face is a 225-token spend.
MERGE_TOKENS = 225
MERGE_COST = (200 * 1.0 + 25 * 2.0) / 1_000_000  # priced 1/2 per 1M by MINICC_PRICING_JSON


def _config() -> SimpleNamespace:
    return SimpleNamespace(
        yolo=False,
        max_concurrent_tasks=2,
        sandbox_mode="host",
        sandbox_image="python:3.11-slim",
        base_url="https://example.test/v1",
        api_key="Zx9q-not-a-real-key",
        model="test-model",
        timeout=10,
        tool_mode="auto",
        reasoning_effort="high",
        max_turns=4,
        compact_threshold=300_000,
        context_window_tokens=300_000,
        auto_resume_on_start=False,
    )


def _total(usage: Any) -> int:
    return int((usage or {}).get("total_tokens") or 0)


def _run_batch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    arm_merge_budget=None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """One real 2-child batch through the real service, offline provider.

    Children carry their own run budgets untouched; ``arm_merge_budget``
    (when given) rewrites only the parent's merge budget, mirroring how
    M8-T164's gate armed the main-loop budget.
    """
    monkeypatch.setenv("MINICC_FAKE_PROVIDER", "1")
    monkeypatch.setenv(
        "MINICC_PRICING_JSON", json.dumps({"test-model": {"input": 1.0, "output": 2.0}})
    )
    service = AgentService(tmp_path, _config(), task_store=TaskStore(tmp_path / "tasks.sqlite3"))
    if arm_merge_budget is not None:
        real_builder = getattr(service, "batch_merge_budget", None)
        if real_builder is None:
            # Pre-fix the merge face answers to no budget at all, so there is
            # nothing to arm. The batch still runs and must show the silent
            # trip this batch fixes - a behavioural red, not a setup error.
            pass
        else:
            def armed(model: str):
                budget, estimator = real_builder(model)
                arm_merge_budget(budget)
                return budget, estimator

            monkeypatch.setattr(service, "batch_merge_budget", armed)
    try:
        created = service.tasks.submit_batch({
            "messages": ["合并预算子任务一", "合并预算子任务二"],
            "session_id": "merge-cost-door",
            "workspace_path": str(tmp_path),
            "allow_changes": False,
        })
        parent_id = str(created.get("parent_task_id") or created.get("task_id"))
        deadline = time.time() + 90.0
        parent: dict[str, Any] = {}
        while time.time() < deadline:
            parent = service.tasks.get(parent_id)
            if str(parent.get("status")) in TERMINAL_TASK_STATUSES:
                break
            time.sleep(0.05)
        else:
            raise AssertionError(f"batch parent stuck in {parent.get('status')}")
        children = [service.tasks.get(str(cid)) for cid in created["task_ids"]]
        return parent, children
    finally:
        service.shutdown()


def _merge_trips(parent: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        event for event in parent.get("events") or []
        if isinstance(event, dict)
        and event.get("code") == "budget_exceeded"
        and event.get("name") == "orchestrator"
        and (event.get("detail") or {}).get("stage") == "merge"
    ]


def test_merge_spend_lands_in_the_parent_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent, children = _run_batch(tmp_path, monkeypatch)
    assert parent["status"] == "completed", f"batch parent ended {parent['status']}: {parent.get('error')}"
    budget = (parent.get("metrics") or {}).get("budget")
    assert isinstance(budget, dict), (
        "父任务是运行根：它自己的 LLM 面（合并器）记过的预算必须出现在 metrics 里；"
        f"实测 metrics={parent.get('metrics')!r}（修复前此处没有 budget，合并单不进任何账）"
    )
    assert budget["tokens"] == MERGE_TOKENS, (
        f"父任务预算只应记合并器这一单 225 token；实测 {budget['tokens']}"
    )
    assert budget["cost_usd"] == pytest.approx(MERGE_COST), (
        "合并器造价 $0.00025（定价 1/2 每 1M）必须进父任务预算的成本账；"
        f"实测 cost_usd={budget['cost_usd']!r}（修复前恒为没有这一项）"
    )
    child_tokens = sum(_total(child.get("tokens_used")) for child in children)
    assert _total(parent.get("tokens_used")) == child_tokens + MERGE_TOKENS, (
        "同一份载荷的两个 token 账必须同源：子树折叠 + 合并那一单，不重不漏；"
        f"实测父 {_total(parent.get('tokens_used'))} vs 子树 {child_tokens} + 合并 {MERGE_TOKENS}"
    )
    rows = [row for row in (parent.get("usage_by_turn") or []) if row.get("stage") == "merge"]
    assert len(rows) == 1 and _total(rows[0]) == MERGE_TOKENS, (
        f"用量表里必须恰有一行 stage=merge 且带完整细分：{rows!r}"
    )
    assert not _merge_trips(parent) and not any(
        event.get("code") == "budget_exceeded"
        for event in (parent.get("events") or [])
        if isinstance(event, dict)
    ), "未越限的一次记账不得伪造预算超限事件"


def test_merge_cost_trip_emits_named_event_and_keeps_the_merge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """$0.0001 上限撞上合并单 $0.00025：具名事件，答案照付。"""
    parent, _children = _run_batch(
        tmp_path, monkeypatch, arm_merge_budget=lambda budget: setattr(budget, "max_cost_usd", 0.0001)
    )
    assert parent["status"] == "completed", f"batch parent ended {parent['status']}: {parent.get('error')}"
    assert str(parent.get("answer") or "").strip(), (
        "合并这一单的钱已经花了：它的答案必须照常交付，越限是见证而不是丢弃已购的工作"
    )
    trips = _merge_trips(parent)
    assert len(trips) == 1, (
        "合并单越过 max_cost_usd 时必须发且只发一条具名 orchestrator budget_exceeded；"
        f"实测 {len(trips)} 条（事件里的预算超限集合："
        + "; ".join(
            f"name={event.get('name')!r} code={event.get('code')!r}"
            for event in parent.get("events") or []
            if isinstance(event, dict) and event.get("code") == "budget_exceeded"
        ) + "）"
    )
    assert trips[0].get("phase") == "merging", f"事件必须发生在 merging 阶段：{trips[0]!r}"
    assert "阶段成本上限已用尽" in str(trips[0].get("summary")), (
        f"事件自己的话必须点出成本上限：{trips[0].get('summary')!r}"
    )
    budget = (parent.get("metrics") or {}).get("budget")
    assert isinstance(budget, dict) and budget["cost_usd"] == pytest.approx(MERGE_COST), (
        "越限也先把这单如实记上：账必须是花过的钱，不是因为越限就消失；"
        f"实测 {budget!r}"
    )


def test_merge_token_trip_gets_the_same_named_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """token 侧（10 < 225）同款处理：具名事件，而不是修前的静默。"""
    parent, _children = _run_batch(
        tmp_path, monkeypatch, arm_merge_budget=lambda budget: setattr(budget, "max_tokens", 10)
    )
    assert parent["status"] == "completed", f"batch parent ended {parent['status']}: {parent.get('error')}"
    trips = _merge_trips(parent)
    assert len(trips) == 1, f"token 侧越限同样必须恰一条具名事件；实测 {len(trips)} 条"
    assert "最大 token 预算" in str(trips[0].get("summary")), (
        f"事件自己的话必须点出 token 上限：{trips[0].get('summary')!r}"
    )
    assert _total(parent.get("tokens_used")) > 0, "已花的 token 必须仍然计在任务账上"
