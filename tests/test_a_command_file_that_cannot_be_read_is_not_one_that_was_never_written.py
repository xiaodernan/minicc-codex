"""M8-T528: a command file that cannot be read is not a file that was never written.

``minicc/commands.py`` answered one question - "is there a command named X?" -
with one value, and it collapsed three different facts into it: the file is
fine, the file exists but produced no prompt, and the file exists but **no
bytes came over at all**.  The third one is not the second one.

The consequence was measured on the shipped tree, not argued:

    spelling=ok      in /help=True   expand->template   model receives the prompt
    spelling=gbk     in /help=False  expand->None       model receives '/review src/x.py'
    spelling=empty   in /help=False  expand->None       model receives '/review src/x.py'
    writer holds it  in /help=False  expand->None       model receives '/review x'

so the web ``/api/chat`` face - witnessed by driving ``AgentService.chat`` with
a recording provider - handed the user's literal ``/review 检查 src/x.py`` to
the model as ordinary prose.  The user pressed the button that runs their own
curated prompt; the model read the button's label and improvised.  And the CLI
answered "未知命令" about a file that is on disk, sending the user to a ``/help``
that cannot show it either.

A file saved as ANSI/GBK by Notepad, or as UTF-8-with-BOM by Windows
PowerShell's ``Set-Content``, reaches these states with no bug in this
repository - those are the spellings a hand-edit produces on the platform this
project ships on.

What this does NOT change: a readable file with no prompt body is still not a
command, and an unknown ``/name`` nobody ever wrote still expands to None and
still travels to the model as the text the user typed.
"""

from __future__ import annotations

import re
import types
from pathlib import Path
from typing import Any

import pytest

from minicc import commands as cmd
from minicc.commands import (
    READ_UNDECODABLE,
    READ_UNREADABLE,
    command_file_failures,
    discover_commands,
    expand_slash_command,
    slash_command_read_refusal,
)

REVIEW = "---\ndescription: 审查当前改动\nargument-hint: [scope]\n---\n请审查 $ARGUMENTS 的改动。\n"
GBK_BODY = "请审查改动。这里是 GBK 字节。\n"


def _project(ws: Path, name: str, data: bytes) -> Path:
    root = ws / ".minicc" / "commands"
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{name}.md"
    target.write_bytes(data)
    return target


def _user(home: Path, name: str, data: bytes) -> Path:
    root = home / "commands"
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{name}.md"
    target.write_bytes(data)
    return target


def _utf8(text: str) -> bytes:
    return text.encode("utf-8")


def _gbk(text: str) -> bytes:
    return text.encode("gbk")


# --- the two facts are two facts -------------------------------------------


def test_an_undecodable_command_file_is_reported_and_not_looked_up(tmp_path: Path) -> None:
    """A hand-edit saved as ANSI/GBK: the file is there, no prompt came over."""
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    _project(ws, "review", _gbk(GBK_BODY))

    assert [c.name for c in discover_commands(ws, home=home)] == []
    failures = command_file_failures(ws, home=home)
    assert [f.name for f in failures] == ["review"]
    assert failures[0].reason == READ_UNDECODABLE
    assert failures[0].scope == "project"
    assert failures[0].detail, "a reason with no evidence behind it is a shrug"


