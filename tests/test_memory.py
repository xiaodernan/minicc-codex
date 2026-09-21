"""M8-T1 long-term memory: MEMORY.md tools, prompt index injection, recall.

Acceptance (docs/ROADMAP_TO_PRODUCT.md M8-T1):
- 任务 A 写一条记忆，任务 B 的系统提示里出现该条目的索引行；
- memory_write 拒绝写 .minicc/ 下的敏感路径与绝对路径外路径；
- 索引注入有上限；无记忆时行为不变。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from minicc.llm.base import LLMResponse
from minicc.prompt import build_system_prompt
from minicc.tools import build_registry
from minicc.tools.editor import Editor
from minicc.tools.memory import (
    INDEX_EXCERPT_CHARS,
    MEMORY_FILE_NAME,
    parse_entries,
    render_memory_index,
)
from minicc.tools.registry import ToolCall


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch) -> Path:
    """Redirect ~/.minicc (user-scope MEMORY.md AND the task store) to a tmp."""
    home = tmp_path / "minicc-home"
    home.mkdir()
    monkeypatch.setenv("MINICC_HOME", str(home))
    return home


@pytest.fixture
def ws(tmp_path: Path) -> Path:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    return workspace


def _call(registry, tool: str, **arguments):
    return registry.execute(ToolCall(tool=tool, arguments=dict(arguments)))


def _project_file(ws: Path) -> Path:
    return ws / ".minicc" / MEMORY_FILE_NAME


def _write(registry, content: str, **kwargs) -> dict:
    result = _call(registry, "memory_write", content=content, **kwargs)
    assert result.status == "ok", result.summary
    return result.data["entry"]


# --- registry wiring ---------------------------------------------------------


def test_memory_tools_registered_as_readonly(ws: Path) -> None:
    registry = build_registry(Editor(ws))
    for name in ("memory_write", "memory_read", "memory_list"):
        assert name in registry.names()
        assert registry.risk_of(name) == "readonly"
    schema_names = {item["function"]["name"] for item in registry.openai_schemas()}
    assert {"memory_write", "memory_read", "memory_list"} <= schema_names


# --- write / read roundtrip ----------------------------------------------------


def test_memory_write_creates_parseable_entry(ws: Path) -> None:
    registry = build_registry(Editor(ws))
    entry = _write(registry, "project uses pnpm, not npm", scope="project")
    assert entry["id"].startswith("mem-")
    assert entry["scope"] == "project"
    text = _project_file(ws).read_text(encoding="utf-8")
    assert entry["id"] in text
    parsed = parse_entries(text, "project")
    assert [item.id for item in parsed] == [entry["id"]]
    assert parsed[0].content == "project uses pnpm, not npm"


def test_memory_write_defaults_to_project_scope(ws: Path, isolated_home: Path) -> None:
    registry = build_registry(Editor(ws))
    _write(registry, "default scope marker")
    assert _project_file(ws).is_file()
    assert not (isolated_home / MEMORY_FILE_NAME).exists()


def test_memory_write_user_scope_goes_to_home(ws: Path, isolated_home: Path) -> None:
    registry = build_registry(Editor(ws))
    _write(registry, "user prefers terse answers", scope="user")
    assert (isolated_home / MEMORY_FILE_NAME).is_file()
    assert not _project_file(ws).exists()


def test_memory_redacts_secrets_before_persisting(ws: Path) -> None:
    registry = build_registry(Editor(ws))
    result = _call(
        registry,
        "memory_write",
        content="deploy key sk-abcdefgh12345678 rotates monthly",
    )
    assert result.status == "ok"
    assert "redacted" in result.security_tags
    stored = _project_file(ws).read_text(encoding="utf-8")
    assert "sk-abcdefgh12345678" not in stored
    assert "[REDACTED:llm_api_key]" in stored
    # The tool result handed back to the model is scrubbed too.
    assert "sk-abcdefgh12345678" not in json.dumps(result.data, ensure_ascii=False)


def test_memory_write_rejects_path_like_scopes(ws: Path, isolated_home: Path) -> None:
    registry = build_registry(Editor(ws))
    hostile = [
        ".minicc/web_token.json",
        ".minicc/allowlist.json",
        ".minicc/hooks.json",
        "C:/Windows/minicc",
        "/etc/cron.d/minicc",
        "../../outside-workspace",
        str(isolated_home / "MEMORY.md"),
    ]
    for scope in hostile:
        result = _call(registry, "memory_write", content="escape attempt", scope=scope)
        assert result.status == "error", scope
        assert result.summary.startswith("[INVALID_ARGUMENTS]"), scope
        assert "scope" in result.summary
    assert not list(ws.rglob("web_token.json"))
    assert not list(ws.rglob("allowlist.json"))
    assert not list(ws.rglob("hooks.json"))
    assert not _project_file(ws).exists()


def test_memory_write_rejects_path_argument(ws: Path) -> None:
    registry = build_registry(Editor(ws))
    result = _call(
        registry,
        "memory_write",
        content="with a path",
        path=str(ws / ".minicc" / "web_token.json"),
    )
    assert result.status == "error"
    assert result.summary.startswith("[INVALID_ARGUMENTS]")
    assert "path" in result.summary


def test_memory_write_validates_content(ws: Path) -> None:
    registry = build_registry(Editor(ws))
    empty = _call(registry, "memory_write", content="   \n  ")
    assert empty.summary.startswith("[INVALID_ARGUMENTS]")
    too_long = _call(registry, "memory_write", content="x" * 600)
    assert too_long.summary.startswith("[INVALID_ARGUMENTS]")
    assert "超过最大长度" in too_long.summary


# --- human editing (exit criterion: 记忆文件可被用户手工编辑与删除) ----------


def test_memory_files_are_human_editable_and_deletable(ws: Path) -> None:
    registry = build_registry(Editor(ws))
    first = _write(registry, "MARKER-ONE keep? no")
    second = _write(registry, "MARKER-TWO hand-edit me")
    path = _project_file(ws)
    lines = path.read_text(encoding="utf-8").splitlines()
    kept = [line for line in lines if first["id"] not in line]
    kept = [line.replace(second["content"], "manually edited memory") for line in kept]
    kept.append("# a free-form user note that must simply be ignored")
    kept.append("- [mem-deadbeef] (created=2026-01-01T00:00:00Z, source=user) hand added")
    path.write_text("\n".join(kept) + "\n", encoding="utf-8")

    listing = _call(registry, "memory_list")
    ids = {item["id"] for item in listing.data["entries"]}
    assert first["id"] not in ids
    assert {second["id"], "mem-deadbeef"} <= ids
    edited = _call(registry, "memory_read", id=second["id"])
    assert "manually edited memory" in edited.output
    gone = _call(registry, "memory_read", id=first["id"])
    assert gone.status == "error"
    assert gone.summary.startswith("[TOOL_ERROR]")


def test_memory_read_and_list_scoping_and_limit(ws: Path, isolated_home: Path) -> None:
    registry = build_registry(Editor(ws))
    project = _write(registry, "kubernetes upgrade notes", scope="project")
    user = _write(registry, "user prefers terse answers", scope="user")

    both = _call(registry, "memory_list")
    assert {item["id"] for item in both.data["entries"]} == {project["id"], user["id"]}

    only_project = _call(registry, "memory_list", scope="project")
    assert [item["id"] for item in only_project.data["entries"]] == [project["id"]]

    only_user = _call(registry, "memory_list", scope="user")
    assert [item["id"] for item in only_user.data["entries"]] == [user["id"]]

    bad_scope = _call(registry, "memory_list", scope=".minicc/web_token.json")
    assert bad_scope.summary.startswith("[INVALID_ARGUMENTS]")

    full = _call(registry, "memory_read", id=project["id"])
    assert full.status == "ok"
    assert "kubernetes upgrade notes" in full.output
    assert full.data["entries"][0]["scope"] == "project"


def test_memory_list_query_uses_deterministic_scoring(ws: Path) -> None:
    registry = build_registry(Editor(ws))
    _write(registry, "waffle iron recipe needs batter rest")
    _write(registry, "kubernetes upgrade drained nodes")
    _write(registry, "kubernetes notes on cert rotation")

    scored = _call(registry, "memory_list", query="kubernetes")
    assert scored.status == "ok", scored.summary
    assert scored.data["sort"] == "query-score"
    hits = [item["content"] for item in scored.data["entries"]]
    assert all("kubernetes" in text for text in hits)
    assert len(hits) == 2
    # Newest of the two hits first (same-second writes keep reverse file order).
    assert "cert rotation" in hits[0]

    cjk = _call(registry, "memory_list", query="waffle")
    assert [item["content"] for item in cjk.data["entries"]][0].startswith("waffle")

    miss = _call(registry, "memory_list", query="zzzqqq")
    assert miss.data["entries"] == []
    limited = _call(registry, "memory_list", query="kubernetes", limit=1)
    assert len(limited.data["entries"]) == 1


# --- prompt index injection ----------------------------------------------------


def _many_entries(count: int) -> str:
    lines = ["# hand-generated"]
    for index in range(count):
        created = f"2026-01-01T{index // 60:02d}:{index % 60:02d}:00Z"
        lines.append(
            f"- [mem-{index:08x}] (created={created}, source=test) entry number {index}"
        )
    return "\n".join(lines) + "\n"


def test_prompt_unchanged_without_memories(ws: Path) -> None:
    prompt = build_system_prompt(ws)
    assert "长期记忆索引" not in prompt
    assert not _project_file(ws).exists()
    assert not (ws / ".minicc").exists()


def test_prompt_injects_index_line_with_excerpt(ws: Path) -> None:
    registry = build_registry(Editor(ws))
    long_marker = "LONGMARKER-" + "a" * 140
    entry = _write(registry, long_marker, source="web-test")
    prompt = build_system_prompt(ws)
    assert "长期记忆索引" in prompt
    index_line = next(line for line in prompt.splitlines() if entry["id"] in line)
    assert index_line.startswith(f"- [project] {entry['id']} (")
    assert "来源=web-test" in index_line
    assert long_marker[:INDEX_EXCERPT_CHARS] in index_line
    assert long_marker not in index_line
    assert index_line.rstrip().endswith("…")
    assert "memory_read" in prompt and "memory_write" in prompt


def test_prompt_index_shows_all_below_threshold(ws: Path) -> None:
    _project_file(ws).parent.mkdir(parents=True)
    _project_file(ws).write_text(_many_entries(199), encoding="utf-8")
    prompt = build_system_prompt(ws)
    assert "mem-00000000" in prompt
    assert "mem-000000c6" in prompt  # 198
    assert "仅展示最近" not in prompt


def test_prompt_index_caps_at_200_entries(ws: Path) -> None:
    _project_file(ws).parent.mkdir(parents=True)
    _project_file(ws).write_text(_many_entries(201), encoding="utf-8")
    prompt = build_system_prompt(ws)
    assert "mem-000000c8" in prompt  # 200, most recent
    assert "mem-00000097" in prompt  # 151, oldest of the last 50
    assert "mem-00000096" not in prompt  # 150, omitted
    assert "mem-00000000" not in prompt
    assert "仅展示最近 50 条" in prompt
    assert "151" in prompt


def test_prompt_index_merges_user_and_project(ws: Path, isolated_home: Path) -> None:
    registry = build_registry(Editor(ws))
    _write(registry, "user level note", scope="user")
    _write(registry, "project level note", scope="project")
    block = render_memory_index(ws)
    assert "- [user]" in block
    assert "- [project]" in block


# --- acceptance: task A writes, task B's system prompt carries the index line --


class _MemoryWritingFake:
    """Task A: first model turn calls memory_write, then delegates to the fake."""

    scripted: list[dict] = []

    def __init__(self, *args, **kwargs) -> None:
        from minicc.llm.fake import FakeProvider

        self._inner = FakeProvider()
        self._wrote = False

    async def chat(self, messages, tools, on_delta=None):
        if tools is not None and not self._wrote:
            self._wrote = True
            return LLMResponse(
                content="",
                tool_calls=[
                    {
                        "id": "mem-write-1",
                        "type": "function",
                        "function": {
                            "name": "memory_write",
                            "arguments": json.dumps(
                                {
                                    "content": "MEMORY-ACC-MARKER 部署目标是 k3s 集群",
                                    "scope": "project",
                                    "source": "task-A",
                                }
                            ),
                        },
                    }
                ],
                finish_reason="tool_calls",
                usage={"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
            )
        return await self._inner.chat(messages, tools, on_delta=on_delta)

    async def close(self) -> None:
        await self._inner.close()

    def protocol(self) -> str:
        return "fake"

    def protocol_status(self) -> dict:
        return {"requested": "auto", "active": "fake"}

    @staticmethod
    def is_transient_failure(value) -> bool:
        return False


class _CapturingFake(_MemoryWritingFake):
    """Task B: plain fake provider that records the message lists it sees."""

    instances: list["_CapturingFake"] = []

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._wrote = True  # never emit the scripted memory_write
        self.seen_messages: list[list] = []
        _CapturingFake.instances.append(self)

    async def chat(self, messages, tools, on_delta=None):
        self.seen_messages.append([dict(item) for item in messages])
        return await self._inner.chat(messages, tools, on_delta=on_delta)


def _service_config() -> SimpleNamespace:
    return SimpleNamespace(
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
        fallback_models=(),
    )


def test_task_a_memory_visible_in_task_b_system_prompt(ws: Path, monkeypatch) -> None:
    from minicc import web as web_module

    monkeypatch.setattr(web_module, "OpenAICompatibleProvider", _MemoryWritingFake)
    service_a = web_module.AgentService(ws, _service_config())
    try:
        result_a = service_a._chat_locked(
            {
                "message": "请记住：本项目部署目标是 k3s 集群",
                "session_id": "memory-task-a",
                "allow_changes": False,
                "workspace_path": str(ws),
            },
            workspace=ws,
        )
    finally:
        service_a.shutdown()
    assert result_a["error"] is None, result_a
    stored = _project_file(ws).read_text(encoding="utf-8")
    assert "MEMORY-ACC-MARKER" in stored
    entry_id = parse_entries(stored, "project")[0].id

    _CapturingFake.instances = []
    monkeypatch.setattr(web_module, "OpenAICompatibleProvider", _CapturingFake)
    service_b = web_module.AgentService(ws, _service_config())
    try:
        result_b = service_b._chat_locked(
            {
                "message": "这个项目部署到哪里？",
                "session_id": "memory-task-b",
                "allow_changes": False,
                "workspace_path": str(ws),
            },
            workspace=ws,
        )
    finally:
        service_b.shutdown()
    assert result_b["error"] is None, result_b
    system_prompts = [
        item
        for provider in _CapturingFake.instances
        for messages in provider.seen_messages
        for item in messages
        if item.get("role") == "system"
    ]
    assert system_prompts
    assert any(
        "长期记忆索引" in str(item.get("content"))
        and entry_id in str(item.get("content"))
        and "MEMORY-ACC-MARKER" in str(item.get("content"))
        for item in system_prompts
    )
