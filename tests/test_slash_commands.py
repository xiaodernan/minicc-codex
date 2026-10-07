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
from pathlib import Path

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
