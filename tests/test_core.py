from __future__ import annotations

import json
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
import asyncio

import pytest

import minicc.tools.web as web_tool
from minicc.agent.context import COMPACTION_MARKER, compact
from minicc.config import load_config, normalize_reasoning_effort
from minicc.agent.loop import run_agent
from minicc.llm.base import LLMResponse
from minicc.llm.envelope import extract_json_object, parse_envelope
from minicc.llm.openai_provider import OpenAICompatibleProvider, _is_stream_retryable
from minicc.session import SessionStore
from minicc.sandbox import SandboxRunner
from minicc.mcp import load_mcp_config
from minicc.tools.bash import decode_process_output, is_readonly_command
from minicc.tools.editor import EditError, Editor, StaleContextError
from minicc.tools.schemas import ToolCall
from minicc.tools.web import parse_search_html
from minicc.tools import build_registry
from minicc.changes import ChangeInspector
from minicc.task_store import TaskStore
from minicc.web import AgentService, TaskManager, TaskRecord, _completion_guard_message, _multimodal_content
from minicc.worktree import WorktreeError, WorktreeManager
from minicc.prompt import build_system_prompt


def test_compact_builds_valid_summary() -> None:
    messages = [{"role": "system", "content": "rules"}]
    messages.extend({"role": "user", "content": "x" * 50} for _ in range(8))
    compacted = compact(messages, threshold=100, keep_recent=2)
    assert COMPACTION_MARKER in compacted[1]["content"]
    assert len(compacted) == 4


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


def test_registry_contains_readonly_git_tools(tmp_path: Path) -> None:
    registry = build_registry(Editor(tmp_path))
    assert registry.risk_of("git_status") == "readonly"
    assert registry.risk_of("git_diff") == "readonly"
    assert registry.risk_of("web_search") == "readonly"


def test_bash_output_decodes_windows_code_pages_without_crashing() -> None:
    encoded = "中文输出".encode("gb18030")
    assert decode_process_output(encoded) == "中文输出"


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
    assert normalize_reasoning_effort("standard") == "standard"
    assert normalize_reasoning_effort("high") == "high"
    assert normalize_reasoning_effort("very-high") == "max"


def test_provider_sends_reasoning_budget() -> None:
    seen: dict[str, object] = {}
    provider = OpenAICompatibleProvider(
        "https://example.com/v1",
        "test-key",
        "test-model",
        reasoning_effort="max",
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
    assert seen["reasoning_effort"] == "xhigh"


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
    monkeypatch.delenv("MINICC_API_KEY", raising=False)
    monkeypatch.delenv("MINICC_BASE_URL", raising=False)
    monkeypatch.delenv("MINICC_MODEL", raising=False)
    monkeypatch.delenv("MINICC_YOLO", raising=False)
    config = load_config()
    assert config.api_key == "sk-test-config"
    assert config.base_url == "https://example.test/v1"
    assert config.model == "test-model"
    assert config.yolo is True


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
    result = asyncio.run(
        run_agent(
            FakeProvider(),
            registry,
            messages,
            should_allow=lambda _name, _call: True,
        )
    )
    assert result.answer == "已读取 hello.txt"
    assert result.tool_calls_total == 1
    assert any(message.get("role") == "tool" for message in messages)


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
