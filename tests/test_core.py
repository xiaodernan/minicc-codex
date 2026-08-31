from __future__ import annotations

import json
import shutil
import subprocess
import sys
import threading
import time
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import asyncio

import pytest

import minicc.tools.web as web_tool
from minicc.agent.context import COMPACTION_MARKER, compact, compact_with_checkpoint, message_chars
from minicc.agent.completion import judge_completion, parse_completion_decision
from minicc.agent.graph import DAGPlan, GraphValidationError, NodeResult, PlanTask, build_coding_workflow, execute_dag, fixed_plan
from minicc.agent.orchestration import assess_complexity, build_auto_subtasks
from minicc.agent.planner import PlannerPolicy, build_plan, parse_planner_response, validate_dynamic_plan
from minicc.agent.repair import repair_scope
from minicc.agent.retrieval import LocalEvidenceIndex
from minicc.agent.router import StageRouter
from minicc.audit import authorize_tool
from minicc.benchmarks import build_report, load_tasks, markdown_report
from minicc.config import load_config, normalize_reasoning_effort
from minicc.agent.loop import run_agent
from minicc.agent.protocol import CancellationToken, EventLog, InvalidStatusTransition
from minicc.agent.state import AgentState, Budget, BudgetExceeded
from minicc.agent.verifier import VerificationCommand, Verifier
from minicc.llm.base import LLMResponse
from minicc.llm.envelope import EnvelopeParseError, extract_json_object, parse_envelope
from minicc.llm.openai_provider import OpenAICompatibleProvider, _is_stream_retryable, _merge_stream_text, _parse_usage
from minicc.session import SessionStore
from minicc.sandbox import SandboxRunner
from minicc.mcp import load_mcp_config
from minicc.tools.bash import decode_process_output, is_readonly_command, run_bash
from minicc.tools.editor import EditError, Editor, StaleContextError
from minicc.tools.schemas import ToolCall
from minicc.tools.web import parse_search_html
from minicc.tools import build_registry
from minicc.changes import ChangeInspector
from minicc.task_store import TaskStore
from minicc.web import AgentService, TaskManager, TaskRecord, _completion_guard_message, _multimodal_content
from minicc.worktree import WorktreeError, WorktreeManager
from minicc.prompt import build_system_prompt


def test_complexity_router_only_fans_out_for_multi_dimension_work() -> None:
    simple = assess_complexity("读取 README 并告诉我项目用途")
    assert simple.should_fan_out is False
    assert simple.child_count == 0

    complex_task = assess_complexity(
        "请分析前后端现状，修复登录和任务流式输出，同时优化界面，补充测试并运行验证，最后总结风险。"
    )
    assert complex_task.should_fan_out is True
    assert complex_task.child_count >= 2
    assert len(build_auto_subtasks("复杂需求", complex_task)) == complex_task.child_count

    opted_out = assess_complexity(
        "请分析前后端并修复问题，但不要拆分子任务，只由一个 Agent 完成。"
    )
    assert opted_out.should_fan_out is False


def test_compact_builds_valid_summary() -> None:
    messages = [{"role": "system", "content": "rules"}]
    messages.extend({"role": "user", "content": "x" * 50} for _ in range(8))
    compacted = compact(messages, threshold=100, keep_recent=2)
    assert COMPACTION_MARKER in compacted[1]["content"]
    assert len(compacted) == 4


def test_structured_compaction_preserves_coding_evidence_and_merges() -> None:
    messages = [{"role": "system", "content": "rules"}]
    messages.extend([
        {"role": "user", "content": "修复 parser.py，必须运行 pytest tests/test_parser.py 并完成验收。"},
        {
            "role": "assistant",
            "tool_calls": [{
                "id": "call-1",
                "type": "function",
                "function": {"name": "read_file", "arguments": '{"path":"minicc/parser.py"}'},
            }],
        },
        {"role": "tool", "name": "read_file", "content": "读取完成，sha256 digest: abcdef1234567890"},
        {"role": "assistant", "content": "验证失败：pytest tests/test_parser.py 报错。"},
        {"role": "user", "content": "继续处理 " + "x" * 200},
        {"role": "user", "content": "最近消息 " + "y" * 200},
    ])
    compacted, checkpoint = compact_with_checkpoint(messages, threshold=100, keep_recent=2)
    assert checkpoint is not None
    assert "minicc/parser.py" in checkpoint["files"]
    assert "abcdef1234567890" in checkpoint["digests"]
    assert any("pytest tests/test_parser.py" in item for item in checkpoint["verification"])
    assert checkpoint["failures"]
    assert checkpoint["loss_risk"]
    assert len(compacted) == 4

    compacted_again, checkpoint_again = compact_with_checkpoint(compacted, threshold=100, keep_recent=1)
    assert checkpoint_again is not None
    assert "minicc/parser.py" in checkpoint_again["files"]
    assert checkpoint_again["archive"]["messages"] >= checkpoint["archive"]["messages"]


def test_compaction_keeps_visual_reference_and_agent_restores_it() -> None:
    image = {
        "type": "image_url",
        "image_url": {"url": "data:image/png;base64,cG5nLWJ5dGVz"},
    }
    messages = [{"role": "system", "content": "rules"}]
    messages.append({
        "role": "user",
        "content": [{"type": "text", "text": "请根据图片完成任务"}, image],
    })
    messages.extend({"role": "user", "content": f"背景 {index} " + "x" * 80} for index in range(7))

    class FakeProvider:
        def __init__(self) -> None:
            self.requests: list[list[dict[str, object]]] = []

        async def chat(self, messages, tools, on_delta=None):
            self.requests.append(deepcopy(messages))
            return LLMResponse(content="已根据图片完成")

    provider = FakeProvider()
    result = asyncio.run(
        run_agent(
            provider,
            build_registry(Editor(Path.cwd())),
            messages,
            compact_threshold=100,
            vision_context=[image],
            should_allow=lambda _name, _call: True,
        )
    )

    assert result.answer == "已根据图片完成"
    assert result.compaction_events
    checkpoint = result.compaction_events[0]["checkpoint"]
    assert checkpoint["visual_attachments"][0]["mime_type"] == "image/png"
    assert message_chars(messages) < 4000
    assert provider.requests
    request_images = [
        part
        for message in provider.requests[0]
        for part in message.get("content", [])
        if isinstance(part, dict) and part.get("type") == "image_url"
    ]
    assert len(request_images) == 1
    assert any(event.get("code") == "vision_context_restored" for event in result.trace_events)


def test_completion_judge_receives_persistent_visual_context() -> None:
    image = {
        "type": "image_url",
        "image_url": {"url": "data:image/png;base64,cG5nLWJ5dGVz"},
    }
    requests: list[list[dict[str, object]]] = []

    class FakeProvider:
        async def chat(self, messages, tools, on_delta=None):
            requests.append(deepcopy(messages))
            return LLMResponse(content=json.dumps({
                "status": "complete",
                "confidence": 0.9,
                "rationale": "已结合截图和验证证据",
                "missing": [],
                "next_action": "",
                "evidence": ["截图已提供"],
            }))

    decision = asyncio.run(
        judge_completion(
            FakeProvider(),
            task="按截图实现页面",
            answer="页面已实现",
            events=[],
            verification_results=[],
            allow_changes=True,
            workspace="workspace",
            vision_context=[image],
        )
    )

    assert decision.status == "complete"
    assert requests
    review_content = requests[0][1]["content"]
    assert isinstance(review_content, list)
    assert "已提供 1 张图片" in review_content[0]["text"]
    assert review_content[1]["type"] == "image_url"


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


def test_agent_state_snapshot_contains_context_checkpoint() -> None:
    state = AgentState("checkpoint-test", "repair parser")
    state.set_context_checkpoint({"version": 1, "files": ["parser.py"]})
    snapshot = state.snapshot()
    assert snapshot["context_checkpoint"]["files"] == ["parser.py"]


