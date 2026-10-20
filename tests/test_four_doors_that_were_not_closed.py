"""M8-T315 / T316 / T317 / T318 — 四道门该关的地方没关

| 编号 | 门 | 洞 |
| --- | --- | --- |
| M8-T315 | 沙箱的加固旗标 | ``sandbox_image`` 落在 docker run 的**选项**位置，一个以 ``-`` 开头的值会被当成选项消费——项目级配置里的 ``--privileged`` 把上面加的加固全废了 |
| M8-T316 | "坏 hooks.json 只关掉 hooks" | 读文件/解析 JSON 的错误**在保护之外**，一个 BOM 就让整次运行挂掉（Web 500、CLI 中止） |
| M8-T317 | deny 规则覆盖所有读路径 | mention 注入是工作区的**第三个**读者，它只查了 .minicc 凭据表——``read_file`` 被拒的路径被 ``@`` 整份塞进了模型 |
| M8-T318 | slash 命令的参数替换 | 模板的位置参数替换跑在**用户文本插入之后**，用户自己写的 ``$1`` 被替换或被删掉 |

This door pins all four.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from minicc.commands import expand_slash_command
from minicc.hooks import HookConfigError, HookRunner
from minicc.mentions import apply_mentions
from minicc.sandbox import SandboxRunner


# --- M8-T315: an image name is not an option ------------------------------------


def test_an_image_name_that_looks_like_an_option_is_refused(tmp_path: Path) -> None:
    """``--privileged`` must not reach docker's option parser."""
    sandbox = SandboxRunner("docker", image="--privileged")
    result = sandbox.run("echo hi", tmp_path)
    assert result.status == "error", (
        "an image name that reads as an option was accepted"
    )
    assert "sandbox_image" in result.summary or "镜像" in result.summary, result.summary


def test_an_empty_image_is_refused(tmp_path: Path) -> None:
    sandbox = SandboxRunner("docker", image="")
    result = sandbox.run("echo hi", tmp_path)
    assert result.status == "error"


def test_an_ordinary_image_name_is_accepted(tmp_path: Path) -> None:
    """The control: a real image name is not refused."""
    from minicc import sandbox as sandbox_module

    captured: dict[str, Any] = {}

    def fake_run(args, workspace, timeout=120, cancel_event=None, shell=False,
                summary_label="", security_tags=()):
        captured["args"] = list(args)
        from minicc.tools.schemas import ToolResult

        return ToolResult(status="ok", summary="ok")

    original_run = sandbox_module.run_process
    original_status = SandboxRunner.status
    sandbox_module.run_process = fake_run  # type: ignore[assignment]
    SandboxRunner.status = lambda self: {  # type: ignore[method-assign]
        "mode": "docker", "backend": "docker", "docker_available": True,
        "image": self.image, "isolated": True,
    }
    try:
        sandbox = SandboxRunner("docker", image="python:3.11-slim")
        result = sandbox.run("echo hi", tmp_path)
    finally:
        sandbox_module.run_process = original_run  # type: ignore[assignment]
        SandboxRunner.status = original_status  # type: ignore[method-assign]
    assert result.status == "ok", result.summary
    assert "python:3.11-slim" in captured.get("args", [])


# --- M8-T316: a malformed hooks.json only disables the hooks -------------------


def test_a_bom_prefixed_hooks_file_does_not_kill_the_run(tmp_path: Path) -> None:
    """A BOM is what several Windows editors write by default."""
    config = tmp_path / ".minicc" / "hooks.json"
    config.parent.mkdir(parents=True)
    config.write_bytes(
        json.dumps({"hooks": {}}, ensure_ascii=False).encode("utf-8-sig")
    )
    runner = HookRunner(tmp_path)
    assert runner.specs == []
    assert runner.load_error is None, runner.load_error


def test_an_invalid_hooks_file_does_not_kill_the_run(tmp_path: Path) -> None:
    """The control: a broken file is reported, and the run continues."""
    config = tmp_path / ".minicc" / "hooks.json"
    config.parent.mkdir(parents=True)
    config.write_text("{not json", encoding="utf-8")
    runner = HookRunner(tmp_path)
    assert runner.specs == []
    assert runner.load_error, "the broken file was not reported"


def test_a_non_object_hooks_file_still_raises(tmp_path: Path) -> None:
    """The existing contract: a wrong top level is a configuration error."""
    config = tmp_path / ".minicc" / "hooks.json"
    config.parent.mkdir(parents=True)
    config.write_text("[]", encoding="utf-8")
    with pytest.raises(HookConfigError):
        HookRunner(tmp_path)


# --- M8-T317: a mention is a read too ------------------------------------------


def test_a_denied_path_is_not_injected_by_a_mention(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    (workspace / "secrets").mkdir(parents=True)
    (workspace / "secrets" / "k.txt").write_text("TOP-SECRET-PAYLOAD\n", encoding="utf-8")
    (workspace / ".minicc").mkdir()
    (workspace / ".minicc" / "permissions.json").write_text(
        json.dumps({"deny": {"paths": ["secrets/*"]}}), encoding="utf-8"
    )
    message, records = apply_mentions("@secrets/k.txt 请看", workspace)
    assert "TOP-SECRET-PAYLOAD" not in message, (
        "a denied path was injected into the model context"
    )
    assert any(item.get("status") == "rejected" for item in records), records


def test_an_allowed_path_is_still_injected(tmp_path: Path) -> None:
    """The control: the ordinary mention still works."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "notes.txt").write_text("hello\n", encoding="utf-8")
    message, records = apply_mentions("@notes.txt 请看", workspace)
    assert "hello" in message, message
    assert any(item.get("status") == "injected" for item in records), records


# --- M8-T318: the user's own text survives the expansion -----------------------


def test_a_literal_dollar_one_in_the_arguments_survives(tmp_path: Path) -> None:
    """``$1`` in the user's text is the user's text."""
    command = tmp_path / ".minicc" / "commands" / "demo.md"
    command.parent.mkdir(parents=True)
    command.write_text("Task: $1\nArgs: $ARGUMENTS\n", encoding="utf-8")
    expanded = expand_slash_command("/demo check $1 file", tmp_path)
    assert expanded is not None
    assert "check $1 file" in expanded, expanded


def test_a_literal_dollar_nine_is_not_deleted(tmp_path: Path) -> None:
    """An out-of-range index used to delete the text silently."""
    command = tmp_path / ".minicc" / "commands" / "demo.md"
    command.parent.mkdir(parents=True)
    command.write_text("Task: $1\nArgs: $ARGUMENTS\n", encoding="utf-8")
    expanded = expand_slash_command("/demo use $9 here", tmp_path)
    assert expanded is not None
    assert "$9" in expanded, expanded


def test_the_templates_own_positionals_still_expand(tmp_path: Path) -> None:
    """The control: the template's placeholders are the template's."""
    command = tmp_path / ".minicc" / "commands" / "demo.md"
    command.parent.mkdir(parents=True)
    command.write_text("Task: $1\nArgs: $ARGUMENTS\n", encoding="utf-8")
    expanded = expand_slash_command("/demo check the file", tmp_path)
    assert expanded is not None
    assert "Task: check" in expanded, expanded
    assert "Args: check the file" in expanded, expanded
