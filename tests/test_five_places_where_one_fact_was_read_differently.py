"""M8-T308 / T309 / T310 / T311 / T312 — 同一份数据，五处分叉

这一批专门盯住"同一份数据在几处被各自解释"这个形状。五处都**已经**分叉了：

| 编号 | 事实来源 | 分叉 |
| --- | --- | --- |
| M8-T308 | `is_workspace_write`（"这次调用改了工作区"） | Web 事件流用**窄**的写工具名单重算了一遍，bash 改写因此不算写 → 验证阶段被跳过、任务被判"没改任何东西"、检查点被标成安全只读 |
| M8-T309 | 带标签密钥的规则 | 模型上下文问"这值像不像凭据"，日志侧**裸跑**同一条正则 → 同一段源码在两处被改成不同样子 |
| M8-T310 | 改动文件清单 | 审计记**原始拼写**、git 记**干净路径** → 同一个文件进清单两次，状态自相矛盾，加减行数被加两遍 |
| M8-T311 | `SKIP_DIRS` 的跳过规则 | glob/grep 按"只跳目录"，tree 与 Web 文件树按"名字命中就跳" → 一个叫 `build` 的**普通文件**在 agent 的 glob 里存在、在 tree 里不存在 |
| M8-T312 | `.minicc/audit.jsonl` | 变更面板只看最后 500 行且不披露，审计面板读全文件 → 改动被挤出窗口后面板说"工作区干净" |

This door pins all five.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from minicc.changes import ChangeInspector
from minicc.logging_setup import redact
from minicc.tools.editor import Editor
from minicc.tools.registry import redact_text


def _git(workspace: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=str(workspace),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


def _repo(workspace: Path) -> Path:
    workspace.mkdir(parents=True, exist_ok=True)
    _git(workspace, "init")
    _git(workspace, "config", "user.email", "t@example.test")
    _git(workspace, "config", "user.name", "t")
    return workspace


# --- M8-T308: the write flag has one meaning -----------------------------------


def test_the_web_event_and_the_agent_loop_agree_on_a_write(tmp_path: Path) -> None:
    """A bash rewrite is a write, and the event stream has to say so."""
    from minicc.agent.loop import build_tool_feedback
    from minicc.agent.tool_policy import is_workspace_write
    from minicc.tools.schemas import ToolCall, ToolResult

    call = ToolCall(
        tool="bash",
        arguments={"command": "sed -i 's/a/b/' notes.md"},
        call_id="c1",
    )
    result = ToolResult(status="ok", summary="ok")
    feedback = build_tool_feedback(call, result, risk="exec")

    assert is_workspace_write("bash", call.arguments, "ok") is True
    assert feedback.get("write") is True, (
        "the canonical predicate and the feedback disagree about a bash rewrite"
    )


def test_the_web_face_does_not_recompute_the_write_flag() -> None:
    """M8-T308: the Web event must carry the canonical verdict.

    The face recomputed the flag with a narrower list of write tools and
    dropped the canonical one, so a ``sed -i`` looked like "no write"
    there while the agent loop said otherwise.
    """
    source = (
        Path(__file__).resolve().parents[1] / "minicc" / "web.py"
    ).read_text(encoding="utf-8")
    marker = "def on_tool(call: ToolCall, result: ToolResult) -> None:"
    start = source.index(marker)
    branch = source[start:start + 2000]
    assert '"write": bool(feedback.get("write"))' in branch, (
        "the Web face recomputes the write flag instead of carrying the "
        "canonical one"
    )


# --- M8-T309: the log and the model context see the same text ------------------


@pytest.mark.parametrize(
    "text",
    [
        "self.token = compute()",
        "config.key = value",
        'x = {"key": "value"}',
        "password = read_from_env()",
    ],
)
def test_the_model_context_leaves_ordinary_code_alone(text: str) -> None:
    """The agent must read the code as it is on disk."""
    model_side, _changed = redact_text(text)
    assert model_side == text, f"the model context rewrote the code: {model_side!r}"


def test_the_log_masks_a_credential_wherever_it_is() -> None:
    """The log is a record of what ran: it masks every labelled value.

    It may be **stricter** than the model context (which leaves ordinary
    source readable so the agent edits the real file), but it must not be
    looser - a short value or one with code punctuation is still a value
    that landed in a log file.
    """
    for raw, needle in (
        ('{"api_key": "abcd1234efgh5678"}', "abcd1234efgh5678"),
        ("password=abc", "abc"),
        ("api_key=a(b", "a(b"),
        ("token=x", "x"),
    ):
        masked = redact(raw)
        assert needle not in masked, (
            f"the log left {needle!r} in {raw!r}: {masked!r}"
        )


def test_the_log_still_masks_a_credential() -> None:
    """The control: the log's job is unchanged."""
    masked = redact('{"api_key": "abcd1234efgh5678"}')
    assert "abcd1234efgh5678" not in masked