def test_state_graph_repairs_verification_failure() -> None:
    graph = build_coding_workflow()
    state = AgentState("graph-test", "implement and verify", budget=Budget(max_turns=10))
    verify_calls = 0

    def handler(node: str):
        def run(_state: AgentState) -> NodeResult:
            nonlocal verify_calls
            if node == "verify":
                verify_calls += 1
                return NodeResult("failed" if verify_calls == 1 else "ok", error="test failed" if verify_calls == 1 else None)
            return NodeResult("ok")

        return run

    handlers = {name: handler(name) for name in graph.nodes}
    completed = asyncio.run(graph.run(state, handlers, max_steps=20))
    assert completed.status == "completed"
    assert verify_calls == 2
    assert any(event.get("node") == "repair" for event in completed.trace_events)


def test_dag_validates_dependencies_and_bounds_concurrency() -> None:
    plan = fixed_plan("parallel_inspect", task_count=3)
    running = 0
    maximum = 0

    async def handler(task):
        nonlocal running, maximum
        running += 1
        maximum = max(maximum, running)
        await asyncio.sleep(0.01)
        running -= 1
        return {"task": task.id}

    result = asyncio.run(execute_dag(plan, handler, max_concurrency=2))
    assert result.status == "completed"
    assert result.completed[-1] == "summarize"
    assert maximum <= 2
    with pytest.raises(GraphValidationError, match="存在环"):
        DAGPlan(
            "cycle",
            (
                PlanTask("a", "readonly", ("b",)),
                PlanTask("b", "readonly", ("a",)),
            ),
        ).validate()


def test_dag_can_pass_completed_dependency_outputs_to_handlers() -> None:
    plan = DAGPlan(
        "dependency-context",
        (
            PlanTask("inspect", "readonly"),
            PlanTask("review", "review", depends_on=("inspect",)),
        ),
    )
    seen: list[dict[str, dict[str, object]]] = []

    async def handler(task, dependencies):
        seen.append({key: dict(value) for key, value in dependencies.items()})
        return {"node": task.id}

    result = asyncio.run(execute_dag(
        plan,
        handler,
        max_concurrency=2,
        include_dependency_outputs=True,
    ))
    assert result.status == "completed"
    assert seen[-1] == {"inspect": {"node": "inspect", "status": "completed"}}


def test_verifier_returns_structured_failure_and_rejects_shell_composition(tmp_path: Path) -> None:
    def fake_executor(_command: str, _workspace: Path, _timeout: int):
        return SimpleNamespace(
            status="error",
            exit_code=1,
            render=lambda: "FAILED tests/test_demo.py::test_one - AssertionError",
        )

    verifier = Verifier(executor=fake_executor)
    result = verifier.run(tmp_path, [VerificationCommand("python -m pytest -q")])
    assert result.status == "failed"
    assert result.failed_tests == ["tests/test_demo.py::test_one"]
    assert result.to_event()["code"] == "verification_failed"
    blocked = verifier.run(tmp_path, [VerificationCommand("python -m pytest -q > report.txt")])
    assert blocked.status == "blocked"


def test_editor_rejects_escape_and_stale_write(tmp_path: Path) -> None:
    editor = Editor(tmp_path)
    with pytest.raises(EditError):
        editor.write_file("../outside.txt", "no")

    editor.write_file("note.txt", "one\n")
    digest = editor.file_digest("note.txt")
    (tmp_path / "note.txt").write_text("changed\n", encoding="utf-8")
    with pytest.raises(StaleContextError):
        editor.write_file("note.txt", "agent overwrite\n", expected_digest=digest)


def test_editor_requires_unique_edit(tmp_path: Path) -> None:
    editor = Editor(tmp_path)
    editor.write_file("note.txt", "same\nsame\n")
    with pytest.raises(EditError, match="不唯一"):
        editor.apply_edit("note.txt", "same", "new")


def test_envelope_parser_handles_fenced_json() -> None:
    obj = extract_json_object('说明 {"action":"read_file","params":{"path":"a.py"}}')
    assert obj == {"action": "read_file", "params": {"path": "a.py"}}
    call = parse_envelope('{"action":"read_file","params":{"path":"a.py"}}')
    assert call is not None
    assert ToolCall.from_openai(call).tool == "read_file"


def test_envelope_parser_accepts_model_dict_dialect_and_action_objects() -> None:
    call = parse_envelope("```json\n{'action': {'command': 'npm run test:web', 'timeout': 180}}\n```")
    assert call is not None
    parsed = ToolCall.from_openai(call)
    assert parsed.tool == "bash"
    assert parsed.arguments == {"command": "npm run test:web", "timeout": 180}
    assert parsed.parse_error is None


def test_envelope_parser_accepts_nested_named_action_arguments() -> None:
    call = parse_envelope(
        "{'action': {'name': 'grep', 'arguments': "
        "{'pattern': 'function (render|addAssistantMessage|syncLiveEvents|updateLiveTask', "
        "'path': 'web/app.js'}}}"
    )
    assert call is not None
    parsed = ToolCall.from_openai(call)
    assert parsed.tool == "grep"
    assert parsed.arguments == {
        "pattern": "function (render|addAssistantMessage|syncLiveEvents|updateLiveTask",
        "path": "web/app.js",
    }
    assert parsed.parse_error is None


def test_envelope_parser_reports_incomplete_output_as_repairable_error() -> None:
    with pytest.raises(EnvelopeParseError) as caught:
        parse_envelope("{'action': 'bash', 'params': {'command': 'npm run test:web'}")
    assert "不完整" in str(caught.value)
    assert caught.value.content.startswith("{")


def test_invalid_native_tool_arguments_become_model_feedback(tmp_path: Path) -> None:
    call = ToolCall.from_openai({
        "id": "bad-args",
        "type": "function",
        "function": {"name": "read_file", "arguments": "{'path': 'note.txt'"},
    })
    result = build_registry(Editor(tmp_path)).execute(call)
    assert result.status == "error"
    assert "INVALID_TOOL_ARGUMENTS" in result.summary


def test_registry_contains_readonly_git_tools(tmp_path: Path) -> None:
    registry = build_registry(Editor(tmp_path))
    assert registry.risk_of("git_status") == "readonly"
    assert registry.risk_of("git_diff") == "readonly"
    assert registry.risk_of("web_search") == "readonly"


def test_authorization_policy_requires_explicit_network_and_write_permission() -> None:
    readonly = authorize_tool("read_file", "readonly", {}, allow_changes=False, allow_network=False)
    assert readonly.allowed is True
    assert authorize_tool("write_file", "write", {}, allow_changes=False, allow_network=False).allowed is False
    assert authorize_tool("bash", "exec", {"command": "python -m pytest -q"}, allow_changes=False, allow_network=False).allowed is True
    assert authorize_tool("web_search", "readonly", {"query": "documentation"}, allow_changes=True, allow_network=False).allowed is False
    assert authorize_tool("web_search", "readonly", {"query": "documentation"}, allow_changes=False, allow_network=True).allowed is True
    assert authorize_tool("bash", "exec", {"command": "curl https://example.test"}, allow_changes=True, allow_network=False).allowed is False


def test_offline_benchmark_report_has_exact_fixtures_and_no_fabricated_results() -> None:
    tasks = load_tasks()
    report = build_report(tasks)
    assert len(tasks) == 30
    assert report["executed_count"] == 0
    assert report["metrics"]["pass_at_1"] is None
    assert all(item["status"] == "not_run" and item["cost_usd"] is None for item in report["results"])
    assert "N/A" in markdown_report(report)


