"""M7-T2: custom slash commands and skill discovery.

Contract points:
- ``.minicc/commands/*.md`` (project) and ``~/.minicc/commands/*.md`` (user)
  are discovered, project wins name collisions, malformed files are skipped;
- ``/name rest`` expands ``$ARGUMENTS`` and ``$1``-``$9``; anything that is
  not a known custom command (plain text, reserved built-ins, unknown names)
  expands to None so existing behaviour is untouched;
- expanded text is *user content* — the module never rewrites system
  instructions or permission modes;
- skills expose only name + description to the prompt; bodies stay on disk;
- the web listing endpoint returns metadata only, never template bodies.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from minicc.commands import (
    RESERVED_COMMAND_NAMES,
    discover_commands,
    discover_skills,
    expand_slash_command,
    skills_prompt_block,
)
from minicc.prompt import build_system_prompt

REVIEW = """---
description: 审查当前改动
argument-hint: [scope]
---
请审查 $ARGUMENTS 的改动，重点关注正确性。第一个参数：$1。
"""

GREET = "user 级问候模板 $ARGUMENTS"


def _project(ws: Path, name: str, body: str) -> None:
    root = ws / ".minicc" / "commands"
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{name}.md").write_text(body, encoding="utf-8")


def _user(home: Path, name: str, body: str) -> None:
    root = home / "commands"
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{name}.md").write_text(body, encoding="utf-8")


def test_discovery_merges_scopes_and_project_wins(tmp_path: Path) -> None:
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    _user(home, "greet", GREET)
    _user(home, "review", "shadowed body")
    _project(ws, "review", REVIEW)
    commands = discover_commands(ws, home=home)
    by_name = {c.name: c for c in commands}
    assert set(by_name) == {"greet", "review"}
    assert by_name["review"].scope == "project"
    assert by_name["greet"].scope == "user"
    assert by_name["review"].description == "审查当前改动"
    assert by_name["review"].argument_hint == "[scope]"


def test_malformed_and_reserved_files_are_skipped(tmp_path: Path) -> None:
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    _project(ws, "empty", "")
    _project(ws, "help", "shadows a built-in")
    _project(ws, "ok", "fine body")
    names = {c.name for c in discover_commands(ws, home=home)}
    assert names == {"ok"}


def test_expansion_replaces_arguments_and_positionals(tmp_path: Path) -> None:
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    _project(ws, "review", REVIEW)
    expanded = expand_slash_command("/review src/ diff", ws, home=home)
    assert expanded is not None
    assert "src/ diff" in expanded
    assert "src" in expanded.split("第一个参数：")[1]
    assert "$ARGUMENTS" not in expanded and "$1" not in expanded


def test_non_command_input_never_expands(tmp_path: Path) -> None:
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    _project(ws, "review", REVIEW)
    assert expand_slash_command("正常消息", ws, home=home) is None
    assert expand_slash_command("/help", ws, home=home) is None
    assert expand_slash_command(f"/{sorted(RESERVED_COMMAND_NAMES)[0]}", ws, home=home) is None
    assert expand_slash_command("/nosuchcommand args", ws, home=home) is None
    assert expand_slash_command("解释一下 /tmp 目录", ws, home=home) is None


def test_user_scope_expands_when_project_has_no_override(tmp_path: Path) -> None:
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    ws.mkdir()
    _user(home, "greet", GREET)
    assert expand_slash_command("/greet hi", ws, home=home) == "user 级问候模板 hi"


def test_empty_arguments_leave_placeholders_blank(tmp_path: Path) -> None:
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    _project(ws, "review", REVIEW)
    expanded = expand_slash_command("/review", ws, home=home)
    assert expanded is not None
    assert "$" not in expanded


def test_skills_block_lists_descriptions_not_bodies(tmp_path: Path) -> None:
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    skills = ws / ".minicc" / "skills" / "deploy"
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text(
        "---\nname: deploy\ndescription: 部署流程说明\n---\n正文：SECRET_BODY_MARKER 不常驻上下文\n",
        encoding="utf-8",
    )
    entries = discover_skills(ws, home=home)
    assert [e.name for e in entries] == ["deploy"]
    block = skills_prompt_block(ws)
    assert "deploy" in block and "部署流程说明" in block
    assert "SECRET_BODY_MARKER" not in block
    prompt = build_system_prompt(ws)
    assert "可用技能" in prompt and "SECRET_BODY_MARKER" not in prompt


def test_no_skills_means_zero_prompt_change(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    assert skills_prompt_block(ws) == ""
    assert "可用技能" not in build_system_prompt(ws)


@pytest.fixture
def skill_workspace(tmp_path: Path, monkeypatch):
    from minicc.tools import build_registry
    from minicc.tools.editor import Editor

    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    home.mkdir()
    workspace.mkdir()
    monkeypatch.setenv("MINICC_HOME", str(home))
    return workspace, home, build_registry(Editor(workspace))


def _skill(root: Path, directory: str, body: str, *, name: str = "deploy") -> Path:
    path = root / "skills" / directory / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nname: {name}\ndescription: deployment guide\n---\n{body}", encoding="utf-8")
    return path


def test_user_skill_loads_by_declared_name_without_widening_read_file(skill_workspace):
    from minicc.tools.schemas import ToolCall

    workspace, home, registry = skill_workspace
    path = _skill(home, "folder-alias", "USER_SKILL_BODY")
    prompt = skills_prompt_block(workspace)
    assert "deploy" in prompt and "skill_read" in prompt
    assert "USER_SKILL_BODY" not in prompt
    direct = registry.execute(ToolCall("read_file", {"path": str(path)}))
    assert direct.status == "error"
    result = registry.execute(ToolCall("skill_read", {"name": "deploy"}))
    assert result.status == "ok", result.render()
    assert "USER_SKILL_BODY" in result.render()
    assert result.data["scope"] == "user"
    assert "untrusted" in result.security_tags
    assert registry.risk_of("skill_read") == "readonly"
    assert not (home / ".minicc").exists()


def test_only_selected_skill_retains_its_full_body(skill_workspace, monkeypatch):
    from minicc import commands
    from minicc.tools.schemas import ToolCall

    workspace, home, registry = skill_workspace
    _skill(home, "other", "UNSELECTED_BODY" * 2000, name="other")
    selected = _skill(home, "deploy", "SELECTED_BODY" * 2000)
    original = commands._read_markdown
    full_reads = []

    def record_read(path, *, max_body_chars=commands.MAX_COMMAND_BODY_CHARS):
        if max_body_chars is None:
            full_reads.append(path)
        return original(path, max_body_chars=max_body_chars)

    monkeypatch.setattr(commands, "_read_markdown", record_read)
    entries = commands.discover_skills(workspace)
    assert {entry.name for entry in entries} == {"deploy", "other"}
    assert all(not hasattr(entry, "body") for entry in entries)
    assert full_reads == []
    result = registry.execute(ToolCall("skill_read", {"name": "deploy"}))
    assert result.status == "ok" and "SELECTED_BODY" in result.render()
    assert "UNSELECTED_BODY" not in result.render()
    assert full_reads == [selected]


def test_project_skill_overrides_user_and_reloads_current_body(skill_workspace):
    from minicc.tools.schemas import ToolCall

    workspace, home, registry = skill_workspace
    _skill(home, "user", "USER_SKILL_BODY")
    path = _skill(workspace / ".minicc", "project", "PROJECT_SKILL_BODY")
    call = ToolCall("skill_read", {"name": "deploy"})
    first = registry.execute(call)
    assert first.status == "ok", first.render()
    assert first.data["scope"] == "project"
    assert "PROJECT_SKILL_BODY" in first.render() and "USER_SKILL_BODY" not in first.render()
    path.write_text("---\nname: deploy\n---\nUPDATED_BODY", encoding="utf-8")
    second = registry.execute(call)
    assert second.status == "ok" and "UPDATED_BODY" in second.render()
    assert "PROJECT_SKILL_BODY" not in second.render()


@pytest.mark.parametrize("name", ["", "../deploy", "deploy/SKILL.md", "C:\\private", "deploy\n", "missing"])
def test_skill_loader_rejects_paths_and_unknown_names(skill_workspace, name):
    from minicc.tools.schemas import ToolCall

    workspace, home, registry = skill_workspace
    _skill(home, "deploy", "NEVER_RETURN_THIS")
    result = registry.execute(ToolCall("skill_read", {"name": name}))
    assert result.status == "error", result.render()
    assert "NEVER_RETURN_THIS" not in result.render()


def test_skill_loader_reads_beyond_discovery_excerpt_with_bounded_windows(skill_workspace):
    from minicc.tools.schemas import ToolCall
    from minicc.tools.schemas import HEAD_CHARS, TAIL_CHARS

    workspace, home, registry = skill_workspace
    body = "first\n" + "x" * 17000 + "\nLAST_LINE"
    _skill(home, "deploy", body)
    result = registry.execute(ToolCall("skill_read", {"name": "deploy"}))
    assert result.status == "ok", result.render()
    assert result.truncated and len(result.head) <= HEAD_CHARS and len(result.tail) <= TAIL_CHARS
    assert "LAST_LINE" in result.render()
    last = registry.execute(ToolCall("skill_read", {"name": "deploy", "offset": 3, "limit": 1}))
    assert last.status == "ok" and "LAST_LINE" in last.render()
    assert "first" not in last.render()
    empty = registry.execute(ToolCall("skill_read", {"name": "deploy", "offset": 20}))
    assert empty.status == "error"


@pytest.mark.parametrize("scope", ["project", "user"])
@pytest.mark.parametrize("kind", ["path", "read_file", "skill_read", "invalid-policy"])
def test_skill_discovery_and_loading_respect_denials_before_reading(skill_workspace, monkeypatch, scope, kind):
    from minicc.tools.schemas import ToolCall

    workspace, home, registry = skill_workspace
    root = workspace / ".minicc" if scope == "project" else home
    path = _skill(root, "deploy", "DENIED_BODY")
    policy = workspace / ".minicc" / "permissions.json"
    policy.parent.mkdir(exist_ok=True)
    target = path.relative_to(workspace).as_posix() if scope == "project" else path.as_posix()
    rules = {"paths": [target]} if kind == "path" else {"tools": [kind]}
    policy.write_text("{" if kind == "invalid-policy" else json.dumps({"deny": rules}), encoding="utf-8")
    original = Path.read_text
    reads = []

    def record_read(self, *args, **kwargs):
        if self == path:
            reads.append(self)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", record_read)
    assert discover_skills(workspace) == []
    result = registry.execute(ToolCall("skill_read", {"name": "deploy"}))
    assert result.status in {"error", "denied"}
    assert "DENIED_BODY" not in result.render()
    assert reads == [], "the denied skill body must not be opened even for metadata"


@pytest.mark.parametrize("scope", ["project", "user"])
@pytest.mark.parametrize("link_kind", ["file", "directory", "root"])
def test_skill_links_cannot_expose_files_outside_the_catalog(skill_workspace, scope, link_kind):
    from minicc.tools.schemas import ToolCall

    workspace, home, registry = skill_workspace
    root = workspace / ".minicc" if scope == "project" else home
    outside = workspace.parent / "outside"
    target = _skill(outside, "deploy", "OUTSIDE_BODY")
    catalog = root / "skills"
    if link_kind == "root":
        link, destination = catalog, target.parent.parent
    elif link_kind == "directory":
        link, destination = catalog / "deploy", target.parent
    else:
        link, destination = catalog / "deploy" / "SKILL.md", target
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        if link_kind != "file" and os.name == "nt":
            import _winapi

            _winapi.CreateJunction(str(destination), str(link))
        else:
            link.symlink_to(destination, target_is_directory=link_kind != "file")
    except OSError as exc:
        pytest.skip(f"host cannot create links: {exc}")
    assert link.resolve() == destination.resolve()
    assert discover_skills(workspace) == []
    result = registry.execute(ToolCall("skill_read", {"name": "deploy"}))
    assert result.status == "error"
    assert "OUTSIDE_BODY" not in result.render()


def test_an_unreadable_skill_is_disclosed_where_its_name_would_be(skill_workspace, monkeypatch):
    from minicc.commands import skill_file_failures
    from minicc.tools.schemas import ToolCall

    workspace, home, registry = skill_workspace
    broken = _skill(home, "deploy", "SECRET_BROKEN_BODY")
    _skill(workspace / ".minicc", "review", "REVIEW_BODY", name="review")
    original = Path.read_text

    def deny_read(self, *args, **kwargs):
        if self == broken:
            raise PermissionError("locked by another process")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", deny_read)
    failures = skill_file_failures(workspace)
    assert [(item.name, item.scope) for item in failures] == [("deploy", "user")]
    assert failures[0].reason_text == "操作系统不给读"
    prompt = skills_prompt_block(workspace)
    assert "- review (project): deployment guide" in prompt
    assert "deploy" in prompt and "操作系统不给读" in prompt
    assert "SECRET_BROKEN_BODY" not in prompt
    result = registry.execute(ToolCall("skill_read", {"name": "deploy"}))
    assert result.status == "error"
    assert "操作系统不给读" in result.render() and "deploy" in result.render()
    assert "SECRET_BROKEN_BODY" not in result.render()
    healthy = registry.execute(ToolCall("skill_read", {"name": "review"}))
    assert healthy.status == "ok" and "REVIEW_BODY" in healthy.render()


def test_an_undecodable_skill_is_disclosed_in_the_prompt_and_the_refusal(skill_workspace):
    from minicc.commands import skill_file_failures
    from minicc.tools.schemas import ToolCall

    workspace, home, registry = skill_workspace
    broken = home / "skills" / "deploy" / "SKILL.md"
    broken.parent.mkdir(parents=True)
    broken.write_bytes("---\nname: deploy\ndescription: 部署\n---\n正文\n".encode("gbk"))
    failures = skill_file_failures(workspace)
    assert [(item.name, item.reason_text) for item in failures] == [("deploy", "编码读不出来")]
    prompt = skills_prompt_block(workspace)
    assert "deploy" in prompt and "编码读不出来" in prompt
    assert "正文" not in prompt
    result = registry.execute(ToolCall("skill_read", {"name": "deploy"}))
    assert result.status == "error" and "编码读不出来" in result.render()
    assert "正文" not in result.render()


def test_an_empty_skill_file_is_not_a_read_failure(skill_workspace):
    from minicc.commands import skill_file_failures
    from minicc.tools.schemas import ToolCall

    workspace, home, registry = skill_workspace
    _skill(home, "deploy", "")
    assert skill_file_failures(workspace) == []
    assert skills_prompt_block(workspace) == ""
    result = registry.execute(ToolCall("skill_read", {"name": "deploy"}))
    assert result.status == "error"
    assert "编码读不出来" not in result.render() and "操作系统不给读" not in result.render()


def test_a_denied_skill_is_not_disclosed_as_a_read_failure(skill_workspace):
    from minicc.commands import skill_file_failures

    workspace, home, _registry = skill_workspace
    path = _skill(home, "deploy", "DENIED_BODY")
    policy = workspace / ".minicc" / "permissions.json"
    policy.parent.mkdir(exist_ok=True)
    policy.write_text(json.dumps({"deny": {"paths": [path.as_posix()]}}), encoding="utf-8")
    assert skill_file_failures(workspace) == []
    assert skills_prompt_block(workspace) == ""


@pytest.mark.parametrize("window", [{}, {"offset": 2, "limit": 1}])
def test_skill_credentials_are_refused_before_windowing_or_truncation(skill_workspace, window):
    from minicc.tools.schemas import ToolCall

    workspace, home, registry = skill_workspace
    payload = "SYNTHETIC_KEY_PAYLOAD" * 800
    body = "\n".join(["-----BEGIN TEST PRIVATE KEY-----", payload, "-----END TEST PRIVATE KEY-----"])
    _skill(home, "deploy", body)
    result = registry.execute(ToolCall("skill_read", {"name": "deploy", **window}))
    assert result.status == "error", result.render()[:200]
    assert "SYNTHETIC_KEY_PAYLOAD" not in result.render()
    assert "凭据" in result.render()


@pytest.mark.parametrize("change", ["update", "deny-path", "deny-read-file", "project-override"])
def test_agent_skill_reads_recheck_catalog_and_permission_changes(skill_workspace, change):
    import asyncio

    from minicc.agent.loop import run_agent
    from minicc.llm.base import LLMResponse

    workspace, home, registry = skill_workspace
    target = _skill(home, "deploy", "FIRST_BODY")
    seen = []

    class ReadsTwice:
        calls = 0

        async def chat(self, messages, tools=None, on_delta=None, **kwargs):
            self.calls += 1
            if self.calls <= 2:
                return LLMResponse(tool_calls=[{
                    "id": f"skill-{self.calls}", "type": "function",
                    "function": {"name": "skill_read", "arguments": json.dumps({"name": "deploy"})},
                }], finish_reason="tool_calls")
            return LLMResponse(content="done", finish_reason="stop")

    def on_tool(call, result):
        seen.append(result)
        if len(seen) != 1:
            return
        if change == "update":
            _skill(home, "deploy", "UPDATED_BODY")
        elif change == "project-override":
            _skill(workspace / ".minicc", "deploy", "UPDATED_BODY")
        else:
            policy = workspace / ".minicc" / "permissions.json"
            policy.parent.mkdir(exist_ok=True)
            rules = {"paths": [target.as_posix()]} if change == "deny-path" else {"tools": ["read_file"]}
            policy.write_text(json.dumps({"deny": rules}), encoding="utf-8")

    asyncio.run(run_agent(
        ReadsTwice(), registry, [{"role": "user", "content": "读取技能"}],
        max_turns=6, on_tool=on_tool, should_allow=lambda _name, _call: True, workspace=workspace,
    ))
    assert len(seen) == 2
    assert seen[0].status == "ok" and "FIRST_BODY" in seen[0].render()
    assert not seen[1].data.get("cached") and "FIRST_BODY" not in seen[1].render()
    if change.startswith("deny"):
        assert seen[1].status in {"error", "denied"}
    else:
        assert seen[1].status == "ok" and "UPDATED_BODY" in seen[1].render()


def test_web_listing_exposes_metadata_only(tmp_path: Path) -> None:
    from minicc.web import AgentService

    home = tmp_path / "home"
    ws = tmp_path / "ws"
    _project(ws, "review", REVIEW)
    service = object.__new__(AgentService)
    service.workspace = ws
    payload = service.list_commands()
    dumped = json.dumps(payload, ensure_ascii=False)
    assert payload["commands"][0]["name"] == "review"
    assert "请审查" not in dumped, "template bodies must not leak via /api/commands"


# ---------------------------------------------------------------------------
# M7-T2 acceptance: the Web composer reaches the same expansion engine.
# The pure-function gates above cover discovery and expansion; this one walks
# the real web entry (_chat_locked), so a regression that wires the CLI but
# forgets the web.py call site turns red here instead of only failing by hand.
# ---------------------------------------------------------------------------


def test_web_composer_expands_the_command_before_the_model(tmp_path: Path, monkeypatch) -> None:
    from types import SimpleNamespace

    from minicc import web as web_module
    from minicc.web import AgentService

    class _Capturing:
        instances: list["_Capturing"] = []

        def __init__(self, *args, **kwargs) -> None:
            from minicc.llm.fake import FakeProvider

            # The web loop runs a completion judge on a provider whose answer
            # must parse; a hand-written script cannot honor that contract, so
            # delegate everything to the scripted FakeProvider and only record.
            self._inner = FakeProvider()
            self.seen: list[list[dict]] = []
            _Capturing.instances.append(self)

        async def chat(self, messages, tools, on_delta=None):
            self.seen.append([dict(m) for m in messages])
            return await self._inner.chat(messages, tools, on_delta=on_delta)

        async def close(self) -> None:
            return await self._inner.close()

    _Capturing.instances = []
    monkeypatch.setattr(web_module, "OpenAICompatibleProvider", _Capturing)

    ws = tmp_path / "ws"
    ws.mkdir()
    _project(ws, "review", REVIEW)
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
        fallback_models=(),
    )
    service = AgentService(ws, config)
    try:
        result = service._chat_locked(
            {
                "message": "/review src/main.py",
                "session_id": "slash-web-wiring",
                "allow_changes": False,
                "workspace_path": str(ws),
            },
            workspace=ws,
        )
    finally:
        service.shutdown()

    assert result["error"] is None, result.get("error")
    messages = [m for cap in _Capturing.instances for batch in cap.seen for m in batch]
    user_texts = [str(m.get("content") or "") for m in messages if m.get("role") == "user"]
    system_texts = [str(m.get("content") or "") for m in messages if m.get("role") == "system"]
    assert any(
        "请审查 src/main.py 的改动" in t and "第一个参数：src/main.py" in t
        for t in user_texts
    ), "the expanded template never reached the model as user content"
    assert not any("$ARGUMENTS" in t for t in user_texts + system_texts)
    assert not any("重点关注正确性" in t for t in system_texts), (
        "template body must never enter the system prompt — expanded commands are "
        "user content, so they cannot rewrite instructions or permission boundaries"
    )


# ---------------------------------------------------------------------------
# Built-in REPL commands: the /help line must cover every command the REPL
# dispatches. README「交互命令」行承诺了其中九条；/cost 实现于 REPL 但曾被
# 两份清单同时漏掉（/help 文本与 README），这条测试把清单钉成一处。
# ---------------------------------------------------------------------------


def test_builtin_help_line_covers_every_dispatched_command() -> None:
    from minicc.main import BUILTIN_HELP_LINE

    expected = [
        "/help",
        "/tools",
        "/status",
        "/view",
        "/compact",
        "/collapse",
        "/expand [n]",
        "/clear",
        "/cost",
        "/exit",
    ]
    missing = [name for name in expected if name not in BUILTIN_HELP_LINE]
    assert not missing, f"/help line is missing dispatched commands: {missing}"
