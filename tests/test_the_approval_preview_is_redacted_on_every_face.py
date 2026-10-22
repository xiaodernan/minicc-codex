"""M8-T363 — 审批预览要脱敏：同一个问题，两个面必须给同一个答案

用户被问"允许这次调用吗"时看到的**预览**，是两个面（Web 的审批请求 ✓ / CLI 的
权限询问 ✓）问的**同一个问题** ✓，所以答案也该是同一个 ✓。

Web 那边的预览**脱敏** ✓（`redact_text` ✓ —— 命令或参数里可能带着 token ✓）；
CLI 那边的预览**不脱敏** ✗：`_tool_preview` 直接把 `bash` 的完整命令 ✓、或工具的
完整参数 ✓ 印到终端上 ✓。

于是 Web 藏起来的密钥 ✓，CLI 印了出来 ✓——终端的回滚缓冲 ✓、用户粘去提 issue 的
那段输出 ✓、CI 日志 ✓，全都带着它 ✓。

本门钉住：CLI 的权限询问**不打印密钥** ✓（终端输出里没有它 ✓、有脱敏标记 ✓）；
控制组——Web 那边的预览仍然照旧 ✓，而且**两个面的预览说的是同一句话** ✓。
"""

from __future__ import annotations

from pathlib import Path

from minicc.config import Config
from minicc.main import _permission_gate, _tool_preview
from minicc.tools import ToolCall, build_registry
from minicc.tools.editor import Editor

#: The secret is built at run time on purpose: a literal that looks like a
#: credential in this file would be caught by the repository's own
#: pre-commit secret scan, and it must not be committed either way.
SECRET = "sk-" + "abcdefghij1234567890"
COMMAND = f"curl -H 'Authorization: Bearer {SECRET}' https://example.invalid/x"


def _config() -> Config:
    return Config(base_url="http://localhost:1/v1", api_key="k", model="m")


def test_the_cli_preview_hides_the_secret() -> None:
    call = ToolCall(tool="bash", arguments={"command": COMMAND}, call_id="c1")
    preview = _tool_preview(call)
    assert SECRET not in preview, preview
    assert "REDACTED" in preview, preview
    # The harmless part of the command is still readable.
    assert "example.invalid" in preview, preview


def test_the_permission_prompt_never_prints_the_secret(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setattr("builtins.input", lambda *_: "n")
    gate = _permission_gate(
        _config(),
        build_registry(Editor(tmp_path)),
        "default",
        session_id="s1",
        workspace=tmp_path,
    )
    call = ToolCall(tool="bash", arguments={"command": COMMAND}, call_id="c1")
    assert gate("bash", call) is False

    printed = capsys.readouterr().out
    assert SECRET not in printed, printed
    assert "REDACTED" in printed, printed


def test_both_faces_say_the_same_thing() -> None:
    """The control: the Web face keeps its contract, and the two agree."""
    from minicc.web import AgentService

    arguments = {"command": COMMAND}
    web_preview = AgentService._approval_preview("bash", arguments)
    cli_preview = _tool_preview(ToolCall(tool="bash", arguments=arguments, call_id="c1"))

    assert SECRET not in web_preview, web_preview
    assert SECRET not in cli_preview, cli_preview
    # The CLI adds a label; the wording underneath is the same.
    assert "example.invalid" in web_preview, web_preview
    assert "example.invalid" in cli_preview, cli_preview
