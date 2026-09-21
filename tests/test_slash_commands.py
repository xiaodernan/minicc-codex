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
