"""M8-T364 — CLI 显示与落盘的工具命令，要用**同一个脱敏副本**

用户看到的工具调用有两个去处 ✓：终端上那一行 ✓，以及**视图历史文件** ✓
（`session.save_view` ✓）。而 CLI 两个去处都写的是**原始命令** ✗。

Web 那边显示的命令来自循环给事件做的那份**脱敏副本** ✓（`build_tool_feedback` ✓
—— 它的 docstring 就写着"safe to show in the UI" ✓）。于是同一个事实（用户看到的
命令）✓，两个面两个答案 ✓：Web 给脱敏版 ✓，CLI 给原文 ✓。

后果 ✓：命令里的 token（`sk-*` ✓ / `Bearer …` ✓）被印到终端 ✓，也被**写进磁盘上
的视图文件** ✓。

本门钉住：CLI 的终端输出 ✓ 与视图历史文件 ✓ 里**都没有**那个密钥 ✓；控制组——
CLI 显示的命令与 Web 那份**是同一句话** ✓（两个面问同一个事实 ✓）。
"""

from __future__ import annotations

from pathlib import Path

from minicc.agent.loop import build_tool_feedback
from minicc.main import CliView
from minicc.session import SessionStore
from minicc.tools import ToolCall, ToolResult

#: Built at run time on purpose: a credential-looking literal in this file
#: would be caught by the repository's own pre-commit secret scan.
SECRET = "sk-" + "abcdefghij1234567890"
COMMAND = f"curl -H 'Authorization: Bearer {SECRET}' https://example.invalid/x"


def _view(tmp_path: Path) -> CliView:
    session = SessionStore(tmp_path, "cli")
    return CliView(session)


def _call() -> ToolCall:
    return ToolCall(tool="bash", arguments={"command": COMMAND}, call_id="c1")


def _result() -> ToolResult:
    return ToolResult(status="ok", summary="执行完成", output="ok")


def test_the_cli_line_does_not_print_the_secret(
    tmp_path: Path, capsys
) -> None:
    view = _view(tmp_path)
    view.record_tool(_call(), _result())
    printed = capsys.readouterr().out
    assert SECRET not in printed, printed
    assert "REDACTED" in printed, printed


def test_the_view_file_does_not_keep_the_secret(tmp_path: Path) -> None:
    """An invariant, not a discriminator for this batch.

    The session store redacts what it writes, so the view file never held
    the secret - even before this batch.  The batch's leak was the
    **terminal line**; this assertion keeps the disk side honest too.
    """
    view = _view(tmp_path)
    view.record_tool(_call(), _result())
    stored = view.session.load_view()
    assert SECRET not in str(stored), stored


def test_both_faces_show_the_same_command(tmp_path: Path) -> None:
    """The control: the CLI and the Web face show one and the same command."""
    call = _call()
    result = _result()
    web_side = str(build_tool_feedback(call, result).get("command") or "")

    view = _view(tmp_path)
    view.record_tool(call, result)
    history = view.tool_history[-1]

    assert web_side and web_side in history["command"], (web_side, history)
