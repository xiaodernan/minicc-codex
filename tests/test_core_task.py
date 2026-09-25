"""任务层核心测试：TaskManager/TaskRecord/TaskStore、事件回放、快照恢复、审计导出。

M8-T6 拆分说明：测试本体逐字搬迁，未改断言。"""

from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from types import SimpleNamespace
import pytest
from minicc.agent.protocol import CancellationToken, EventLog, InvalidStatusTransition
from minicc.agent.state import Budget, BudgetExceeded
from minicc.llm.base import LLMResponse
from minicc.llm.openai_provider import OpenAICompatibleProvider
from minicc.tools.editor import Editor
from minicc.task_store import TaskStore
from minicc.web import AgentService, TaskManager, TaskRecord
from minicc.agent.loop import TurnResult


def _completion_evidence_ids(messages) -> list[str]:
    """Fake reviewers must cite actual IDs from the review evidence packet."""
    return list(dict.fromkeys(re.findall(r'"id":"((?:event|verification)-\d+)"', str(messages))))[-8:]


def test_budget_tracks_usage_and_stops_at_limits() -> None:
    budget = Budget(max_turns=1, max_tokens=3, max_tool_calls=1)
    budget.record_turn()
    budget.record_usage({"total_tokens": 3})
    budget.record_tool_call()
    with pytest.raises(BudgetExceeded):
        budget.record_turn()


def test_runtime_protocol_replays_events_detects_gaps_and_closes_cleanly() -> None:
    log = EventLog(task_id="protocol-test", limit=32)
    first = log.append("state", {"phase": "planning"})
    assert first is not None
    for index in range(40):
        log.append("trace", {"index": index})

    events, gap = log.read(after=0, timeout=0)
    assert gap is True
    assert events[-1].sequence == log.cursor
    log.close()
    assert log.closed is True
    assert log.append("late", {}) is None
    assert log.read(after=log.cursor, timeout=0) == ([], False)


def test_task_runtime_history_indexes_and_counters_stay_bounded() -> None:
    task = TaskRecord(
        task_id="bounded-task",
        session_id="bounded",
        message="inspect",
        allow_changes=False,
        event_limit=32,
        usage_limit=8,
        compaction_limit=8,
    )
    task.transition_status("running")
    first_event = None
    for index in range(80):
        event = task.add_event({
            "kind": "trace",
            "name": "agent",
            "status": "ok",
            "phase": "planning",
            "code": f"step_{index}",
            "summary": f"step {index}",
            "detail": {"turn": index + 1},
        })
        if index == 0:
            first_event = event
    for index in range(20):
        task.update_usage({"total_tokens": index + 1})
        task.add_compaction({"turn": index + 1})

    assert len(task.events) == 32
    assert len(task._event_ids) == 32
    assert len(task._event_keys) == 32
    assert len(task.usage_by_turn) == 8
    assert len(task.compaction_events) == 8
    assert task.snapshot()["events_truncated"] >= 48
    assert task.event_log.read(after=0, timeout=0)[1] is True
    assert first_event is not None


def test_restored_task_reports_replay_gap_when_live_events_are_unavailable() -> None:
    restored = TaskRecord.from_snapshot({
        "task_id": "restored-gap",
        "session_id": "restored",
        "prompt": "inspect",
        "status": "completed",
        "event_cursor": 12,
        "events": [],
    })
    events, gap = restored.wait_events(after=0, timeout=0)
    assert events == []
    assert gap is True


def test_cancellation_token_propagates_to_children_and_status_transitions_are_terminal() -> None:
    parent = CancellationToken()
    child = parent.child()
    parent.cancel("service_shutdown")
    assert child.is_set() is True
    assert child.reason == "service_shutdown"

    task = TaskRecord(task_id="protocol-task", session_id="protocol", message="x", allow_changes=False)
    task.transition_status("running")
    task.request_cancel("user")
    with pytest.raises(InvalidStatusTransition):
        task.transition_status("completed")
    assert task.apply_result({"answer": "late provider result", "cancelled": False}) is False
    snapshot = task.snapshot()
    assert snapshot["status"] == "cancelled"
    assert snapshot["answer"] == "任务已取消"
    assert "late provider result" not in snapshot.get("answer", "")


def test_a_result_payload_without_usage_never_erases_the_usage_already_reported() -> None:
    """An empty ``tokens_used`` means "no information", not "cost nothing".

    ``TaskResult.to_payload()`` emits the key even when the producer never
    filled it in, so treating it as authoritative resets a run that already
    reported every turn's usage to zero — and ``/api/metrics``, which bills the
    root row, then reports a free task that really cost money.
    """
    task = TaskRecord(task_id="usage-task", session_id="usage", message="x", allow_changes=False)
    task.transition_status("running")
    task.update_usage({"prompt_tokens": 400, "completion_tokens": 100, "total_tokens": 500})

    assert task.apply_result({"answer": "provider forgot the usage", "tokens_used": {}}) is True
    assert dict(task.tokens_used) == {"prompt_tokens": 400, "completion_tokens": 100, "total_tokens": 500}
    assert task.snapshot()["tokens_used"]["total_tokens"] == 500

    # A real cumulative figure still wins.
    assert task.apply_result({"answer": "final", "tokens_used": {"total_tokens": 700}}) is True
    assert task.tokens_used["total_tokens"] == 700

    # ...and an all-zero payload stays "no information": a run that reported
    # 700 tokens turn by turn is not retroactively free.
    assert task.apply_result({"answer": "final", "tokens_used": {"total_tokens": 0}}) is True
    assert task.tokens_used["total_tokens"] == 700

    fresh = TaskRecord(task_id="usage-task-2", session_id="usage", message="x", allow_changes=False)
    fresh.transition_status("running")
    assert fresh.apply_result({"answer": "final", "tokens_used": {"total_tokens": 0}}) is True
    assert fresh.tokens_used.get("total_tokens", 0) == 0