# --- M8-T310: one file, one row -----------------------------------------------


def test_a_file_appears_once_in_the_change_list(tmp_path: Path) -> None:
    """The audit records the raw spelling; git records the clean path."""
    workspace = _repo(tmp_path / "ws")
    (workspace / "notes.md").write_text("# demo\n", encoding="utf-8")
    _git(workspace, "add", "-A")
    _git(workspace, "commit", "-m", "init")

    editor = Editor(workspace, audit_path=workspace / ".minicc" / "audit.jsonl")
    editor.write_file("sub/../notes.md", "# changed\n")

    summary = ChangeInspector(workspace).summary()
    paths = [item["path"] for item in summary["files"]]
    # The two spellings name the same file, so the comparison has to be on
    # the resolved path - the raw strings differ.
    resolved = [(workspace / path).resolve() for path in paths]
    assert len(resolved) == len(set(resolved)), (
        f"the same file appears twice: {paths}"
    )
    assert summary["total_files"] == len(paths)


# --- M8-T311: the skip rule has one meaning ------------------------------------


def test_a_plain_file_named_like_a_build_artefact_is_visible_everywhere(
    tmp_path: Path,
) -> None:
    """glob, grep, the tree tool and the panel must agree."""
    from minicc.tools import build_registry
    from minicc.tools.editor import Editor as ToolsEditor
    from minicc.tools.schemas import ToolCall

    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "build").write_text("not a directory\n", encoding="utf-8")
    (workspace / "keep.py").write_text("x = 1\n", encoding="utf-8")

    registry = build_registry(ToolsEditor(workspace))
    globbed = registry.execute(ToolCall(
        tool="glob", arguments={"pattern": "**/*"}, call_id="c1"
    ))
    assert "build" in globbed.render(), "glob does not show the file"

    treed = registry.execute(ToolCall(
        tool="tree", arguments={"path": "."}, call_id="c2"
    ))
    assert "build" in treed.render(), (
        "the tree tool hides a plain file that glob shows"
    )


def test_a_directory_named_like_a_build_artefact_is_still_hidden(tmp_path: Path) -> None:
    """The control: the rule is about directories, not names."""
    from minicc.tools import build_registry
    from minicc.tools.editor import Editor as ToolsEditor
    from minicc.tools.schemas import ToolCall

    workspace = tmp_path / "ws"
    (workspace / "build").mkdir(parents=True)
    (workspace / "build" / "x.py").write_text("x = 1\n", encoding="utf-8")

    registry = build_registry(ToolsEditor(workspace))
    treed = registry.execute(ToolCall(
        tool="tree", arguments={"path": "."}, call_id="c1"
    ))
    assert "build" not in treed.render(), "a build directory is still hidden"


# --- M8-T312: the audit window is disclosed ------------------------------------


def test_the_audit_window_truncation_is_disclosed(tmp_path: Path) -> None:
    """A change pushed out of the window must not silently disappear."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    editor = Editor(workspace, audit_path=workspace / ".minicc" / "audit.jsonl")
    editor.write_file("a.py", "x = 1\n")
    for _ in range(600):
        editor.read_file("a.py")

    summary = ChangeInspector(workspace).summary()
    assert summary.get("audit_window_truncated") is True, (
        "the audit window dropped entries and said nothing"
    )
