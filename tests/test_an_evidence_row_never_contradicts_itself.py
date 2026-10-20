"""M8-T331 — 证据链里不能有"自相矛盾"的一行，也不能有裸异常

复核在我这批的改动里抓到的两处：

* **聚合退出码把"没有结论"写成 0**。`0` 在证据链里的意思是"命令成功"，
  而同一条记录的状态写着 `blocked`、提示写着"验证命令不在只读白名单中"——
  交给裁决 LLM 的这一行**自相矛盾**，而 LLM 很可能读成"这条检查跑过了且
  成功"。没有结论就是没有结论，值应当是 `None`。
* **协议校验器抛的是裸 `AttributeError`**。`tool_round_walk` 容忍"不是对象的
  消息"，校验器却直接对它 `.get(...)`——而这个函数的承诺是"在网络 I/O 之前
  拒掉非法轮次"，`AttributeError` 不是任何人会**故意**去接的拒绝。

本门禁钉住这两条。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from minicc.agent.context import validate_tool_protocol
from minicc.agent.verification_plan import VerificationCommand, VerificationPlan
from minicc.agent.verifier import Verifier
from minicc.tools.schemas import ToolResult


def test_a_blocked_check_does_not_report_a_successful_exit_code(tmp_path: Path) -> None:
    """``0`` means success; a blocked check has no conclusion at all.

    Two blocked checks, so the **aggregate** is the thing under test (a
    single command returns its own result, which already carries no exit
    code).
    """
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "app.py").write_text("x = 1\n", encoding="utf-8")

    def executor(command: str, ws: Path, timeout: int) -> ToolResult:
        return ToolResult(status="ok", summary="ok", exit_code=0)

    verifier = Verifier(executor=executor)
    plan = VerificationPlan(
        commands=[
            VerificationCommand(command="rm -rf /", label="blocked-1"),
            VerificationCommand(command="chmod -R 777 /", label="blocked-2"),
        ],
        changed_paths=["app.py"],
        fingerprint="",
    )
    result = verifier.run(workspace, plan=plan)
    assert result.status == "blocked", result.to_dict()
    assert result.exit_code is None, (
        f"a blocked check reported an exit code: {result.to_dict()}"
    )


def test_a_failed_check_still_reports_its_real_exit_code(tmp_path: Path) -> None:
    """The control: a real failure keeps its real code."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "app.py").write_text("x = 1\n", encoding="utf-8")

    def executor(command: str, ws: Path, timeout: int) -> ToolResult:
        return ToolResult(status="error", summary="failed", exit_code=1, output="1 failed")

    verifier = Verifier(executor=executor)
    plan = VerificationPlan(
        commands=[VerificationCommand(command="python -m pytest -q", label="pytest")],
        changed_paths=["app.py"],
        fingerprint="",
    )
    result = verifier.run(workspace, plan=plan)
    assert result.status == "failed", result.to_dict()
    assert result.exit_code == 1, result.to_dict()


def test_a_malformed_message_is_rejected_with_a_value_error() -> None:
    """The validator promises ``ValueError``, not an ``AttributeError``."""
    with pytest.raises(ValueError):
        validate_tool_protocol(["not a message"])  # type: ignore[list-item]


def test_a_valid_history_is_still_accepted() -> None:
    """The control: the ordinary case is unchanged."""
    validate_tool_protocol([
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "read_file", "arguments": "{}"}},
        ]},
        {"role": "tool", "tool_call_id": "c1", "content": "ok"},
        {"role": "assistant", "content": "done"},
    ])