def test_dynamic_planner_rejects_unsafe_tool_and_falls_back_to_fixed_plan() -> None:
    policy = PlannerPolicy(max_nodes=4, max_depth=3, max_concurrency=2)
    valid = validate_dynamic_plan({
        "name": "narrow",
        "tasks": [
            {"id": "inspect", "kind": "readonly", "allowed_tools": ["read_file"]},
            {"id": "verify", "kind": "exec", "depends_on": ["inspect"], "allowed_tools": ["bash"]},
        ],
    }, policy=policy)
    assert valid.name == "narrow"
    fallback = build_plan({"tasks": [{"id": "bad", "allowed_tools": ["web_search"]}]}, policy=policy)
    assert fallback.source == "fixed_fallback"
    assert fallback.plan.name == "inspect_implement_verify"


def test_model_planner_parses_wrapped_json_and_rejects_unknown_kind() -> None:
    policy = PlannerPolicy(max_nodes=4, max_depth=3, max_concurrency=2)
    parsed = parse_planner_response(
        "```json\n"
        '{"plan":{"name":"readonly-review","tasks":['
        '{"id":"inspect","kind":"readonly","allowed_tools":["read_file"]},'
        '{"id":"review","kind":"review","depends_on":["inspect"],"allowed_tools":["git_diff"]}'
        ']}}\n```',
        fallback_name="inspect_summarize",
        policy=policy,
    )
    assert parsed.source == "dynamic_model"
    assert parsed.plan.name == "readonly-review"
    invalid = parse_planner_response(
        '{"tasks":[{"id":"inspect","kind":"unknown","allowed_tools":["read_file"]}]}',
        fallback_name="inspect_summarize",
        policy=policy,
    )
    assert invalid.source == "fixed_fallback"
    assert invalid.plan.name == "inspect_summarize"
    assert invalid.reason


def test_agent_service_preflights_complex_tasks_with_a_safe_model_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"planner": 0, "agent": 0, "judge": 0}

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
                    "evidence": ["planner", "agent"],
                }, ensure_ascii=False))
            calls["agent"] += 1
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
    assert calls == {"planner": 1, "agent": 3, "judge": 1}
    assert result["context"]["planner"]["source"] == "dynamic_model"
    assert result["metrics"]["planner"]["plan"]["name"] == "readonly-review"
    assert result["metrics"]["planner"]["execution"]["status"] == "completed"
    assert result["metrics"]["planner"]["execution"]["completed"] == ["inspect", "review"]
    assert any(event.get("code") == "planner_started" for event in result["events"])
    assert any(event.get("code") == "planner_dynamic_ready" for event in result["events"])
    assert any(event.get("code") == "planner_execution_finished" for event in result["events"])


def test_local_evidence_index_and_repair_scope_are_bounded(tmp_path: Path) -> None:
    (tmp_path / "feature.py").write_text("def parse_widget():\n    return 1\n", encoding="utf-8")
    (tmp_path / ".env").write_text("MINICC_API_KEY=must-not-index\n", encoding="utf-8")
    hits = LocalEvidenceIndex(tmp_path).search("parse widget")
    assert hits and hits[0].path == "feature.py"
    assert all(".env" not in hit.path for hit in hits)
    scope = repair_scope(
        [{"write": True, "path": "feature.py"}, {"write": True, "path": "unrelated.css"}],
        {"failed_tests": ["tests/test_feature.py::test_parse_widget"]},
    )
    assert scope["repair_targets"] == ["feature.py"]


def test_stage_router_preserves_explicit_model_without_stage_turn_budget() -> None:
    route = StageRouter("terra", 100).route("inspect")
    assert route.model == "terra"
    assert route.timeout == 75.0
    assert route.max_turns is None
    assert "max_turns" not in route.to_dict()


def test_bash_output_decodes_windows_code_pages_without_crashing() -> None:
    encoded = "中文输出".encode("gb18030")
    assert decode_process_output(encoded) == "中文输出"


def test_bash_cancellation_terminates_long_running_process(tmp_path: Path) -> None:
    cancel_event = threading.Event()
    command = subprocess.list2cmdline([
        sys.executable,
        "-c",
        'import time; print("started", flush=True); time.sleep(30)',
    ])
    result_box: dict[str, object] = {}

    def run() -> None:
        result_box["result"] = run_bash(
            command,
            tmp_path,
            timeout=30,
            cancel_event=cancel_event,
        )

    worker = threading.Thread(target=run)
    worker.start()
    try:
        time.sleep(0.25)
        cancel_event.set()
        worker.join(8)
        assert not worker.is_alive(), "cancelled bash must not leave the task thread blocked"
        result = result_box["result"]
        assert result.status == "cancelled"
        assert "终止进程树" in result.summary
    finally:
        cancel_event.set()
        worker.join(8)


def test_change_request_cannot_be_marked_complete_after_text_only_reply() -> None:
    result = SimpleNamespace(error=None, cancelled=False, answer="我已经确认了问题，准备继续处理。")
    guard = _completion_guard_message(
        "修复这些 bug 并继续做完，不要提前结束。",
        result,
        [{"name": "git_status", "status": "ok", "write": False}],
        True,
    )
    assert guard == "模型在没有完成任何工作区修改前结束了任务"
    assert _completion_guard_message(
        "只读检查当前项目，不要修改文件。",
        result,
        [],
        True,
    ) is None


def test_change_request_cannot_claim_no_changes_after_readonly_verification() -> None:
    result = SimpleNamespace(
        error=None,
        cancelled=False,
        answer="我已检查项目，当前已经实现，无需修改。接下来会继续修复。",
    )
    guard = _completion_guard_message(
        "修复这些 bug 并继续做完。",
        result,
        [
            {"name": "git_status", "status": "ok", "write": False},
            {"name": "read_file", "status": "ok", "write": False},
        ],
        True,
    )
    assert guard == "模型在没有完成任何工作区修改前结束了任务"


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


def test_agent_service_runs_verifier_after_successful_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_smoke.py").write_text("def test_smoke():\n    assert True\n", encoding="utf-8")

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
                        "evidence": ["write_file", "pytest"],
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
                                "arguments": json.dumps({"command": "python -m pytest -q"}),
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


def test_completion_decision_parser_accepts_fenced_json_and_rejects_unknown() -> None:
    decision = parse_completion_decision(
        "```json\n"
        '{"status":"continue","confidence":92,"rationale":"缺少测试",'
        '"missing":["运行测试"],"next_action":"运行 pytest",'
        '"evidence":["发现修改"]}\n```'
    )
    assert decision.status == "continue"
    assert decision.confidence == 0.92
    assert decision.missing == ["运行测试"]
    assert parse_completion_decision("模型说了一段普通话").status == "unknown"


def test_completion_judge_replans_text_only_reply_until_workspace_is_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeProvider:
        def __init__(self, **_kwargs) -> None:
            self.agent_calls = 0
            self.judge_calls = 0

        async def chat(self, messages, tools, on_delta=None):
            if tools is None:
                self.judge_calls += 1
                status = "continue" if self.judge_calls == 1 else "complete"
                return LLMResponse(content=json.dumps({
                    "status": status,
                    "confidence": 0.95,
                    "rationale": "首轮没有修改；后续已写入并取得读取证据。" if status == "complete" else "还没有实际创建游戏文件。",
                    "missing": [] if status == "complete" else ["创建游戏文件"],
                    "next_action": "创建 game.html" if status == "continue" else "",
                    "evidence": ["write_file", "read_file"] if status == "complete" else [],
                }, ensure_ascii=False))
            self.agent_calls += 1
            if self.agent_calls == 1:
                return LLMResponse(content="我先确认一下需求，稍后处理。")
            if self.agent_calls == 2:
                return LLMResponse(tool_calls=[{
                    "id": "write-game",
                    "type": "function",
                    "function": {
                        "name": "write_file",
                        "arguments": json.dumps({
                            "path": "game.html",
                            "content": "<!doctype html><title>Mini game</title>\n",
                        }),
                    },
                }])
            if self.agent_calls == 3:
                return LLMResponse(tool_calls=[{
                    "id": "read-game",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": '{"path":"game.html"}',
                    },
                }])
            return LLMResponse(content="游戏文件已经创建并检查完成。")

        async def close(self) -> None:
            return None

    monkeypatch.setattr("minicc.web.OpenAICompatibleProvider", FakeProvider)
    config = SimpleNamespace(
        yolo=True,
        max_concurrent_tasks=1,
        max_repair_attempts=1,
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
                "message": "制作一个可打开的小游戏并完成验证",
                "session_id": "completion-replan",
                "allow_changes": True,
                "workspace_path": str(tmp_path),
            },
            workspace=tmp_path,
        )
    finally:
        service.shutdown()
    assert result["error"] is None
    assert result["completion"]["status"] == "complete"
    assert (tmp_path / "game.html").is_file()
    assert any(event.get("code") == "completion_continue" for event in result["events"])
    assert any(event.get("code") == "completion_complete" for event in result["events"])


