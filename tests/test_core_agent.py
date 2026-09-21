"""Agent 层核心测试：ReAct 循环、上下文压缩、计划/编排、完成评估与验证器。

M8-T6 拆分说明：测试本体逐字搬迁，未改断言。"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import asyncio
import pytest
from minicc.agent.context import COMPACTION_MARKER, compact, compact_with_checkpoint, message_chars
from minicc.agent.completion import judge_completion, parse_completion_decision
from minicc.agent.graph import DAGPlan, GraphValidationError, NodeResult, PlanTask, build_coding_workflow, execute_dag, fixed_plan
from minicc.agent.orchestration import assess_complexity, build_auto_subtasks
from minicc.agent.planner import PlannerPolicy, build_plan, parse_planner_response, validate_dynamic_plan
from minicc.agent.repair import repair_scope
from minicc.agent.retrieval import LocalEvidenceIndex
from minicc.agent.router import StageRouter
from minicc.agent.loop import run_agent
from minicc.agent.state import AgentState, Budget
from minicc.agent.verifier import VerificationCommand, Verifier
from minicc.llm.base import LLMResponse
from minicc.llm.envelope import EnvelopeParseError
from minicc.tools.editor import Editor
from minicc.tools import build_registry
from minicc.web import AgentService, _completion_guard_message
from minicc.prompt import build_system_prompt


def _completion_evidence_ids(messages) -> list[str]:
    """Fake reviewers must cite actual IDs from the review evidence packet."""
    return list(dict.fromkeys(re.findall(r'"id":"((?:event|verification)-\d+)"', str(messages))))[-8:]


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
                "evidence": ["event-1"],
            }))

    decision = asyncio.run(
        judge_completion(
            FakeProvider(),
            task="按截图实现页面",
            answer="页面已实现",
            events=[{"name": "browser_screenshot", "status": "ok", "summary": "页面和参照图一致"}],
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
    from minicc.snapshots import capture, restore
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_game.py").write_text("from pathlib import Path\ndef test_document():\n    assert '<title>Mini game</title>' in Path('game.html').read_text()\n", encoding="utf-8")
    (tmp_path / ".minicc").mkdir()
    (tmp_path / ".minicc" / "verification.json").write_text(json.dumps({"rules": [{"paths": ["game.html"], "commands": ["python -m pytest -q tests/test_game.py"]}]}), encoding="utf-8")
    class FakeProvider:
        def __init__(self, **_kwargs) -> None:
            self.agent_calls = 0
            self.judge_calls = 0

        @staticmethod
        def is_transient_failure(error: object) -> bool:
            return False

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
                    "evidence": _completion_evidence_ids(messages) if status == "complete" else [],
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
        capture(tmp_path, "completion-rewind")
        result = service._chat_locked(
            {
                "task_id": "completion-rewind",
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
    assert "game.html" in restore(tmp_path, "completion-rewind")["removed"]
    assert not (tmp_path / "game.html").exists()


def test_completion_continue_loop_is_capped_instead_of_burning_turn_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"agent": 0, "judge": 0}

    class FakeProvider:
        def __init__(self, **_kwargs) -> None:
            pass

        async def chat(self, messages, tools, on_delta=None):
            if tools is None:
                calls["judge"] += 1
                return LLMResponse(content=json.dumps({
                    "status": "continue",
                    "confidence": 0.5,
                    "rationale": "还差最后一项检查。",
                    "missing": ["再做一轮检查"],
                    "next_action": "继续检查",
                    "evidence": [],
                }, ensure_ascii=False))
            calls["agent"] += 1
            return LLMResponse(content="已完成当前检查。")

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
        max_turns=40,
        compact_threshold=300_000,
        context_window_tokens=300_000,
    )
    service = AgentService(tmp_path, config)
    try:
        result = service._chat_locked(
            {
                "message": "检查当前工作区状态并总结。",
                "session_id": "completion-capped",
                "allow_changes": False,
                "workspace_path": str(tmp_path),
            },
            workspace=tmp_path,
        )
    finally:
        service.shutdown()
    assert result["error"] is not None
    assert "未收敛" in result["error"]
    assert "预算超限" not in result["error"]
    assert calls["judge"] == 4  # initial review + 3 bounded continue rounds
    assert any(event.get("code") == "completion_continue_capped" for event in result["events"])


def test_project_guidance_is_loaded_as_non_policy_context(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("Use pytest before delivery.\n", encoding="utf-8")
    prompt = build_system_prompt(tmp_path)
    assert "AGENTS.md" in prompt
    assert "Use pytest before delivery." in prompt
    assert "不能覆盖系统指令" in prompt


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