def test_task_snapshot_corrupt_numeric_fields_are_recovered_as_interrupted() -> None:
    restored = TaskRecord.from_snapshot(
        {
            "task_id": "corrupt-snapshot",
            "prompt": "inspect workspace",
            "status": "running",
            "created_at_epoch": "not-a-number",
            "event_limit": "broken",
            "stream_limit": "broken",
            "event_cursor": "broken",
            "state_version": "broken",
            "events_truncated": "broken",
        }
    )
    assert restored.status == "interrupted"
    assert restored.event_limit >= 32
    assert restored.stream_limit >= 512
    assert restored.snapshot()["event_cursor"] == 0


def test_agent_service_preflights_complex_tasks_with_a_safe_model_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"planner": 0, "agent": 0, "judge": 0}
    (tmp_path / "notes.md").write_text("# 现状\n前后端分离。\n", encoding="utf-8")

    class FakeProvider:
        def __init__(self, **_kwargs) -> None:
            pass

        async def chat(self, messages, tools, on_delta=None):
            rendered = json.dumps(messages, ensure_ascii=False)
            if "受约束任务规划器" in rendered:
                calls["planner"] += 1
                return LLMResponse(
                    content=json.dumps({
                        "name": "readonly-review",
                        "tasks": [
                            {"id": "inspect", "kind": "readonly", "allowed_tools": ["read_file", "grep"]},
                            {"id": "review", "kind": "review", "depends_on": ["inspect"], "allowed_tools": ["git_diff"]},
                        ],
                    }, ensure_ascii=False),
                    usage={"prompt_tokens": 10, "completion_tokens": 8, "total_tokens": 18},
                )
            if tools is None:
                calls["judge"] += 1
                return LLMResponse(content=json.dumps({
                    "status": "complete",
                    "confidence": 0.96,
                    "rationale": "只读检查已完成，证据足够交付。",
                    "missing": [],
                    "next_action": "",
                    "evidence": _completion_evidence_ids(messages),
                }, ensure_ascii=False))
            calls["agent"] += 1
            # M4-T1: a read-only completion must cite real tool evidence, not
            # narration traces. The old fake agent never called a tool, so the
            # task was judged complete only because trace ids were wrongly
            # accepted as evidence. Emit one read_file observation per node so
            # the judge has a citable id.
            if "read-1" not in rendered:
                return LLMResponse(
                    tool_calls=[
                        {
                            "id": "read-1",
                            "type": "function",
                            "function": {
                                "name": "read_file",
                                "arguments": json.dumps({"path": "notes.md"}),
                            },
                        }
                    ]
                )
            return LLMResponse(content="已完成复杂只读检查并整理风险。")

        async def close(self) -> None:
            return None

    monkeypatch.setattr("minicc.web.OpenAICompatibleProvider", FakeProvider)
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
    )
    service = AgentService(tmp_path, config)
    try:
        result = service._chat_locked(
            {
                "message": (
                    "分析 src/app.py、web/app.js 和 tests/test_core.py 的前后端现状，"
                    "同时检查界面和测试，运行验证并总结风险。"
                ),
                "session_id": "planner-preflight",
                "allow_changes": False,
                "workspace_path": str(tmp_path),
            },
            workspace=tmp_path,
        )
    finally:
        service.shutdown()
    assert result["error"] is None
    # agent: each read-only DAG node now spends one turn on a real read_file
    # observation and one on its summary (M4-T1), so the count rises over the
    # old tool-less fake. planner/judge stay at exactly one call each.
    assert calls["planner"] == 1
    assert calls["judge"] == 1
    assert calls["agent"] >= 3
    assert result["context"]["planner"]["source"] == "dynamic_model"
    assert result["metrics"]["planner"]["plan"]["name"] == "readonly-review"
    assert result["metrics"]["planner"]["execution"]["status"] == "completed"
    assert result["metrics"]["planner"]["execution"]["completed"] == ["inspect", "review"]
    assert any(event.get("code") == "planner_started" for event in result["events"])
    assert any(event.get("code") == "planner_dynamic_ready" for event in result["events"])
    assert any(event.get("code") == "planner_execution_finished" for event in result["events"])