def test_an_unreadable_command_file_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The OS would not hand the bytes over - a live writer, a locked file."""
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    _project(ws, "review", _utf8(REVIEW))
    real_read = Path.read_text

    def _denied(self: Path, *args: Any, **kwargs: Any) -> str:
        if self.name == "review.md":
            raise PermissionError(13, "另一个进程正在使用此文件")
        return real_read(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _denied)
    failures = command_file_failures(ws, home=home)
    assert [f.reason for f in failures] == [READ_UNREADABLE]
    assert "另一个进程" in failures[0].detail


def test_a_readable_file_with_no_prompt_is_still_not_a_failure(tmp_path: Path) -> None:
    """No body is not "we could not read it" - nothing was ever written."""
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    _project(ws, "review", _utf8("---\ndescription: 只有前言\n---\n\n"))
    assert command_file_failures(ws, home=home) == []
    assert expand_slash_command("/review x", ws, home=home) is None


def test_an_empty_file_does_not_hide_a_broken_one_in_the_other_scope(tmp_path: Path) -> None:
    """A project file with no prompt defines nothing, so it cannot be the
    reason a broken user file stops being worth reporting."""
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    _user(home, "review", _gbk(GBK_BODY))
    _project(ws, "review", _utf8("---\ndescription: 只有前言\n---\n\n"))
    failures = command_file_failures(ws, home=home)
    assert [f.scope for f in failures] == ["user"]
    assert slash_command_read_refusal("/review x", ws, home=home).startswith("自定义命令 /review")


def test_a_working_command_shadowing_a_broken_one_is_not_reported(tmp_path: Path) -> None:
    """Both directions: the name resolves, so saying 读不出来 would be a lie."""
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    _project(ws, "review", _utf8(REVIEW))
    _user(home, "review", _gbk(GBK_BODY))
    assert command_file_failures(ws, home=home) == []
    assert expand_slash_command("/review a", ws, home=home) == "请审查 a 的改动。"

    home2 = tmp_path / "home2"
    ws2 = tmp_path / "ws2"
    _user(home2, "review", _utf8(REVIEW))
    _project(ws2, "review", _gbk(GBK_BODY))
    assert command_file_failures(ws2, home=home2) == []
    assert expand_slash_command("/review b", ws2, home=home2) == "请审查 b 的改动。"


# --- the refusal, in one home ----------------------------------------------


def test_the_refusal_names_only_a_broken_command_file(tmp_path: Path) -> None:
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    target = _project(ws, "review", _gbk(GBK_BODY))
    _project(ws, "ok", _utf8("一个可用的命令"))

    refusal = slash_command_read_refusal("/review src/x.py", ws, home=home)
    assert refusal.startswith("自定义命令 /review")
    assert str(target) in refusal, "the user has to know which file to fix"
    assert GBK_BODY not in refusal, "a refusal must not dump the file it could not read"

    assert slash_command_read_refusal("正常消息", ws, home=home) == ""
    assert slash_command_read_refusal("/help", ws, home=home) == ""
    assert slash_command_read_refusal("/nosuchcommand args", ws, home=home) == ""
    assert slash_command_read_refusal("/ok x", ws, home=home) == "", (
        "a command that expanded has nothing to refuse"
    )


def test_the_refusal_is_the_same_sentence_for_every_face(tmp_path: Path) -> None:
    """One wording, three faces - the CLI must not paraphrase the web."""
    ws = tmp_path / "ws"
    home = tmp_path / "home"
    _project(ws, "review", _gbk(GBK_BODY))
    first = slash_command_read_refusal("/review x", ws, home=home)
    assert first
    assert first == slash_command_read_refusal("/review y z", ws, home=home)


# --- the BOM is not a prompt -----------------------------------------------


def test_a_utf8_bom_does_not_turn_front_matter_into_instructions(tmp_path: Path) -> None:
    """Windows PowerShell's Set-Content writes a BOM; the ``---`` opener was
    no longer the first line, so the metadata block never closed and the
    model received ``description:`` as part of its instructions."""
    home = tmp_path / "home"
    ws = tmp_path / "ws"
    _project(ws, "review", b"\xef\xbb\xbf" + _utf8(REVIEW))

    commands = discover_commands(ws, home=home)
    assert [c.name for c in commands] == ["review"]
    assert commands[0].description == "审查当前改动"
    expanded = expand_slash_command("/review src/x.py", ws, home=home)
    assert expanded == "请审查 src/x.py 的改动。"
    assert "description" not in expanded
    assert "\ufeff" not in expanded


# --- the web face -----------------------------------------------------------


class _Config:
    yolo = False
    max_concurrent_tasks = 2
    sandbox_mode = "host"
    sandbox_image = "python:3.11-slim"
    base_url = "https://example.test/v1"
    api_key = "test-key"
    model = "test-model"
    timeout = 10
    tool_mode = "auto"
    reasoning_effort = "high"
    max_turns = 4
    compact_threshold = 300_000
    context_window_tokens = 300_000
    workspace_roots = ()
    output_style = ""
    llm_protocol = "chat_completions"
    provider_retries = 4


class _Recorder:
    def __init__(self, received: list[str]) -> None:
        self._received = received

    async def chat(self, messages: Any, tools: Any = None, **kwargs: Any) -> Any:
        self._received.append(str(messages[-1]["content"]))
        from minicc.llm.base import LLMResponse

        return LLMResponse(content="ok", finish_reason="stop")

    async def close(self) -> None:
        return None


def _service(ws: Path, received: list[str]) -> Any:
    from minicc.web import AgentService

    service = AgentService(ws, _Config())  # type: ignore[arg-type]
    service._make_provider = lambda **kwargs: _Recorder(received)  # type: ignore[assignment]
    return service


def test_the_web_chat_refuses_instead_of_forwarding_the_button_label(tmp_path: Path) -> None:
    received: list[str] = []
    ws = tmp_path / "ws"
    _project(ws, "review", _gbk(GBK_BODY))
    service = _service(ws, received)

    with pytest.raises(ValueError) as raised:
        service.chat({"message": "/review 检查 src/x.py", "session_id": "gate"})
    assert "自定义命令 /review" in str(raised.value)
    assert received == [], "the model must never see a /name it was meant to expand"


def test_the_web_chat_still_sends_prose_and_working_commands(tmp_path: Path) -> None:
    received: list[str] = []
    ws = tmp_path / "ws"
    _project(ws, "review", _utf8(REVIEW))
    service = _service(ws, received)

    # The run asks the provider again for its completion judge, so the gate
    # reads the first message of each run - the one that carries the user's
    # (expanded or literal) text.
    start = len(received)
    service.chat({"message": "/review src/x.py", "session_id": "a"})
    assert received[start] == "请审查 src/x.py 的改动。"
    start = len(received)
    service.chat({"message": "/nosuchcommand 参数", "session_id": "b"})
    assert received[start] == "/nosuchcommand 参数", "an unknown name is the user's text"
    start = len(received)
    service.chat({"message": "解释一下 /tmp 目录", "session_id": "c"})
    assert received[start] == "解释一下 /tmp 目录"


def test_the_listing_discloses_a_broken_command_without_its_content(tmp_path: Path) -> None:
    received: list[str] = []
    ws = tmp_path / "ws"
    target = _project(ws, "review", _gbk(GBK_BODY))
    _project(ws, "ok", _utf8("一个可用的命令"))
    payload = _service(ws, received).list_commands()

    assert [c["name"] for c in payload["commands"]] == ["ok"]
    assert payload["unreadable"] == [
        {"name": "review", "scope": "project", "reason": READ_UNDECODABLE}
    ]
    dumped = repr(payload)
    assert GBK_BODY not in dumped
    assert str(target) not in dumped, "to_public_dict omits the path; so does this"


# --- the CLI faces ----------------------------------------------------------


class _CliProvider:
    """Stand-in for the configured provider; the run itself is stubbed."""

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = dict(kwargs)

    @classmethod
    def is_transient_failure(cls, error: object) -> bool:
        return False

    def protocol(self) -> str:
        return "chat_completions"

    def protocol_status(self) -> dict[str, str]:
        return {"requested": "chat_completions", "active": "chat_completions"}

    async def chat(self, messages: Any, tools: Any = None, **kwargs: Any) -> Any:
        from minicc.llm.base import LLMResponse

        return LLMResponse(content="cli-ok", finish_reason="stop")

    async def close(self) -> None:
        return None


def test_the_cli_one_shot_refuses_with_a_nonzero_exit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import minicc.main as cli

    ws = tmp_path / "ws"
    _project(ws, "review", _gbk(GBK_BODY))
    turns: list[str] = []

    async def _recording_turn(provider: Any, registry: Any, messages: Any, config: Any, prompt: Any, *a: Any, **k: Any) -> None:
        turns.append(str(prompt))

    async def _no_interactive(*a: Any, **k: Any) -> None:
        return None

    lines: list[str] = []
    monkeypatch.setattr(cli, "_turn", _recording_turn)
    monkeypatch.setattr(cli, "_interactive", _no_interactive)
    monkeypatch.setattr(cli, "OpenAICompatibleProvider", _CliProvider)
    monkeypatch.setattr(cli, "cli_out", lambda *args: lines.append(" ".join(str(x) for x in args)))

    code = cli.main(["--workspace", str(ws), "--no-stream", "/review 检查 src/x.py"])
    assert code == 1, f"a refused one-shot run must not report success: {lines}"
    assert turns == []
    assert any("自定义命令 /review" in line for line in lines), lines

    # Control, same face: a readable file still runs the turn with the
    # expanded prompt and still reports success.
    turns.clear()
    lines.clear()
    _project(ws, "review", _utf8(REVIEW))
    code = cli.main(["--workspace", str(ws), "--no-stream", "/review src/x.py"])
    assert code == 0, lines
    assert turns == ["请审查 src/x.py 的改动。"]


def test_the_repl_stops_calling_a_broken_file_an_unknown_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import minicc.main as cli

    ws = tmp_path / "ws"
    target = _project(ws, "review", _gbk(GBK_BODY))
    lines: list[str] = []
    asked = iter(["/review x", "/help", "/exit"])
    turns: list[str] = []

    async def _recording_turn(provider: Any, registry: Any, messages: Any, config: Any, prompt: Any, *a: Any, **k: Any) -> None:
        turns.append(str(prompt))

    monkeypatch.setattr("builtins.input", lambda *_a: next(asked))
    monkeypatch.setattr(cli, "cli_out", lambda *args: lines.append(" ".join(str(x) for x in args)))
    monkeypatch.setattr(cli, "_turn", _recording_turn)

    config = types.SimpleNamespace(max_output_tokens=100)
    registry = types.SimpleNamespace(names=lambda: [], get=lambda name: None)
    import asyncio

    asyncio.run(
        cli._interactive(
            types.SimpleNamespace(), registry, [], config,
            session=None, view=None, stream=False, workspace=ws,
        )
    )
    assert turns == []
    refusal = [line for line in lines if "自定义命令 /review" in line]
    assert refusal, lines
    assert not any("未知命令：/review" in line for line in lines), (
        f"{target} is on disk; '未知命令' is the wrong sentence"
    )
    assert any("未加载" in line and "/review" in line for line in lines), (
        f"/help must show the file it could not load: {lines}"
    )


# --- one home, no second answer --------------------------------------------


def _package_tree() -> Path:
    return Path(cmd.__file__).resolve().parent


def test_no_call_site_keeps_its_own_fallback_for_an_unexpanded_command() -> None:
    """``expand_slash_command(...) or <the raw text>`` is exactly the shape
    that forwarded the label; it must not come back at a fourth face."""
    offenders = []
    for source in sorted(_package_tree().rglob("*.py")):
        text = source.read_text(encoding="utf-8")
        for line in text.splitlines():
            if "expand_slash_command" in line and re.search(r"\)\s*or\s+", line):
                offenders.append(f"{source.name}:{line.strip()}")
    assert offenders == [], offenders


def test_the_reading_of_a_command_file_has_one_home() -> None:
    """Only ``minicc/commands.py`` reads ``.minicc/commands``."""
    readers = []
    for source in sorted(_package_tree().rglob("*.py")):
        if source.name == "commands.py":
            continue
        text = source.read_text(encoding="utf-8")
        if "COMMANDS_DIR_NAME" in text or '".minicc" / "commands"' in text:
            readers.append(str(source))
    assert readers == [], readers


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q", "-W", "error"]))