def test_search_parser_supports_duckduckgo_lite_redirects() -> None:
    html = """
    <a class='result-link' href='//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fdocs'>Docs</a>
    <td class='result-snippet'>A short result summary.</td>
    """
    results = parse_search_html(html, 3)
    assert results == [{
        "title": "Docs",
        "url": "https://example.com/docs",
        "snippet": "A short result summary.",
    }]


def test_search_parser_supports_bing_result_cards() -> None:
    html = """
    <li class="b_algo">
      <h2><a href="https://example.com/docs">A <strong>title</strong></a></h2>
      <div class="b_caption"><p class="b_lineclamp2">A short result summary.</p></div>
    </li>
    """
    assert parse_search_html(html, 3) == [{
        "title": "A title",
        "url": "https://example.com/docs",
        "snippet": "A short result summary.",
    }]


def test_web_search_caches_results_and_marks_cache_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    web_tool._SEARCH_CACHE.clear()
    calls = 0

    def fake_fetch(_query: str) -> web_tool._SearchFetch:
        nonlocal calls
        calls += 1
        return web_tool._SearchFetch(
            source="test",
            results=[{"title": "Docs", "url": "https://example.com", "snippet": "summary"}],
            diagnostics=[],
        )

    monkeypatch.setattr(web_tool, "_fetch_search", fake_fetch)
    first = web_tool.web_search({"query": "cache me", "max_results": 1})
    second = web_tool.web_search({"query": "cache me", "max_results": 1})
    assert calls == 1
    assert first.data["cached"] is False
    assert second.data["cached"] is True


def test_reasoning_effort_aliases_are_normalized() -> None:
    assert normalize_reasoning_effort("standard") == "mid"
    assert normalize_reasoning_effort("low") == "low"
    assert normalize_reasoning_effort("mid") == "mid"
    assert normalize_reasoning_effort("high") == "high"
    assert normalize_reasoning_effort("xhigh") == "xhigh"
    assert normalize_reasoning_effort("very-high") == "xhigh"


def test_provider_sends_reasoning_budget() -> None:
    seen: dict[str, object] = {}
    provider = OpenAICompatibleProvider(
        "https://example.com/v1",
        "test-key",
        "test-model",
        reasoning_effort="max",
        protocol="chat_completions",
        sdk_client=object(),
    )

    async def fake_create(kwargs: dict[str, object]) -> object:
        seen.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content="done", tool_calls=[]),
                finish_reason="stop",
            )],
            usage=None,
            model="test-model",
        )

    provider._create = fake_create  # type: ignore[method-assign]
    response = asyncio.run(provider.chat([{"role": "user", "content": "test"}], tools=None))
    assert response.content == "done"
    assert seen["reasoning_effort"] == "max"


