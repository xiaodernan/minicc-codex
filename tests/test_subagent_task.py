"""Task subagent tool tests: restriction, bounded execution, propagation."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from minicc.agent.subagent import (
    DEFAULT_MAX_TURNS,
    SUBAGENT_TOOLS,
    build_task_tool_spec,
)
from minicc.llm.base import LLMResponse
from minicc.tools import build_registry
from minicc.tools.editor import Editor
from minicc.tools.registry import ToolError


class FakeProvider:
    """Minimal provider: one tool-use turn (read_file) then a final answer."""

    def __init__(self, *args, **kwargs) -> None:
        self.requests: list = []
        self.calls = calls if (calls := kwargs.pop("calls", None)) is not None else []
        self.closed = False

    async def chat(self, messages, tools, on_delta=None):
        self.requests.append(list(messages))
        self.calls.append(dict(tools=tools))
        if len(self.calls) == 1:
            return LLMResponse(tool_calls=[{
                "id": "call-1",
                "type": "function",
                "function": {"name": "read_file", "arguments": '{"path": "README.md"}'},
            }])
        return LLMResponse(content="子代理结论：项目是一个本地 coding agent。")

    async def close(self):
        self.closed = True


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "README.md").write_text("# demo project\n", encoding="utf-8")
    return tmp_path


def _spec(workspace: Path, provider: FakeProvider, **overrides):
    registry = build_registry(Editor(workspace))
    return build_task_tool_spec(
        provider_factory=lambda: provider,
        workspace=workspace,
        system_prompt="你是 minicc 测试系统提示。",
        base_registry=registry,
        **overrides,
    )


def test_subagent_runs_readonly_loop_and_returns_answer(workspace: Path) -> None:
    provider = FakeProvider()
    spec = _spec(workspace, provider)
    result = spec.handler({"description": "调研项目结构", "prompt": "读取 README.md 并总结项目用途。"})
    assert result.status == "ok"
    assert "子代理结论" in result.output
    assert result.data["turns"] == 2
    assert any(entry["tool"] == "read_file" for entry in result.data["tool_log"])
    assert "untrusted" in result.security_tags
    assert "subagent" in result.security_tags
    # Worker thread closes its own provider instance.
    assert provider.closed is True


def test_subagent_registry_excludes_write_exec_and_self(workspace: Path) -> None:
    provider = FakeProvider()
    _spec(workspace, provider)
    restricted = build_registry(Editor(workspace)).restrict(SUBAGENT_TOOLS)
    names = set(restricted.names())
    assert "task" not in names, "subagents must not be able to spawn subagents"
    assert not names & {"bash", "write_file", "edit_file", "web_search", "webfetch", "todo_write"}
    assert {"read_file", "grep", "git_status"} <= names


def test_subagent_param_validation(workspace: Path) -> None:
    provider = FakeProvider()
    spec = _spec(workspace, provider)
    with pytest.raises(ToolError, match="description"):
        spec.handler({"description": "ab", "prompt": "足够长的任务说明文本"})
    with pytest.raises(ToolError, match="prompt"):
        spec.handler({"description": "有效描述文本", "prompt": "短"})


def test_subagent_budget_bounds_turns(workspace: Path) -> None:
    class EndlessProvider:
        def __init__(self) -> None:
            self.rounds = 0

        async def chat(self, messages, tools, on_delta=None):
            self.rounds += 1
            return LLMResponse(tool_calls=[{
                "id": f"call-{self.rounds}",
                "type": "function",
                "function": {"name": "read_file", "arguments": '{"path": "README.md"}'},
            }])

        async def close(self):
            return None

    provider = EndlessProvider()
    spec = _spec(workspace, provider, max_turns=3)
    result = spec.handler({"description": "永不停止的调研", "prompt": "反复读取 README.md。"})
    # The sub-loop must terminate near the turn budget instead of running
    # forever; exact accounting may include the final summary turn.
    assert provider.rounds <= 4
    assert result.status in {"ok", "error", "timed_out"}


def test_spec_shape_and_schema(workspace: Path) -> None:
    provider = FakeProvider()
    spec = _spec(workspace, provider)
    assert spec.risk == "readonly"
    schema = spec.input_schema
    assert schema["required"] == ["description", "prompt"]
    assert schema["properties"]["prompt"]["maxLength"] == 8000


def test_web_service_registers_task_tool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The web chat path registers the task tool into the per-task registry."""
    from minicc.web import AgentService

    registered: dict[str, object] = {}

    class RecordingRegistry:
        def __init__(self, inner) -> None:
            self._inner = inner

        def register(self, spec) -> None:
            registered[spec.name] = spec
            self._inner.register(spec)

        def __getattr__(self, item):
            return getattr(self._inner, item)

    real_build_registry = build_registry

    def spy_build_registry(*args, **kwargs):
        return RecordingRegistry(real_build_registry(*args, **kwargs))

    monkeypatch.setattr("minicc.web.build_registry", spy_build_registry)

    class FakeProvider:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def chat(self, messages, tools, on_delta=None):
            registered_names = sorted(registered)
            return LLMResponse(content=f"tools可见: {registered_names}")

        async def close(self):
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
        service._chat_locked(
            {"message": "检查当前可用的工具并直接回答", "allow_changes": False, "workspace_path": str(tmp_path)},
            workspace=tmp_path,
        )
        # The contract under test: the per-task registry received the bounded
        # task tool before the agent loop started. (The fake provider's plain
        # text fails the completion judge, so the final answer is irrelevant.)
        assert "task" in registered
    finally:
        service.shutdown()