def test_planner_dag_nodes_run_with_a_bounded_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P2-8 漏网复核（2026-09-25 全量评测批次登记）：DAG 节点不得拿到全 None 预算。

    捕获每一次 run_agent 调用的 budget/max_turns 后直接返回合成结果——这样在
    未修复代码上也不会挂死，红法是断言「没有任何一次调用带着 12 轮的界」。
    """
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
                    usage={"prompt_tokens": 10, "completion_tokens": 8, "total_tokens": 18},
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
            return LLMResponse(content="节点执行已由捕获桩接管。")

        async def close(self) -> None:
            return None

    async def capturing_run_agent(provider, registry, messages, *, budget=None, max_turns=None, **kwargs):
        captured.append({"max_turns": max_turns, "budget": budget})
        return TurnResult(answer="节点完成")

    monkeypatch.setattr("minicc.web.OpenAICompatibleProvider", FakeProvider)
    monkeypatch.setattr("minicc.web.run_agent", capturing_run_agent)
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
                "message": (
                    "分析 src/app.py 和 web/app.js 的现状，运行验证并总结风险。"
                ),
                "session_id": "node-budget-capture",
                "allow_changes": False,
                "workspace_path": str(tmp_path),
            },
            workspace=tmp_path,
        )
    finally:
        service.shutdown()

    assert captured, "DAG 执行应当发起至少一次 run_agent"
    node_budgets = [
        entry for entry in captured
        if isinstance(entry["budget"], Budget)
        and getattr(entry["budget"], "max_turns", None) == 12
        and getattr(entry["budget"], "max_duration_seconds", None) == 300.0
    ]
    # 未修复代码上这里红：所有调用要么 max_turns=None，要么没有 300s 的墙钟界。
    assert node_budgets, (
        "DAG 节点必须带 12 轮 / 300s 的界运行；当前捕获到 "
        + "; ".join(
            f"max_turns={entry['max_turns']!r}, budget={entry['budget']!r}" for entry in captured[:6]
        )
    )
    node_budget = node_budgets[0]["budget"]
    assert node_budget.max_retries is None, "重试策略不是节点预算，与 chat 路径同一立场"
    assert node_budget.soft_max_tokens == 5000
    assert node_budget.soft_max_duration_seconds == 120.0
    assert any(entry["max_turns"] == 12 for entry in captured), (
        "run_agent 的 max_turns 兼容参数也要设界：while 循环读的是它，不是 Budget"
    )
    assert result is not None


def test_agent_service_marks_text_only_change_request_as_incomplete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeProvider:
        def __init__(self, **_kwargs) -> None:
            pass

        async def chat(self, messages, tools, on_delta=None):
            return LLMResponse(content="我已经确认问题，稍后再处理。")

        async def close(self) -> None:
            return None

    monkeypatch.setattr("minicc.web.OpenAICompatibleProvider", FakeProvider)
    config = SimpleNamespace(
        yolo=False,
        max_concurrent_tasks=1,
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
    )
    service = AgentService(tmp_path, config)
    try:
        result = service._chat_locked(
            {
                "message": "修复这个问题并继续做完",
                "session_id": "completion-guard",
                "allow_changes": True,
                "workspace_path": str(tmp_path),
            },
            workspace=tmp_path,
        )
    finally:
        service.shutdown()
    assert result["completion_guard"]
    assert result["error"] == "模型在没有完成任何工作区修改前结束了任务"
    assert result["cancelled"] is False


def test_agent_service_runs_verifier_after_successful_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, suite_python_bin: str) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_smoke.py").write_text("def test_smoke():\n    assert True\n", encoding="utf-8")
    (tmp_path / ".minicc").mkdir()
    (tmp_path / ".minicc" / "verification.json").write_text(json.dumps({"rules": [{"paths": ["result.txt"], "commands": [f"{suite_python_bin} -m pytest -q tests/test_smoke.py"]}]}), encoding="utf-8")

    class FakeProvider:
        def __init__(self, **_kwargs) -> None:
            self.calls = 0

        async def chat(self, messages, tools, on_delta=None):
            self.calls += 1
            if tools is None:
                return LLMResponse(
                    content=json.dumps({
                        "status": "complete",
                        "confidence": 0.98,
                        "rationale": "修改已写入，工具验证和自动验证均通过。",
                        "missing": [],
                        "next_action": "",
                        "evidence": _completion_evidence_ids(messages),
                    }, ensure_ascii=False)
                )
            if self.calls == 1:
                return LLMResponse(
                    tool_calls=[
                        {
                            "id": "write-1",
                            "type": "function",
                            "function": {
                                "name": "write_file",
                                "arguments": json.dumps({"path": "result.txt", "content": "verified\n"}),
                            },
                        }
                    ]
                )
            if self.calls == 2:
                return LLMResponse(
                    tool_calls=[
                        {
                            "id": "pytest-1",
                            "type": "function",
                            "function": {
                                "name": "bash",
                                "arguments": json.dumps({"command": f"{suite_python_bin} -m pytest -q"}),
                            },
                        }
                    ]
                )
            return LLMResponse(content="修改和验证都已完成。")

        async def close(self) -> None:
            return None

    monkeypatch.setattr("minicc.web.OpenAICompatibleProvider", FakeProvider)
    config = SimpleNamespace(
        yolo=True,
        max_concurrent_tasks=1,
        max_repair_attempts=2,
        sandbox_mode="host",
        sandbox_image="python:3.11-slim",
        base_url="https://example.test/v1",
        api_key="test-key",
        model="test-model",
        timeout=10,
        tool_mode="auto",
        reasoning_effort="high",
        max_turns=8,
        compact_threshold=300_000,
        context_window_tokens=300_000,
    )
    service = AgentService(tmp_path, config)
    try:
        result = service._chat_locked(
            {
                "message": "修改 result.txt 并验证",
                "session_id": "verifier-loop",
                "allow_changes": True,
                "workspace_path": str(tmp_path),
            },
            workspace=tmp_path,
        )
    finally:
        service.shutdown()
    assert result["error"] is None
    assert (tmp_path / "result.txt").read_text(encoding="utf-8") == "verified\n"
    assert result["metrics"]["verification_runs"] == 1
    assert any(event.get("code") == "verification_passed" for event in result["events"])


def test_terminal_snapshot_prefers_status_over_stale_phase(tmp_path: Path) -> None:
    task = TaskRecord(
        task_id="task-terminal",
        session_id="terminal",
        message="done",
        allow_changes=False,
        status="completed",
        phase="answering",
    )
    assert task.snapshot()["phase"] == "completed"


def test_task_manager_runs_batch_in_parallel() -> None:
    class FakeService:
        config = SimpleNamespace(yolo=False, model="test-model")

        @staticmethod
        def _run_chat(payload, *, on_event=None, on_stream=None, cancel_event=None):
            if on_event is not None:
                on_event({"name": "fake", "status": "ok", "summary": payload["message"]})
            return {"answer": payload["message"], "cancelled": False, "events": []}

    manager = TaskManager(FakeService(), max_workers=2)
    try:
        batch = manager.submit_batch({"messages": ["one", "two"], "session_id": "batch-test"})
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            states = [manager.get(task_id)["status"] for task_id in batch["task_ids"]]
            if all(state == "completed" for state in states):
                break
            time.sleep(0.01)
        assert [manager.get(task_id)["status"] for task_id in batch["task_ids"]] == ["completed", "completed"]
        assert all(manager.get(task_id)["answer"].startswith("[Parallel subagent") for task_id in batch["task_ids"])
        assert all(manager.get(task_id)["parent_id"] == batch["parent_task_id"] for task_id in batch["task_ids"])
        child_sessions = [manager.get(task_id)["session_id"] for task_id in batch["task_ids"]]
        assert len(set(child_sessions)) == len(child_sessions)
        assert all("-subagent-" in session for session in child_sessions)
        assert any(event.get("code") == "batch_started" for event in manager.get(batch["parent_task_id"])["events"])
    finally:
        manager.shutdown()


def test_task_manager_auto_orchestrates_complex_task_then_resumes_parent(tmp_path: Path) -> None:
    calls: list[tuple[str, bool]] = []

    class FakeService:
        config = SimpleNamespace(yolo=False, max_concurrent_tasks=4, model="test-model")
        workspace = tmp_path

        @staticmethod
        def _run_chat(payload, *, on_event=None, on_stream=None, cancel_event=None):
            message = str(payload["message"])
            calls.append((message, bool(payload.get("allow_changes"))))
            if "自动子任务" in message:
                if on_event is not None:
                    on_event({"kind": "trace", "phase": "planning", "status": "ok", "summary": "只读侦察完成"})
                return {"answer": "已检查 src/app.py；建议先修复状态同步，再运行测试。", "cancelled": False, "events": []}
            assert "自动编排证据" in message
            if on_event is not None:
                on_event({"kind": "trace", "phase": "implementing", "status": "ok", "summary": "主 Agent 已接管"})
            return {"answer": "主任务已基于侦察证据完成。", "cancelled": False, "events": []}

    manager = TaskManager(FakeService(), max_workers=4)
    try:
        created = manager.submit(
            {
                "message": "请分析前后端现状，修复登录和任务流式输出，同时优化界面，并补充测试，联网调研最新文档后运行验证。",
                "session_id": "auto-test",
                "allow_changes": True,
                "workspace_path": str(tmp_path),
            }
        )
        assert created["task_kind"] == "batch"
        assert created["orchestration_mode"] == "auto"
        assert len(created["child_task_ids"]) >= 2

        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and manager.get(created["task_id"])["status"] not in {"completed", "failed"}:
            time.sleep(0.01)
        parent = manager.get(created["task_id"])
        assert parent["status"] == "completed"
        assert "主任务已基于侦察证据完成" in parent["answer"]
        assert all(manager.get(child_id)["allow_changes"] is False for child_id in created["child_task_ids"])
        assert any(message.startswith("[自动子任务") for message, _allow_changes in calls)
        assert any("自动编排证据" in message and allow_changes for message, allow_changes in calls)
        codes = {event.get("code") for event in parent["events"]}
        assert {"auto_orchestration_triggered", "orchestration_parent_resumed"} <= codes
    finally:
        manager.shutdown()


def test_batch_watcher_marks_missing_child_interrupted_and_finishes_parent(tmp_path: Path) -> None:
    class FakeService:
        config = SimpleNamespace(yolo=False, max_concurrent_tasks=1, model="test-model")
        workspace = tmp_path

    manager = TaskManager(FakeService(), max_workers=1)
    parent = TaskRecord(
        task_id="batch-missing-child",
        session_id="batch-missing",
        message="批任务",
        allow_changes=False,
        workspace_path=str(tmp_path),
        status="running",
        phase="planning",
    )
    try:
        with manager.lock:
            manager.tasks[parent.task_id] = parent
        manager._watch_batch(parent, ["missing-child"])
        snapshot = manager.get(parent.task_id)
        assert snapshot["status"] == "failed"
        assert "子任务" in snapshot["error"]
        assert any(event.get("code") == "batch_finished" for event in snapshot["events"])
    finally:
        manager.shutdown()


def test_batch_merge_passes_reasoning_effort_to_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}

    class FakeProvider:
        def __init__(self, **kwargs):
            seen.update(kwargs)

        async def chat(self, **kwargs):
            return LLMResponse(content="merged", usage={"total_tokens": 3})

        async def close(self) -> None:
            return None

    monkeypatch.delenv("MINICC_FAKE_PROVIDER", raising=False)
    monkeypatch.setattr("minicc.web.OpenAICompatibleProvider", FakeProvider)
    # A ``SimpleNamespace`` receiver let the real call site drift until it
    # crashed: merge_batch now builds its provider through the service, so this
    # exercises the same bound method the batch watcher calls.
    service = AgentService(
        tmp_path,
        SimpleNamespace(
            base_url="https://example.test/v1",
            api_key="test-key",
            model="test-model",
            timeout=30,
            tool_mode="auto",
            reasoning_effort="high",
            yolo=False,
            sandbox_mode="host",
            sandbox_image="python:3.11-slim",
        ),
    )

    result = service.merge_batch(
        [{"status": "completed", "answer": "child result"}],
        reasoning_effort="max",
    )

    assert result["answer"] == "merged"
    assert seen["reasoning_effort"] == "max"


def test_task_store_round_trips_redacted_history_and_marks_running_as_interrupted(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "tasks.sqlite3")
    store.upsert(
        {
            "task_id": "task-persisted",
            "created_at_epoch": 1,
            "workspace_path": str(tmp_path),
            "prompt": "inspect sk-secret-value",
            "answer": "sk-secret-value",
            "status": "running",
        }
    )
    with store._connect() as connection:
        connection.execute(
            "INSERT INTO tasks(task_id, created_at, workspace_path, payload) VALUES (?, ?, ?, ?)",
            (
                "task-legacy",
                2,
                str(tmp_path),
                json.dumps({"task_id": "ta[REDACTED:llm_api_key]", "status": "completed"}),
            ),
        )

    loaded = store.load()
    by_id = {item["task_id"]: item for item in loaded}
    assert by_id["task-persisted"]["prompt"] != "inspect sk-secret-value"
    assert by_id["task-legacy"]["task_id"] == "task-legacy"
    assert "sk-secret-value" not in json.dumps(loaded)

    restored = TaskRecord.from_snapshot(by_id["task-persisted"])
    assert restored.status == "interrupted"
    assert restored.phase == "interrupted"
    assert restored.error


def test_task_store_prunes_old_terminal_history_but_keeps_active_and_batch_children(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "tasks.sqlite3")
    base_time = time.time()
    for index in range(5):
        store.upsert(
            {
                "task_id": f"task-{index}",
                "created_at_epoch": base_time + index,
                "workspace_path": str(tmp_path),
                "prompt": f"task {index}",
                "status": "completed",
                "child_task_ids": ["task-child"] if index == 4 else [],
                "events": [{"name": "tool", "output": "large history"}],
            }
        )
    store.upsert(
        {
            "task_id": "task-child",
            "created_at_epoch": base_time - 100,
            "workspace_path": str(tmp_path),
            "prompt": "child",
            "status": "completed",
        }
    )
    store.upsert(
        {
            "task_id": "task-active",
            "created_at_epoch": 0,
            "workspace_path": str(tmp_path),
            "prompt": "active",
            "status": "running",
        }
    )

    deleted = store.prune(keep_terminal=1, max_age_days=3650)
    remaining = {item["task_id"] for item in store.load()}

    assert "task-4" not in deleted
    assert "task-4" in remaining
    assert "task-child" in remaining
    assert "task-active" in remaining
    assert "task-0" in deleted


def test_task_manager_list_returns_bounded_summaries(tmp_path: Path) -> None:
    class FakeService:
        config = SimpleNamespace(yolo=False, max_concurrent_tasks=1, model="test-model")
        workspace = tmp_path

    store = TaskStore(tmp_path / "tasks.sqlite3")
    store.upsert(
        {
            "task_id": "task-summary",
            "created_at_epoch": time.time(),
            "workspace_path": str(tmp_path),
            "prompt": "summary",
            "status": "completed",
            "events": [{"name": "tool", "output": "do not send this in the index"}],
            "stream_text": "large stream",
            "result": {"answer": "full answer"},
        }
    )
    manager = TaskManager(FakeService(), max_workers=1, store=store)
    try:
        item = manager.list(limit=1)[0]
        assert item["summary_only"] is True
        assert item["event_count"] == 1
        assert "events" not in item
        assert "result" not in item
        assert "stream_text" not in item
    finally:
        manager.shutdown()


def test_task_manager_resume_reuses_only_unchanged_readonly_checkpoint(tmp_path: Path) -> None:
    (tmp_path / "evidence.txt").write_text("stable\n", encoding="utf-8")
    observed_payloads: list[dict[str, object]] = []

    class FakeService:
        config = SimpleNamespace(yolo=False, max_concurrent_tasks=1, model="test-model")
        workspace = tmp_path

        @staticmethod
        def _run_chat(payload, *, on_event=None, on_stream=None, cancel_event=None):
            observed_payloads.append(payload)
            if on_event is not None:
                on_event({"name": "read_file", "path": "evidence.txt", "status": "ok", "write": False})
            return {"answer": "evidence checked", "cancelled": False, "events": []}

    store = TaskStore(tmp_path / "tasks.sqlite3")
    manager = TaskManager(FakeService(), max_workers=1, store=store)
    try:
        original = manager.submit({"message": "检查证据文件", "session_id": "checkpoint-test"})
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and manager.get(original["task_id"])["status"] != "completed":
            time.sleep(0.01)
        completed = manager.get(original["task_id"])
        assert completed["status"] == "completed"
        assert completed["allow_network"] is False
        assert completed["checkpoint"]["safe_readonly"] is True
        assert completed["checkpoint"]["paths"] == ["evidence.txt"]

        resumed = manager.resume(original["task_id"])
        assert resumed["context"]["recovery"]["mode"] == "safe_readonly_checkpoint"
        assert resumed["context"]["recovery"]["workspace_digest_matches"] is True
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and manager.get(resumed["task_id"])["status"] not in {"completed", "failed"}:
            time.sleep(0.01)

        (tmp_path / "evidence.txt").write_text("changed\n", encoding="utf-8")
        changed = manager.resume(original["task_id"])
        assert changed["context"]["recovery"]["mode"] == "reinspect_required"
        assert changed["context"]["recovery"]["workspace_digest_matches"] is False
        assert changed["events"][-1]["code"] == "reinspect_required"
    finally:
        manager.shutdown()


def test_audit_export_redacts_sensitive_detail(tmp_path: Path) -> None:
    audit_path = tmp_path / ".minicc" / "audit.jsonl"
    editor = Editor(tmp_path, audit_path=audit_path)
    editor._audit("write", "note.txt", "sk-secret-value")

    exported = AgentService.audit_export(SimpleNamespace(workspace=tmp_path), limit=10)
    rendered = json.dumps(exported, ensure_ascii=False)
    assert exported["count"] == 1
    assert "sk-secret-value" not in rendered
    assert "[REDACTED:llm_api_key]" in rendered


def test_task_snapshot_and_restore_preserve_network_authorization() -> None:
    task = TaskRecord(
        task_id="task-network-flag",
        session_id="network",
        message="查询资料",
        allow_changes=False,
        allow_network=True,
    )
    restored = TaskRecord.from_snapshot(task.snapshot())
    assert restored.allow_network is True
    assert restored.snapshot()["allow_network"] is True


def test_task_snapshot_without_status_is_not_treated_as_completed() -> None:
    restored = TaskRecord.from_snapshot({"task_id": "task-unknown", "prompt": "continue the work"})
    assert restored.status == "interrupted"
    assert restored.phase == "interrupted"
    assert restored.error


def test_task_snapshot_repairs_legacy_false_completion() -> None:
    restored = TaskRecord.from_snapshot(
        {
            "task_id": "task-false-complete",
            "prompt": "修复这个问题并继续做完",
            "status": "completed",
            "events": [{"name": "read_file", "status": "ok", "write": False}],
            "answer": "我已经检查过了，无需修改。",
            "result": {"answer": "我已经检查过了，无需修改。", "cancelled": False},
        }
    )
    assert restored.status == "failed"
    assert restored.phase == "failed"
    assert restored.error == "历史任务没有成功修改工作区，旧记录的完成状态已更正为失败。"
    assert restored.result["completion_guard"] == restored.error


def test_task_snapshot_keeps_evidence_backed_no_change_completion() -> None:
    restored = TaskRecord.from_snapshot(
        {
            "task_id": "task-judged-no-change",
            "prompt": "修复这个问题，如果现状已经正确则说明依据",
            "status": "completed",
            "events": [{"name": "read_file", "status": "ok", "write": False}],
            "answer": "现状已经满足需求。",
            "result": {
                "answer": "现状已经满足需求。",
                "cancelled": False,
                "completion": {
                    "status": "complete",
                    "confidence": 0.94,
                    "evidence": ["read_file"],
                },
            },
        }
    )
    assert restored.status == "completed"
    assert restored.error is None


def test_task_manager_exposes_live_stream_and_phase() -> None:
    entered = threading.Event()
    release = threading.Event()

    class FakeService:
        config = SimpleNamespace(yolo=False, model="test-model")

        @staticmethod
        def _run_chat(payload, *, on_event=None, on_stream=None, cancel_event=None):
            if on_stream is not None:
                on_stream("第一段")
                on_stream("第二段")
            entered.set()
            release.wait(2)
            return {"answer": "第一段第二段", "cancelled": False, "events": []}

    manager = TaskManager(FakeService(), max_workers=1)
    try:
        task_id = manager.submit({"message": "实时回答", "session_id": "stream-test"})["task_id"]
        assert entered.wait(2)
        live = manager.get(task_id)
        assert live["status"] == "running"
        assert live["phase"] == "answering"
        assert live["stream_text"] == "第一段第二段"
        release.set()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and manager.get(task_id)["status"] != "completed":
            time.sleep(0.01)
        final = manager.get(task_id)
        assert final["status"] == "completed"
        assert final["phase"] == "completed"
    finally:
        release.set()
        manager.shutdown()


def test_task_manager_drops_stream_deltas_after_cancel() -> None:
    entered = threading.Event()
    release = threading.Event()

    class FakeService:
        config = SimpleNamespace(yolo=False, model="test-model")

        @staticmethod
        def _run_chat(payload, *, on_event=None, on_stream=None, cancel_event=None):
            if on_stream is not None:
                on_stream("取消前")
            entered.set()
            release.wait(2)
            if on_stream is not None:
                on_stream("取消后")
            cancelled = cancel_event.is_set() if cancel_event is not None else False
            return {"answer": "任务已取消。", "cancelled": cancelled, "events": []}

    manager = TaskManager(FakeService(), max_workers=1)
    try:
        task_id = manager.submit({"message": "取消测试", "session_id": "cancel-test"})["task_id"]
        assert entered.wait(2)
        manager.cancel(task_id)
        assert manager.get(task_id)["status"] == "cancelled"
        assert manager.get(task_id)["stream_text"] == "取消前"
        release.set()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and manager.get(task_id)["status"] != "cancelled":
            time.sleep(0.01)
        final = manager.get(task_id)
        assert final["status"] == "cancelled"
        assert final["phase"] == "cancelled"
        assert final["stream_text"] == "取消前"
    finally:
        release.set()
        manager.shutdown()


def test_task_manager_marks_agent_errors_as_failed() -> None:
    class FakeService:
        config = SimpleNamespace(yolo=False, model="test-model")

        @staticmethod
        def _run_chat(payload, *, on_event=None, on_stream=None, cancel_event=None):
            return {"answer": "[错误] provider unavailable", "error": "provider unavailable", "cancelled": False, "events": []}

    manager = TaskManager(FakeService(), max_workers=1)
    try:
        task_id = manager.submit({"message": "error status", "session_id": "error-test"})["task_id"]
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if manager.get(task_id)["status"] == "failed":
                break
            time.sleep(0.01)
        task = manager.get(task_id)
        assert task["status"] == "failed"
        assert task["phase"] == "failed"
        assert task["error"] == "provider unavailable"
    finally:
        manager.shutdown()


def test_task_manager_binds_workspace_from_submission(tmp_path: Path) -> None:
    workspace = tmp_path / "submitted"
    workspace.mkdir()

    class FakeService:
        config = SimpleNamespace(yolo=False, max_concurrent_tasks=1, model="test-model")
        workspace = tmp_path / "current"

        @staticmethod
        def _run_chat(payload, *, on_event=None, on_stream=None, cancel_event=None):
            return {"answer": payload["workspace_path"], "cancelled": False, "events": []}

    FakeService.workspace.mkdir()
    manager = TaskManager(FakeService(), max_workers=1)
    try:
        task = manager.submit({"message": "bound", "session_id": "bound", "workspace_path": str(workspace)})
        assert Path(task["workspace_path"]).resolve() == workspace.resolve()
    finally:
        manager.shutdown()


def test_task_manager_preserves_trace_phase_while_running() -> None:
    entered = threading.Event()
    release = threading.Event()

    class FakeService:
        config = SimpleNamespace(yolo=False, max_concurrent_tasks=1, model="test-model")
        workspace = Path.cwd()

        @staticmethod
        def _run_chat(payload, *, on_event=None, on_stream=None, cancel_event=None):
            on_event({"kind": "trace", "phase": "planning", "status": "ok", "summary": "plan"})
            entered.set()
            release.wait(2)
            return {"answer": "done", "cancelled": False, "events": []}

    manager = TaskManager(FakeService(), max_workers=1)
    try:
        task_id = manager.submit({"message": "trace", "session_id": "trace"})["task_id"]
        assert entered.wait(1)
        assert manager.get(task_id)["phase"] == "planning"
        release.set()
    finally:
        release.set()
        manager.shutdown()


def test_task_recovers_after_transient_provider_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    instances: list[object] = []

    class FakeProvider:
        def __init__(self, **_kwargs) -> None:
            self.calls = 0
            self.failed_once = len(instances) == 0
            instances.append(self)

        async def chat(self, messages, tools, on_delta=None):
            self.calls += 1
            if self.failed_once and self.calls == 1:
                raise RuntimeError("stream disconnected before completion: Connection error.")
            if tools is None:
                return LLMResponse(content=json.dumps({"status": "complete", "confidence": 0.99, "rationale": "已有充分证据。", "missing": [], "next_action": "", "evidence": _completion_evidence_ids(messages)}))
            return LLMResponse(content="断流恢复后已完成检查。")

        def protocol(self) -> str:
            return "chat_completions"

        def protocol_status(self) -> dict[str, str]:
            return {"active": "chat_completions", "requested": "chat_completions"}

        async def close(self) -> None:
            return None

        @staticmethod
        def is_transient_failure(error: str | None) -> bool:
            return OpenAICompatibleProvider.is_transient_failure(error or "")

    monkeypatch.setattr("minicc.web.OpenAICompatibleProvider", FakeProvider)
    config = SimpleNamespace(
        yolo=False,
        max_concurrent_tasks=1,
        max_repair_attempts=0,
        task_recovery_retries=1,
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
        max_duration_seconds=20,
        max_tool_calls=20,
    )
    service = AgentService(tmp_path, config)
    try:
        result = service._chat_locked(
            {
                "message": "检查当前项目并给出结论",
                "session_id": "provider-recovery",
                "allow_changes": False,
                "workspace_path": str(tmp_path),
            },
            workspace=tmp_path,
        )
    finally:
        service.shutdown()

    assert result["error"] is None
    assert result["answer"] == "断流恢复后已完成检查。"
    assert result["metrics"]["provider_recoveries"] == 1
    assert len(instances) == 2
    assert any(event.get("code") == "task_provider_recovery" for event in result["events"])


def test_agent_service_recovers_stagnation_before_verifying_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    suite_python_bin: str,
) -> None:
    (tmp_path / ".minicc").mkdir()
    (tmp_path / ".minicc" / "verification.json").write_text(json.dumps({"rules": [{"paths": ["result.txt"], "commands": [f"{suite_python_bin} -m pytest -q tests/test_smoke.py"]}]}), encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_smoke.py").write_text(
        "def test_smoke():\n    assert True\n",
        encoding="utf-8",
    )

    class FakeProvider:
        def __init__(self, **_kwargs) -> None:
            self.agent_calls = 0
            self.inspection_call = False
            self.recovery_write = False
            self.verification_call = False

        async def chat(self, messages, tools, on_delta=None):
            rendered = json.dumps(messages, ensure_ascii=False)
            if tools is None:
                return LLMResponse(content=json.dumps({
                    "status": "complete",
                    "confidence": 0.98,
                    "rationale": "恢复后已写入目标文件并通过验证。",
                    "missing": [],
                    "next_action": "",
                    "evidence": _completion_evidence_ids(messages),
                }, ensure_ascii=False))

            self.agent_calls += 1
            if "[任务级错误恢复]" not in rendered:
                return LLMResponse(tool_calls=[{
                    "id": f"stuck-{self.agent_calls}",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": '{"path":"missing.txt"}',
                        },
                    }])
            if not self.inspection_call:
                self.inspection_call = True
                return LLMResponse(tool_calls=[{
                    "id": "recovery-tree",
                    "type": "function",
                    "function": {
                        "name": "tree",
                        "arguments": "{}",
                    },
                }])
            if not self.recovery_write:
                self.recovery_write = True
                return LLMResponse(tool_calls=[{
                    "id": "recovered-write",
                    "type": "function",
                    "function": {
                        "name": "write_file",
                        "arguments": json.dumps({"path": "result.txt", "content": "recovered\n"}),
                    },
                }])
            if not self.verification_call:
                self.verification_call = True
                return LLMResponse(tool_calls=[{
                    "id": "recovered-test",
                    "type": "function",
                    "function": {
                        "name": "bash",
                        "arguments": json.dumps({"command": f"{suite_python_bin} -m pytest -q"}),
                    },
                }])
            return LLMResponse(content="修改和验证已完成。")

        async def close(self) -> None:
            return None

        @staticmethod
        def is_transient_failure(error: str | None) -> bool:
            return False

    monkeypatch.setattr("minicc.web.OpenAICompatibleProvider", FakeProvider)
    config = SimpleNamespace(
        yolo=True,
        max_concurrent_tasks=1,
        max_repair_attempts=1,
        task_recovery_retries=1,
        sandbox_mode="host",
        sandbox_image="python:3.11-slim",
        base_url="https://example.test/v1",
        api_key="test-key",
        model="test-model",
        timeout=10,
        tool_mode="auto",
        reasoning_effort="high",
        max_turns=12,
        compact_threshold=300_000,
        context_window_tokens=300_000,
    )
    service = AgentService(tmp_path, config)
    try:
        result = service._chat_locked(
            {
                "message": "修复 result.txt 并验证",
                "session_id": "stagnation-recovery",
                "allow_changes": True,
                "workspace_path": str(tmp_path),
            },
            workspace=tmp_path,
        )
    finally:
        service.shutdown()

    assert result["error"] is None
    assert (tmp_path / "result.txt").read_text(encoding="utf-8") == "recovered\n"
    assert result["metrics"]["agent_recoveries"] == 1
    assert any(event.get("code") == "task_stagnation_recovery" for event in result["events"])
    assert any(event.get("code") == "verification_passed" for event in result["events"])