def test_provider_normalizes_cache_usage_across_gateway_shapes() -> None:
    chat_usage = _parse_usage({
        "prompt_tokens": 2174,
        "completion_tokens": 18,
        "total_tokens": 2192,
        "prompt_tokens_details": {"cached_tokens": 1792},
    })
    assert chat_usage["prompt_cache_hit_tokens"] == 1792
    assert chat_usage["prompt_cache_miss_tokens"] == 382
    assert chat_usage["cache_hit_rate"] == round(1792 / 2174, 6)
    assert chat_usage["cache_status"] == "hit"

    responses_usage = _parse_usage(SimpleNamespace(
        input_tokens=2174,
        output_tokens=18,
        total_tokens=2192,
        input_tokens_details=SimpleNamespace(cached_tokens=0),
    ))
    assert responses_usage["prompt_cache_hit_tokens"] == 0
    assert responses_usage["prompt_cache_miss_tokens"] == 2174
    assert responses_usage["cache_hit_rate"] == 0.0
    assert responses_usage["cache_status"] == "miss"

    deepseek_usage = _parse_usage({
        "prompt_tokens": 100,
        "completion_tokens": 10,
        "prompt_cache_hit_tokens": 60,
        "prompt_cache_miss_tokens": 40,
        "cache_write_tokens": 12,
    })
    assert deepseek_usage["prompt_cache_write_tokens"] == 12
    assert deepseek_usage["cache_hit_rate"] == 0.6

    unreported = _parse_usage({"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110})
    assert unreported["cache_status"] == "unreported"
    assert unreported["cache_hit_rate"] is None
    assert "prompt_cache_hit_tokens" not in unreported


@pytest.mark.parametrize(
    "command",
    [
        "pytest -q -p no:cacheprovider",
        "python -m pytest tests/test_core.py",
        r".\\.venv\\Scripts\\python.exe -m pytest -q",
    ],
)
def test_safe_web_command_allows_readonly_pytest(command: str) -> None:
    assert is_readonly_command(command)


@pytest.mark.parametrize(
    "command",
    [
        "python -c print('unsafe')",
        "pytest && del important.txt",
        "pytest > report.txt",
        "powershell -Command Get-ChildItem",
    ],
)
def test_safe_web_command_rejects_other_shell_commands(command: str) -> None:
    assert not is_readonly_command(command)


def test_sensitive_file_is_not_read(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("MINICC_API_KEY=sk-secret-value\n", encoding="utf-8")
    result = build_registry(Editor(tmp_path)).execute(
        ToolCall("read_file", {"path": ".env"})
    )
    assert result.status == "error"
    assert "拒绝访问敏感文件" in result.summary


def test_grep_accepts_single_file_and_read_window_errors_are_explicit(tmp_path: Path) -> None:
    target = tmp_path / "demo.py"
    target.write_text("alpha = 1\nbeta = 2\n", encoding="utf-8")
    registry = build_registry(Editor(tmp_path))

    grep_result = registry.execute(ToolCall("grep", {"pattern": "beta", "path": "demo.py"}))
    assert grep_result.status == "ok"
    assert "demo.py:2: beta = 2" in grep_result.render()

    window_result = registry.execute(
        ToolCall("read_file", {"path": "demo.py", "offset": 99, "limit": 10})
    )
    assert window_result.status == "error"
    assert "读取窗口为空或越界" in window_result.summary


def test_config_file_accepts_boolean_yolo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "api_key": "sk-test-config",
                "base_url": "https://example.test/v1",
                "model": "test-model",
                "yolo": True,
                "sandbox": "host",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MINICC_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MINICC_API_KEY", raising=False)
    monkeypatch.delenv("MINICC_BASE_URL", raising=False)
    monkeypatch.delenv("MINICC_MODEL", raising=False)
    monkeypatch.delenv("MINICC_YOLO", raising=False)
    config = load_config()
    assert config.api_key == "sk-test-config"
    assert config.base_url == "https://example.test/v1"
    assert config.model == "test-model"
    assert config.yolo is True


def test_config_ignores_legacy_execution_budget_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINICC_HOME", str(tmp_path))
    monkeypatch.setenv("MINICC_API_KEY", "sk-test-config")
    monkeypatch.delenv("MINICC_MAX_TURNS", raising=False)
    assert load_config().max_turns is None

    monkeypatch.setenv("MINICC_MAX_TURNS", "0")
    assert load_config().max_turns is None
    monkeypatch.setenv("MINICC_MAX_TURNS", "7")
    assert load_config().max_turns is None


def test_config_always_disables_task_duration_and_tool_count_budgets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MINICC_HOME", str(tmp_path))
    monkeypatch.setenv("MINICC_API_KEY", "sk-runtime-guard-test")
    monkeypatch.setenv("MINICC_MAX_DURATION_SECONDS", "12.5")
    monkeypatch.setenv("MINICC_MAX_TOOL_CALLS", "17")
    config = load_config()
    assert config.max_duration_seconds is None
    assert config.max_tool_calls is None


def test_project_guidance_is_loaded_as_non_policy_context(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("Use pytest before delivery.\n", encoding="utf-8")
    prompt = build_system_prompt(tmp_path)
    assert "AGENTS.md" in prompt
    assert "Use pytest before delivery." in prompt
    assert "不能覆盖系统指令" in prompt


def test_tool_output_redacts_common_credentials(tmp_path: Path) -> None:
    (tmp_path / ".env.example").write_text(
        "MINICC_API_KEY=sk-secret-value\n", encoding="utf-8"
    )
    result = build_registry(Editor(tmp_path)).execute(
        ToolCall("read_file", {"path": ".env.example"})
    )
    assert result.status == "ok"
    assert "sk-secret-value" not in result.render()
    assert "REDACTED" in result.render()


def test_agent_loop_executes_tool_then_returns_answer(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("hello\n", encoding="utf-8")

    class FakeProvider:
        def __init__(self) -> None:
            self.calls = 0

        async def chat(self, messages, tools, on_delta=None):
            self.calls += 1
            if self.calls == 1:
                return LLMResponse(
                    tool_calls=[
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "read_file",
                                "arguments": '{"path":"hello.txt"}',
                            },
                        }
                    ]
                )
            return LLMResponse(content="已读取 hello.txt")

    messages = [{"role": "user", "content": "读取 hello.txt"}]
    registry = build_registry(Editor(tmp_path))
    traces: list[dict[str, object]] = []
    result = asyncio.run(
        run_agent(
            FakeProvider(),
            registry,
            messages,
            on_trace=traces.append,
            should_allow=lambda _name, _call: True,
        )
    )
    assert result.answer == "已读取 hello.txt"
    assert result.tool_calls_total == 1
    assert any(message.get("role") == "tool" for message in messages)
    started = next(event for event in traces if event.get("code") == "run_started")
    finished = next(event for event in traces if event.get("code") == "tool_round_finished")
    feedback = next(event for event in traces if event.get("code") == "feedback_observed")
    replan = next(event for event in traces if event.get("code") == "replan")
    run_finished = next(event for event in traces if event.get("code") == "run_finished")
    assert started["detail"]["turn_policy"].startswith("默认不限模型轮次")
    assert run_finished["summary"] == "执行结束，待验收"
    assert run_finished["phase"] == "review"
    assert finished["detail"]["results"][0]["tool"] == "read_file"
    assert "hello" in finished["detail"]["results"][0]["observation"]
    assert finished["detail"]["results"][0]["structured_data"]["digest"]
    assert finished["detail"]["basis"]
    assert feedback["detail"]["observations"]
    assert feedback["detail"]["basis"]
    assert replan["detail"]["observed"]
    assert replan["detail"]["basis"]


def test_multimodal_content_keeps_text_and_image_parts() -> None:
    content = _multimodal_content(
        "请描述图片",
        [{"mime_type": "image/png", "data": b"png-bytes"}],
    )
    assert isinstance(content, list)
    assert content[0] == {"type": "text", "text": "请描述图片"}
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_task_snapshot_hides_attachment_payload_and_resume_reloads_it(tmp_path: Path) -> None:
    received: list[list[dict[str, object]]] = []

    class FakeService:
        config = SimpleNamespace(yolo=False, max_concurrent_tasks=1)
        workspace = tmp_path

        @staticmethod
        def _run_chat(payload, *, on_event=None, on_stream=None, cancel_event=None):
            received.append(payload.get("attachments") or [])
            return {"answer": "image inspected", "cancelled": False, "events": []}

    manager = TaskManager(FakeService(), max_workers=1)
    try:
        task = manager.submit({
            "message": "请分析图片",
            "session_id": "image-test",
            "attachments": [{
                "name": "screen.png",
                "mime_type": "image/png",
                "data_url": "data:image/png;base64,cG5nLWJ5dGVz",
            }],
        })
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and manager.get(task["task_id"])["status"] != "completed":
            time.sleep(0.01)
        snapshot = manager.get(task["task_id"])
        assert snapshot["status"] == "completed"
        assert snapshot["attachments"][0]["name"] == "screen.png"
        assert "data_url" not in snapshot["attachments"][0]
        assert received[0][0]["data_url"].startswith("data:image/png;base64,")

        resumed = manager.resume(task["task_id"])
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and manager.get(resumed["task_id"])["status"] != "completed":
            time.sleep(0.01)
        assert len(received) == 2
        assert received[1][0]["name"] == "screen.png"
    finally:
        manager.shutdown()


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


def test_agent_loop_forwards_streaming_text_deltas(tmp_path: Path) -> None:
    class FakeProvider:
        async def chat(self, messages, tools, on_delta=None):
            for chunk in ("第一段", "第二段", "第三段"):
                if on_delta is not None:
                    on_delta(chunk)
            return LLMResponse(content="第一段第二段第三段")

    deltas: list[str] = []
    result = asyncio.run(
        run_agent(
            FakeProvider(),
            build_registry(Editor(tmp_path)),
            [{"role": "user", "content": "给我一个简短回答"}],
            on_stream=deltas.append,
            should_allow=lambda _name, _call: True,
        )
    )
    assert deltas == ["第一段", "第二段", "第三段"]
    assert result.answer == "第一段第二段第三段"


def test_agent_loop_deduplicates_cumulative_public_stream_updates(tmp_path: Path) -> None:
    class FakeProvider:
        async def chat(self, messages, tools, on_delta=None):
            for chunk in ("aa", "aab", "aabc"):
                if on_delta is not None:
                    on_delta(chunk)
            return LLMResponse(content="aabc")

    deltas: list[str] = []
    result = asyncio.run(
        run_agent(
            FakeProvider(),
            build_registry(Editor(tmp_path)),
            [{"role": "user", "content": "给我一个简短回答"}],
            on_stream=deltas.append,
            should_allow=lambda _name, _call: True,
        )
    )
    assert deltas == ["aa", "b", "c"]
    assert result.answer == "aabc"


def test_provider_deduplicates_cumulative_stream_chunks() -> None:
    class FakeStream:
        def __init__(self, chunks: list[object]) -> None:
            self.chunks = iter(chunks)

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self.chunks)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

        async def aclose(self) -> None:
            return None

    chunks = [
        SimpleNamespace(model="test-model", usage=None, choices=[SimpleNamespace(finish_reason=None, delta=SimpleNamespace(content=value, reasoning_content=None, tool_calls=[]))])
        for value in ("aa", "aab", "aabc")
    ] + [SimpleNamespace(model="test-model", usage=None, choices=[SimpleNamespace(finish_reason="stop", delta=SimpleNamespace(content=None, reasoning_content=None, tool_calls=[]))])]
    provider = OpenAICompatibleProvider(
        "https://example.com/v1", "test-key", "test-model", protocol="chat_completions", sdk_client=object()
    )

    async def fake_create(_kwargs: dict[str, object]) -> FakeStream:
        return FakeStream(chunks)

    provider._create = fake_create  # type: ignore[method-assign]
    deltas: list[str] = []
    response = asyncio.run(provider.chat([{"role": "user", "content": "test"}], on_delta=deltas.append))
    assert deltas == ["aa", "b", "c"]
    assert response.content == "aabc"
    assert _merge_stream_text("aa", "aab") == ("aab", "b")


def test_provider_retries_silent_incomplete_stream() -> None:
    class FakeStream:
        def __init__(self, chunks: list[object]) -> None:
            self.chunks = iter(chunks)

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self.chunks)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

        async def aclose(self) -> None:
            return None

    calls = 0
    provider = OpenAICompatibleProvider(
        "https://example.com/v1", "test-key", "test-model", protocol="chat_completions", max_retries=1, sdk_client=object()
    )

    async def fake_create(_kwargs: dict[str, object]) -> FakeStream:
        nonlocal calls
        calls += 1
        text = "partial" if calls == 1 else "partial complete"
        terminal = calls > 1
        return FakeStream([
            SimpleNamespace(
                model="test-model",
                usage=None,
                choices=[SimpleNamespace(
                    finish_reason="stop" if terminal else None,
                    delta=SimpleNamespace(content=text, reasoning_content=None, tool_calls=[]),
                )],
            )
        ])

    provider._create = fake_create  # type: ignore[method-assign]
    deltas: list[str] = []
    response = asyncio.run(provider.chat([{"role": "user", "content": "test"}], on_delta=deltas.append))
    assert calls == 2
    assert deltas == ["partial", " complete"]
    assert response.content == "partial complete"


def test_agent_repairs_invalid_envelope_instead_of_ending_run(tmp_path: Path) -> None:
    class FakeProvider:
        def __init__(self) -> None:
            self.calls = 0

        async def chat(self, messages, tools, on_delta=None):
            self.calls += 1
            if self.calls == 1:
                raise EnvelopeParseError("信封缺少 action 字段", content="{'params': {}}")
            return LLMResponse(content="协议已修正，任务完成。")

    traces: list[dict[str, object]] = []
    provider = FakeProvider()
    result = asyncio.run(
        run_agent(
            provider,
            build_registry(Editor(tmp_path)),
            [{"role": "user", "content": "完成一个检查"}],
            on_trace=traces.append,
            should_allow=lambda _name, _call: True,
        )
    )
    assert provider.calls == 2
    assert result.error is None
    assert result.answer == "协议已修正，任务完成。"
    assert any(event.get("code") == "protocol_repair" for event in traces)


def test_agent_loop_disables_streaming_without_output_callback(tmp_path: Path) -> None:
    seen: list[object] = []

    class FakeProvider:
        async def chat(self, messages, tools, on_delta=None):
            seen.append(on_delta)
            return LLMResponse(content="非流式回答")

    result = asyncio.run(
        run_agent(
            FakeProvider(),
            build_registry(Editor(tmp_path)),
            [{"role": "user", "content": "给我一个简短回答"}],
            should_allow=lambda _name, _call: True,
        )
    )
    assert seen == [None]
    assert result.answer == "非流式回答"


def test_agent_emits_public_model_update_before_tool_events(tmp_path: Path) -> None:
    (tmp_path / "note.txt").write_text("evidence\n", encoding="utf-8")

    class FakeProvider:
        def __init__(self) -> None:
            self.calls = 0

        async def chat(self, messages, tools, on_delta=None):
            self.calls += 1
            if self.calls == 1:
                return LLMResponse(
                    content="我会先读取 note.txt，再根据内容给出结论。",
                    reasoning_content="private reasoning must never be shown",
                    tool_calls=[{
                        "id": "read-note",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": '{\"path\":\"note.txt\"}'},
                    }],
                )
            return LLMResponse(content="已读取并完成结论。")

    traces: list[dict[str, object]] = []
    result = asyncio.run(
        run_agent(
            FakeProvider(),
            build_registry(Editor(tmp_path)),
            [{"role": "user", "content": "读取 note.txt"}],
            on_trace=traces.append,
            should_allow=lambda _name, _call: True,
        )
    )
    codes = [str(event.get("code")) for event in traces]
    update = next(event for event in traces if event.get("code") == "model_update")
    assert update["detail"] == {"turn": 1, "text": "我会先读取 note.txt，再根据内容给出结论。"}
    assert codes.index("model_update") < codes.index("model_decision") < codes.index("tool_round_started")
    assert "private reasoning" not in json.dumps(traces, ensure_ascii=False)
    assert result.answer == "已读取并完成结论。"


def test_agent_requires_verification_after_a_successful_write(tmp_path: Path) -> None:
    class FakeProvider:
        def __init__(self) -> None:
            self.calls = 0

        async def chat(self, messages, tools, on_delta=None):
            self.calls += 1
            if self.calls == 1:
                return LLMResponse(
                    tool_calls=[{
                        "id": "write-1",
                        "type": "function",
                        "function": {
                            "name": "write_file",
                            "arguments": '{"path":"changed.txt","content":"changed\\n"}',
                        },
                    }]
                )
            return LLMResponse(content="已经完成修改。")

    traces: list[dict[str, object]] = []
    provider = FakeProvider()
    result = asyncio.run(
        run_agent(
            provider,
            build_registry(Editor(tmp_path)),
            [{"role": "user", "content": "修改 changed.txt 并完成验证"}],
            max_turns=6,
            on_trace=traces.append,
            should_allow=lambda _name, _call: True,
        )
    )
    assert result.error == "Agent 在修改工作区后没有完成验证"
    assert (tmp_path / "changed.txt").read_text(encoding="utf-8") == "changed\n"
    assert any(event.get("code") == "verification_required_before_finish" for event in traces)


def test_agent_loop_replans_once_then_stops_repeated_tool_calls(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("hello\n", encoding="utf-8")

    class FakeProvider:
        def __init__(self) -> None:
            self.calls = 0

        async def chat(self, messages, tools, on_delta=None):
            self.calls += 1
            return LLMResponse(
                tool_calls=[
                    {
                        "id": f"call-{self.calls}",
                        "type": "function",
                        "function": {
                            "name": "read_file",
                            "arguments": '{"path":"hello.txt"}',
                        },
                    }
                ]
            )

    traces: list[dict[str, object]] = []
    provider = FakeProvider()
    result = asyncio.run(
        run_agent(
            provider,
            build_registry(Editor(tmp_path)),
            [{"role": "user", "content": "检查 hello.txt"}],
            max_turns=12,
            on_trace=traces.append,
            should_allow=lambda _name, _call: True,
        )
    )
    assert result.error and "停滞保护" in result.error
    assert any(event.get("code") == "stagnation_replan" for event in traces)
    assert any(event.get("code") == "stagnation_guard" for event in traces)
    assert provider.calls < 12


def test_agent_loop_recovers_duplicate_path_with_readonly_probe(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("hello\n", encoding="utf-8")

    class FakeProvider:
        def __init__(self) -> None:
            self.calls = 0

        async def chat(self, messages, tools, on_delta=None):
            self.calls += 1
            rendered = json.dumps(messages, ensure_ascii=False)
            if self.calls <= 3:
                return LLMResponse(tool_calls=[{
                    "id": f"read-{self.calls}",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": '{"path":"hello.txt"}',
                    },
                }])
            if self.calls == 4 and "执行器恢复第" in rendered:
                return LLMResponse(tool_calls=[{
                    "id": "glob-after-recovery",
                    "type": "function",
                    "function": {
                        "name": "glob",
                        "arguments": '{"pattern":"*.txt"}',
                    },
                }])
            return LLMResponse(content="已基于恢复诊断完成检查。")

    traces: list[dict[str, object]] = []
    provider = FakeProvider()
    result = asyncio.run(
        run_agent(
            provider,
            build_registry(Editor(tmp_path)),
            [{"role": "user", "content": "检查 hello.txt"}],
            max_turns=8,
            on_trace=traces.append,
            should_allow=lambda _name, _call: True,
        )
    )

    assert result.error is None
    assert result.answer == "已基于恢复诊断完成检查。"
    assert provider.calls == 5
    assert any(event.get("code") == "recovery_probe_finished" for event in traces)
    assert any(event.get("code") == "stagnation_replan" for event in traces)
    assert any(event.get("code") == "recovery_inspection_passed" for event in traces)


def test_agent_loop_skips_duplicate_calls_in_same_round(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("hello\n", encoding="utf-8")

    class FakeProvider:
        def __init__(self) -> None:
            self.calls = 0

        async def chat(self, messages, tools, on_delta=None):
            self.calls += 1
            if self.calls == 1:
                call = {
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": '{"path":"hello.txt"}',
                    },
                }
                return LLMResponse(tool_calls=[{**call, "id": "read-1"}, {**call, "id": "read-2"}])
            return LLMResponse(content="检查完成。")

    traces: list[dict[str, object]] = []
    result = asyncio.run(
        run_agent(
            FakeProvider(),
            build_registry(Editor(tmp_path)),
            [{"role": "user", "content": "检查 hello.txt"}],
            max_turns=4,
            on_trace=traces.append,
            should_allow=lambda _name, _call: True,
        )
    )

    finished = next(event for event in traces if event.get("code") == "tool_round_finished")
    statuses = finished["detail"]["statuses"]  # type: ignore[index]
    assert any("DUPLICATE_TOOL_CALL" in str(item) for item in finished["detail"]["results"])  # type: ignore[index]
    assert statuses == ["read_file:ok", "read_file:error"]
    assert result.error is None


def test_agent_service_recovers_stagnation_before_verifying_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
                    "evidence": ["write_file", "pytest"],
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
                        "arguments": '{"command":"python -m pytest -q"}',
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


def test_agent_marks_max_turns_as_incomplete(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("hello\n", encoding="utf-8")

    class FakeProvider:
        async def chat(self, messages, tools, on_delta=None):
            return LLMResponse(tool_calls=[{
                "id": "read-1",
                "type": "function",
                "function": {
                    "name": "read_file",
                    "arguments": '{"path":"hello.txt"}',
                },
            }])

    result = asyncio.run(
        run_agent(
            FakeProvider(),
            build_registry(Editor(tmp_path)),
            [{"role": "user", "content": "检查 hello.txt"}],
            max_turns=1,
            should_allow=lambda _name, _call: True,
        )
    )
    assert result.error == "Agent 达到最大执行轮次 1，任务未完成"


def test_agent_deadline_cancels_an_inflight_provider_request(tmp_path: Path) -> None:
    cancelled: list[bool] = []

    class FakeProvider:
        async def chat(self, messages, tools, on_delta=None):
            try:
                await asyncio.sleep(2)
            except asyncio.CancelledError:
                cancelled.append(True)
                raise
            return LLMResponse(content="迟到的回答")

    result = asyncio.run(
        run_agent(
            FakeProvider(),
            build_registry(Editor(tmp_path)),
            [{"role": "user", "content": "检查任务"}],
            budget=Budget(max_duration_seconds=0.08),
            should_allow=lambda _name, _call: True,
        )
    )
    assert result.error and "最大执行时间" in result.error
    assert cancelled == [True]
    assert any(event.get("code") == "budget_exceeded" for event in result.trace_events)


def test_agent_has_no_default_fixed_turn_cap(tmp_path: Path) -> None:
    for index in range(1, 42):
        (tmp_path / f"probe-{index}.txt").write_text(f"probe {index}\n", encoding="utf-8")

    class FakeProvider:
        def __init__(self) -> None:
            self.calls = 0

        async def chat(self, messages, tools, on_delta=None):
            self.calls += 1
            if self.calls > 41:
                return LLMResponse(content="完成")
            return LLMResponse(tool_calls=[{
                "id": f"read-{self.calls}",
                "type": "function",
                "function": {
                    "name": "read_file",
                    "arguments": json.dumps({"path": f"probe-{self.calls}.txt"}),
                },
            }])

    provider = FakeProvider()
    result = asyncio.run(
        run_agent(
            provider,
            build_registry(Editor(tmp_path)),
            [{"role": "user", "content": "逐个检查这些文件"}],
            should_allow=lambda _name, _call: True,
        )
    )
    assert provider.calls == 42
    assert result.error is None
    assert result.answer == "完成"


def test_session_round_trip_redacts_credentials(tmp_path: Path) -> None:
    store = SessionStore(tmp_path, "interview-1")
    store.save(
        [
            {"role": "system", "content": "rules"},
            {"role": "user", "content": "token sk-secret-value"},
        ]
    )
    loaded = store.load("new rules")
    assert loaded[0]["content"] == "new rules"
    assert "sk-secret-value" not in store.path.read_text(encoding="utf-8")


def test_sandbox_docker_mode_fails_closed_when_docker_is_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("minicc.sandbox.shutil.which", lambda _name: None)
    runner = SandboxRunner("docker")
    assert runner.status()["backend"] == "unavailable"
    assert runner.status()["isolated"] is False
    result = runner.run("echo should-not-run", tmp_path)
    assert result.status == "error"
    assert "SANDBOX_UNAVAILABLE" in result.summary


def test_mcp_config_loads_opt_in_servers(tmp_path: Path) -> None:
    config_dir = tmp_path / ".minicc"
    config_dir.mkdir()
    (config_dir / "mcp.json").write_text(
        json.dumps({"servers": {"docs": {"command": sys.executable, "args": ["server.py"], "read_only": True}}}),
        encoding="utf-8",
    )
    configs = load_mcp_config(tmp_path)
    assert len(configs) == 1
    assert configs[0].name == "docs"
    assert configs[0].read_only is True


def test_worktree_manager_creates_and_removes_managed_tree(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "minicc test"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("test\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)

    manager = WorktreeManager(tmp_path)
    try:
        item = manager.create("feature-test", "feature-test")
        assert item["managed"] is True
        assert Path(item["path"]).is_dir()
        removed = manager.remove("feature-test")
        assert removed["removed"] is True
        with pytest.raises(WorktreeError):
            manager.create("../escape")
    finally:
        shutil.rmtree(manager.root, ignore_errors=True)


def test_task_manager_runs_batch_in_parallel() -> None:
    class FakeService:
        config = SimpleNamespace(yolo=False)

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
        config = SimpleNamespace(yolo=False, max_concurrent_tasks=4)
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


def test_batch_merge_passes_reasoning_effort_to_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    class FakeProvider:
        def __init__(self, **kwargs):
            seen.update(kwargs)

        async def chat(self, **kwargs):
            return LLMResponse(content="merged", usage={"total_tokens": 3})

        async def close(self) -> None:
            return None

    monkeypatch.setattr("minicc.web.OpenAICompatibleProvider", FakeProvider)
    service = SimpleNamespace(
        config=SimpleNamespace(
            base_url="https://example.test/v1",
            api_key="test-key",
            model="test-model",
            timeout=30,
            tool_mode="auto",
            reasoning_effort="high",
        )
    )

    result = AgentService.merge_batch(
        service,
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
        config = SimpleNamespace(yolo=False, max_concurrent_tasks=1)
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
        config = SimpleNamespace(yolo=False, max_concurrent_tasks=1)
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


def test_interrupted_readonly_resume_continues_from_session_checkpoint(tmp_path: Path) -> None:
    (tmp_path / "evidence.txt").write_text("stable\n", encoding="utf-8")
    observed_payloads: list[dict[str, object]] = []

    class FakeService:
        config = SimpleNamespace(yolo=False, max_concurrent_tasks=1)
        workspace = tmp_path

        @staticmethod
        def _run_chat(payload, *, on_event=None, on_stream=None, cancel_event=None):
            observed_payloads.append(payload)
            return {"answer": "从会话检查点继续完成", "cancelled": False, "events": []}

    session = SessionStore(tmp_path, "interrupted-session")
    session.save([
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "原始检查请求"},
        {"role": "assistant", "content": "已读取 evidence.txt"},
    ])
    manager = TaskManager(FakeService(), max_workers=1)
    source = TaskRecord(
        task_id="task-interrupted",
        session_id="interrupted-session",
        message="原始检查请求",
        allow_changes=False,
        workspace_path=str(tmp_path),
        status="interrupted",
        phase="interrupted",
        checkpoint={
            "paths": ["evidence.txt"],
            "workspace_digest": TaskManager._workspace_checkpoint_digest(tmp_path, ["evidence.txt"]),
            "safe_readonly": True,
        },
    )
    manager.tasks[source.task_id] = source
    try:
        resumed = manager.resume(source.task_id)
        assert resumed["context"]["recovery"]["mode"] == "session_checkpoint"
        assert resumed["context"]["recovery"]["resume_session"] is True
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and not observed_payloads:
            time.sleep(0.01)
        assert observed_payloads
        assert observed_payloads[0]["resume_from_checkpoint"] is True
        assert str(observed_payloads[0]["message"]).startswith("[任务恢复]")
        assert "原始检查请求" not in str(observed_payloads[0]["message"])
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
        config = SimpleNamespace(yolo=False)

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
        config = SimpleNamespace(yolo=False)

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
        config = SimpleNamespace(yolo=False)

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


def test_task_manager_runs_different_sessions_without_blocking() -> None:
    entered = {"one": threading.Event(), "two": threading.Event()}
    release = threading.Event()

    class FakeService:
        config = SimpleNamespace(yolo=False, max_concurrent_tasks=2)
        workspace = Path.cwd()

        @staticmethod
        def _run_chat(payload, *, on_event=None, on_stream=None, cancel_event=None):
            session = payload["session_id"]
            entered[session].set()
            release.wait(2)
            return {"answer": session, "cancelled": False, "events": []}

    manager = TaskManager(FakeService(), max_workers=2)
    try:
        first = manager.submit({"message": "one", "session_id": "one"})
        second = manager.submit({"message": "two", "session_id": "two"})
        assert entered["one"].wait(1)
        assert entered["two"].wait(1)
        release.set()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if all(manager.get(item["task_id"])["status"] == "completed" for item in (first, second)):
                break
            time.sleep(0.01)
        assert manager.get(first["task_id"])["status"] == "completed"
        assert manager.get(second["task_id"])["status"] == "completed"
    finally:
        release.set()
        manager.shutdown()


def test_task_manager_queues_same_session_but_runs_other_sessions_in_parallel() -> None:
    entered: list[str] = []
    first_started = threading.Event()
    release = threading.Event()

    class FakeService:
        config = SimpleNamespace(yolo=False, max_concurrent_tasks=2)
        workspace = Path.cwd()

        @staticmethod
        def _run_chat(payload, *, on_event=None, on_stream=None, cancel_event=None):
            session = str(payload["session_id"])
            entered.append(str(payload["message"]))
            if payload["message"] == "same-1":
                first_started.set()
                release.wait(2)
            return {"answer": session, "cancelled": False, "events": []}

    manager = TaskManager(FakeService(), max_workers=2)
    try:
        first = manager.submit({"message": "same-1", "session_id": "same"})
        assert first_started.wait(1)
        second = manager.submit({"message": "same-2", "session_id": "same"})
        other = manager.submit({"message": "other", "session_id": "other"})
        assert manager.get(second["task_id"])["status"] == "queued"
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline and "other" not in entered:
            time.sleep(0.01)
        assert "other" in entered
        assert "same-2" not in entered
        release.set()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if all(manager.get(item["task_id"])["status"] == "completed" for item in (first, second, other)):
                break
            time.sleep(0.01)
        assert [manager.get(item["task_id"])["status"] for item in (first, second, other)] == ["completed"] * 3
        assert entered.index("same-1") < entered.index("same-2")
    finally:
        release.set()
        manager.shutdown()


def test_task_manager_binds_workspace_from_submission(tmp_path: Path) -> None:
    workspace = tmp_path / "submitted"
    workspace.mkdir()

    class FakeService:
        config = SimpleNamespace(yolo=False, max_concurrent_tasks=1)
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
        config = SimpleNamespace(yolo=False, max_concurrent_tasks=1)
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


def test_stream_transport_error_is_retryable() -> None:
  assert _is_stream_retryable(RuntimeError("peer closed connection without sending complete message body (incomplete chunked read)"))
  assert _is_stream_retryable(RuntimeError("kernel event source lost: cause=kernel_source_unavailable replay_gap_source=reconnect_floor"))
  assert _is_stream_retryable(RuntimeError("stream disconnected before completion: error sending request for url (https://example.test/v1/responses)"))


def test_stream_transport_error_checks_wrapped_causes_and_truncated_json() -> None:
    wrapped = RuntimeError("provider request failed")
    wrapped.__cause__ = ConnectionResetError("connection reset by peer")
    assert _is_stream_retryable(wrapped)
    assert _is_stream_retryable(json.JSONDecodeError("Expecting value", "{", 1))
    assert OpenAICompatibleProvider.is_transient_failure("LLM 调用失败: Connection error.")


def test_auto_provider_falls_back_after_responses_transport_disconnect() -> None:
    seen: list[str] = []

    class FailingResponses:
        async def create(self, **kwargs):
            seen.append("responses")
            raise RuntimeError("stream disconnected before completion")

    class WorkingCompletions:
        async def create(self, **kwargs):
            seen.append("chat_completions")
            return SimpleNamespace(
                model="test-model",
                usage=SimpleNamespace(prompt_tokens=2, completion_tokens=1, total_tokens=3),
                choices=[SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(content="recovered", reasoning_content=None, tool_calls=[]),
                )],
            )

    provider = OpenAICompatibleProvider(
        "https://example.com/v1",
        "test-key",
        "test-model",
        protocol="auto",
        max_retries=0,
        sdk_client=SimpleNamespace(
            responses=FailingResponses(),
            chat=SimpleNamespace(completions=WorkingCompletions()),
        ),
    )
    response = asyncio.run(provider.chat([{"role": "user", "content": "recover"}]))
    assert response.content == "recovered"
    assert seen == ["responses", "chat_completions"]
    assert provider.protocol() == "chat_completions"


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
                return LLMResponse(content='{"status":"complete","confidence":0.99,"rationale":"已有充分证据。"}')
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


def test_provider_adapts_responses_api_tool_calls() -> None:
    seen: dict[str, object] = {}

    class FakeResponses:
        async def create(self, **kwargs):
            seen.update(kwargs)
            return SimpleNamespace(
                model="test-model",
                status="completed",
                usage=SimpleNamespace(input_tokens=12, output_tokens=4, total_tokens=16),
                output=[
                    SimpleNamespace(
                        type="message",
                        content=[SimpleNamespace(type="output_text", text="I will inspect the file.")],
                    ),
                    SimpleNamespace(type="function_call", call_id="call-read", name="read_file", arguments='{"path":"README.md"}'),
                ],
            )

    provider = OpenAICompatibleProvider(
        "https://example.com/v1", "test-key", "test-model", protocol="responses", sdk_client=SimpleNamespace(responses=FakeResponses())
    )
    tools = [{"type": "function", "function": {"name": "read_file", "description": "Read a file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}}]
    response = asyncio.run(provider.chat([{"role": "user", "content": "Read README.md"}], tools=tools))
    assert seen["reasoning"] == {"effort": "high"}
    assert seen["tools"][0]["type"] == "function"
    assert response.content == "I will inspect the file."
    assert response.tool_calls[0]["function"]["name"] == "read_file"
    assert response.usage["total_tokens"] == 16


def test_change_inspector_shows_uncommitted_file_diff(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    target = tmp_path / "demo.txt"
    target.write_text("line one\nline two\n", encoding="utf-8")
    inspector = ChangeInspector(tmp_path)
    summary = inspector.summary()
    assert summary["files"][0]["path"] == "demo.txt"
    diff = inspector.diff("demo.txt")
    assert diff["status"] == "added"
    assert diff["additions"] == 2
    assert "+line one" in diff["patch"]
