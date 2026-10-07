"""M8-T163 的行为见证：task 子代理的花费必须折叠回运行预算（T162 同类第三例）。

2026-10-08 实测（进程内 probe，minicc.__file__ 已核）：主循环调用 task 工具跑完一个
子代理花了 700000 token，``subagent_finished.detail.tokens_used`` 看得到 700000，
但同一份载荷里的 ``result.tokens_used.total_tokens`` 与 ``metrics.budget.tokens``
都只有 28（主 10+11 + 评委 7）——运行预算从不知道子代理花了钱，软上限也不响；
M6-T2 行的「计入父预算」对这条路径是假的（DAG 节点与评委在前两次收账中已修）。

折叠只算 token 侧：成本天花板按阶段各管各的（子代理有自己的 inspect 级
max_cost_usd 预算，M11-T9），运行预算不重复计价——与 T162 的 DAG 折叠同口径。

CLI 面的两条见证在 tests/test_cli_stage_routing.py（M8-T163 段）：打印的用量行
把子代理花费带出去，折叠越限发具名 budget_exceeded 进结构化日志。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from minicc.agent.state import BudgetExceeded
from minicc.agent.subagent import build_task_tool_spec
from minicc.llm.base import LLMResponse
from minicc.tools import Editor, build_registry
from minicc.web import AgentService

SUB_TOKENS = 700_000
SUB_USAGE = {"prompt_tokens": 400_000, "completion_tokens": 300_000, "total_tokens": SUB_TOKENS}


# -- web 全链路：一份载荷里的两个数字必须同源 --------------------------------


def _completion_evidence_ids(messages) -> list[str]:
    return list(dict.fromkeys(re.findall(r'"id":"((?:event|verification)-\d+)"', str(messages))))[-8:]


def _run_readonly_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, arm_main_budget=None):
    (tmp_path / "README.md").write_text("# demo project\n本地 coding agent。\n", encoding="utf-8")

    route = {"main_instance": None}

    class FakeProvider:
        def __init__(self, **_kwargs) -> None:
            self.instance = id(self)

        async def chat(self, messages, tools, on_delta=None):
            rendered = json.dumps(messages, ensure_ascii=False)
            if "受约束任务规划器" in rendered:
                # 规划器故障 -> 服务端回退到固定模板，不产生 DAG 噪音。
                raise RuntimeError("planner disabled by the door")
            if tools is None:
                return LLMResponse(
                    content=json.dumps({
                        "status": "complete",
                        "confidence": 0.9,
                        "rationale": "只读调研完成。",
                        "missing": [],
                        "next_action": "",
                        "evidence": _completion_evidence_ids(messages) or ["event-1"],
                    }, ensure_ascii=False),
                    usage={"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
                )
            if route["main_instance"] is None:
                # 第一个非评委调用是主循环的开局轮；它的 provider 实例即父。
                # 同一实例的后续调用是主循环第二段；另一实例是子代理。
                route["main_instance"] = self.instance
                return LLMResponse(
                    tool_calls=[{
                        "id": "call-task-1",
                        "type": "function",
                        "function": {
                            "name": "task",
                            "arguments": json.dumps({
                                "description": "调研项目结构",
                                "prompt": "请读取 README.md 并总结这个项目的用途与结论。",
                            }, ensure_ascii=False),
                        },
                    }],
                    usage={"prompt_tokens": 4, "completion_tokens": 6, "total_tokens": 10},
                )
            if self.instance == route["main_instance"]:
                return LLMResponse(content="已获得调研结论，任务完成。", usage={"prompt_tokens": 5, "completion_tokens": 6, "total_tokens": 11})
            return LLMResponse(content="子代理结论：README 描述了一个本地 coding agent。", usage=dict(SUB_USAGE))

        async def close(self) -> None:
            return None

    monkeypatch.setattr("minicc.web.OpenAICompatibleProvider", FakeProvider)
    if arm_main_budget is not None:
        import minicc.web as web_module

        real_stage_route_budget = web_module._stage_route_budget

        def armed(route_obj, **kwargs):
            budget = real_stage_route_budget(route_obj, **kwargs)
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
                "message": "先调研项目结构，然后总结。",
                "session_id": "subagent-fold-door",
                "allow_changes": False,
                "workspace_path": str(tmp_path),
            },
            workspace=tmp_path,
        )
    finally:
        service.shutdown()
    return result


def test_subagent_spend_lands_in_the_run_budget_and_totals(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _run_readonly_session(tmp_path, monkeypatch)
    expected = 10 + 11 + 7 + SUB_TOKENS
    sub_finished = [
        event for event in result["events"] if event.get("code") == "subagent_finished"
    ]
    assert sub_finished and sub_finished[0]["detail"]["tokens_used"] == SUB_TOKENS, (
        f"子代理真花掉 {SUB_TOKENS}（这条不成立则用例前提失效）: "
        + json.dumps([e.get("detail", {}) for e in sub_finished], ensure_ascii=False)[:200]
    )
    budget = result["metrics"]["budget"]
    assert budget["tokens"] == expected, (
        "运行预算必须记入子代理花费："
        f"预算里 tokens={budget['tokens']}，应为 主21+评委7+子代理{SUB_TOKENS}；"
        "（修复前实测：子代理花得再多，运行预算也只有主循环+评委那些）"
    )
    assert result["tokens_used"]["total_tokens"] == expected, (
        "同一份载荷里的两个 token 数字必须来自同一次记账："
        f"metrics.budget.tokens={budget['tokens']} vs "
        f"tokens_used.total_tokens={result['tokens_used']['total_tokens']}"
    )
    assert budget["tokens"] >= budget["soft_max_tokens"], (
        "子代理花费已越软上限，运行预算必须知道（软上限驱动收尾提示）："
        f"tokens={budget['tokens']} vs soft_max_tokens={budget['soft_max_tokens']}"
    )
    rows = [row for row in result["usage_by_turn"] if row.get("stage") == "subagent"]
    assert len(rows) == 1 and rows[0].get("total_tokens") == SUB_TOKENS, (
        f"usage_by_turn 必须有一行 stage=subagent 的花费账（与 planner 同款）：{rows}"
    )
    trips = [
        event for event in result["events"]
        if event.get("code") == "budget_exceeded" and event.get("name") == "subagent"
    ]
    assert not trips, (
        "未越硬界的一次折叠不得伪造预算超限事件："
        + "; ".join(str(event.get("summary")) for event in trips[:3])
    )


def test_subagent_fold_trip_emits_named_budget_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """折叠越限必须发具名 subagent budget_exceeded trace，而不是静默。"""
    result = _run_readonly_session(
        tmp_path,
        monkeypatch,
        arm_main_budget=lambda budget: setattr(budget, "max_tokens", 1000),
    )
    trips = [
        event for event in result["events"]
        if event.get("code") == "budget_exceeded" and event.get("name") == "subagent"
    ]
    assert len(trips) == 1, (
        "折叠越限必须恰好发一条具名 subagent budget_exceeded 事件；本次事件里的 "
        "(code,name) 集合："
        + "; ".join(sorted({(str(e.get("code")), str(e.get("name"))) for e in result["events"]}))
    )
    detail = trips[0].get("detail", {})
    assert detail.get("stage") == "subagent" and detail.get("tokens_used", {}).get("total_tokens") == SUB_TOKENS, (
        f"事件 detail 必须点名阶段与本次折叠的载荷：{detail!r}"
    )


# -- 核心语义：恰一次、含细分、被中止也要落账 --------------------------------


class _ScriptedProvider:
    def __init__(self, script: list) -> None:
        self.script = list(script)
        self.chats = 0

    async def chat(self, messages, tools, on_delta=None):
        response = self.script[min(self.chats, len(self.script) - 1)]
        self.chats += 1
        return response

    async def close(self) -> None:
        return None


def _read_file_call(call_id: str = "call-r1") -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": "read_file", "arguments": '{"path": "README.md"}'},
    }


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "README.md").write_text("# demo project\n", encoding="utf-8")
    return tmp_path


def _build(workspace: Path, providers: list, **overrides):
    queue = list(providers)

    registry = build_registry(Editor(workspace))
    return build_task_tool_spec(
        provider_factory=lambda: queue.pop(0),
        workspace=workspace,
        system_prompt="你是 minicc 测试系统提示。",
        base_registry=registry,
        **overrides,
    )


def test_child_usage_reported_exactly_once_with_breakdown(workspace: Path) -> None:
    usage_a = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}
    usage_b = {"prompt_tokens": 50, "completion_tokens": 30, "total_tokens": 80}
    child = _ScriptedProvider([
        LLMResponse(tool_calls=[_read_file_call()], usage=dict(usage_a)),
        LLMResponse(content="子代理完成。", usage=dict(usage_b)),
    ])
    seen: list[dict] = []
    spec = _build(workspace, [child], on_child_usage=seen.append)
    result = spec.handler({"description": "读取 README 并总结", "prompt": "请读取 README.md 并给出结论。"})
    assert result.status == "ok", result.summary
    assert len(seen) == 1, f"每次子代理运行必须恰好上报一次花费：{seen}"
    payload = seen[0]
    assert payload.get("total_tokens") == 200, f"上报的应是子循环自己记账的合计：{payload}"
    assert payload.get("prompt_tokens") == 150 and payload.get("completion_tokens") == 50, (
        f"细分必须原样带到父侧（成本计价需要它）：{payload}"
    )
    assert result.data["tokens_used"]["total_tokens"] == 200, (
        "工具结果里的花费与上报的花费必须是同一笔账："
        f"{result.data['tokens_used']} vs {payload}"
    )


def test_aborted_child_still_reports_recorded_tokens(workspace: Path) -> None:
    """子代理撞上自己的成本天花板而失败：token 账仍要回传（含细分）。"""

    class _UsageLoopProvider:
        def __init__(self) -> None:
            self.rounds = 0

        async def chat(self, messages, tools, on_delta=None):
            self.rounds += 1
            return LLMResponse(
                tool_calls=[_read_file_call(f"call-{self.rounds}")],
                usage={"prompt_tokens": 1_000_000, "completion_tokens": 0, "total_tokens": 1_000_000},
            )

        async def close(self) -> None:
            return None

    provider = _UsageLoopProvider()
    seen: list[dict] = []
    spec = _build(
        workspace, [provider],
        max_turns=12, max_cost_usd=0.001, cost_estimator=lambda usage: 1.0,
        on_child_usage=seen.append,
    )
    result = spec.handler({"description": "超预算的调研", "prompt": "反复读取 README.md 直到预算耗尽。"})
    assert result.status == "error" and "阶段成本上限" in result.summary, result.summary
    assert len(seen) == 1, f"被自己的天花板中止也要落账，且恰一次：{seen}"
    assert seen[0].get("total_tokens") == 1_000_000, f"落账的应是子预算实际记到的数：{seen[0]}"
    assert seen[0].get("prompt_tokens") == 1_000_000, (
        f"正常返回路径带得回细分（走不到预算计数兜底）：{seen[0]}"
    )


def test_interrupted_child_folds_what_its_budget_recorded(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """子循环抛出 BudgetExceeded 逃出 run_agent：没有 result，用子预算计数兜底。"""
    import minicc.agent.subagent as sa

    async def _spend_then_raise(*args, budget=None, **kwargs):
        budget.record_usage({"total_tokens": 400})
        raise BudgetExceeded("模拟中断：模型请求被打断")

    monkeypatch.setattr(sa, "run_agent", _spend_then_raise)
    seen: list[dict] = []
    spec = _build(workspace, [object()], on_child_usage=seen.append)
    result = spec.handler({"description": "被打断的调研", "prompt": "读取 README.md 然后被打断。"})
    assert result.status == "error" and result.data.get("budget_exceeded") is True, result.summary
    assert seen == [{"total_tokens": 400}], (
        f"异常路径没有任何 result 可读，只能拿子预算记到的 token 兜底：{seen}"
    )


def test_crashed_child_folds_the_recorded_partial_tokens(workspace: Path) -> None:
    """子 provider 中途崩溃（黑盒）：落账不能因此消失。"""

    class _CrashingProvider:
        def __init__(self) -> None:
            self.chats = 0

        async def chat(self, messages, tools, on_delta=None):
            self.chats += 1
            if self.chats == 1:
                return LLMResponse(
                    tool_calls=[_read_file_call()],
                    usage={"prompt_tokens": 400, "completion_tokens": 0, "total_tokens": 400},
                )
            raise RuntimeError("provider crashed mid-run")

        async def close(self) -> None:
            return None

    provider = _CrashingProvider()
    seen: list[dict] = []
    spec = _build(workspace, [provider], on_child_usage=seen.append)
    try:
        result = spec.handler({"description": "中途崩溃的调研", "prompt": "读取 README.md 后让 provider 崩溃。"})
    except RuntimeError:
        result = None
    assert len(seen) == 1, f"崩溃路径同样恰一次落账：{seen}"
    assert seen[0].get("total_tokens") == 400, (
        f"崩溃路径只能拿子预算记到的 token 数兜底（无论异常是外抛还是收敛为结果）：{seen[0]}"
    )
    if result is not None:
        assert result.status == "error", result.summary


def test_a_reused_spec_never_reports_the_previous_runs_usage(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """同一 spec 连跑两次：第二次没有 result 时不许把第一次的账再报一遍。"""
    import minicc.agent.subagent as sa

    first_usage = {"prompt_tokens": 150, "completion_tokens": 50, "total_tokens": 200}
    child = _ScriptedProvider([LLMResponse(content="第一次完成。", usage=dict(first_usage))])
    seen: list[dict] = []
    spec = _build(workspace, [child, object()], on_child_usage=seen.append)

    result = spec.handler({"description": "第一次调研", "prompt": "请读取 README.md 并给出结论。"})
    assert result.status == "ok", result.summary
    assert seen == [dict(first_usage)], f"第一次必须报它自己的账：{seen}"

    async def _spend_then_raise(*args, budget=None, **kwargs):
        budget.record_usage({"total_tokens": 400})
        raise BudgetExceeded("模拟第二次运行被打断")

    monkeypatch.setattr(sa, "run_agent", _spend_then_raise)
    result2 = spec.handler({"description": "第二次调研", "prompt": "请读取 README.md 后被打断。"})
    assert result2.status == "error", result2.summary
    assert seen[1] == {"total_tokens": 400}, (
        f"第二次没有 result 时必须用第二次自己的预算计数兜底，绝不能复用第一次的载荷：{seen}"
    )


def test_grandchild_spend_propagates_through_the_nested_face(workspace: Path) -> None:
    grand_usage = {"prompt_tokens": 300_000, "completion_tokens": 200_000, "total_tokens": 500_000}
    child_turn1 = {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}
    child_final = {"prompt_tokens": 60, "completion_tokens": 40, "total_tokens": 100}
    grand = _ScriptedProvider([LLMResponse(content="孙代理结论。", usage=dict(grand_usage))])
    child = _ScriptedProvider([
        LLMResponse(
            tool_calls=[{
                "id": "call-nested-1",
                "type": "function",
                "function": {
                    "name": "task",
                    "arguments": json.dumps({
                        "description": "孙代理由此派生",
                        "prompt": "请读取 README.md 并给出孙代理结论。",
                    }, ensure_ascii=False),
                },
            }],
            usage=dict(child_turn1),
        ),
        LLMResponse(content="子代理结论。", usage=dict(child_final)),
    ])
    seen: list[dict] = []
    spec = _build(
        workspace, [child, grand],
        writable=True, permission_mode="acceptEdits", max_depth=2,
        on_child_usage=seen.append,
    )
    result = spec.handler({"description": "派生可写子代理", "prompt": "请派生一个子代理完成阅读并总结。"})
    assert result.status == "ok", result.summary
    totals = [entry.get("total_tokens") for entry in seen]
    assert totals == [500_000, 130], (
        "孙代理与子代理各上报一次、互不合并、也不重复（孙花费每次只进父账一次）："
        f"{seen}"
    )
    assert result.data["tokens_used"]["total_tokens"] == 130, (
        f"顶层工具结果只报子代理自己的 130：{result.data['tokens_used']}"
    )
