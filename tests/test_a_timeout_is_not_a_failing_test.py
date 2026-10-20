"""M8-T300 — 超时不是"测试失败"

验证命令跑超时了，`run_process` 返回 `status="timed_out"`。而验证结果的状态
集合里**没有**这一档，于是它掉进了 "failed"：

* 提示退化成通用的"查看验证输出，修复后重新运行同一命令"；
* Web 层把"failed"送进 **repair 循环**——模型被派去修一个**根本没失败**
  的命令，于是反复重跑直到 repair 上限。

本门禁钉住：超时有自己的状态、自己的提示，而且**不进 repair 循环**。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from minicc.agent.verifier import Verifier
from minicc.agent.verification_plan import VerificationCommand, VerificationPlan
from minicc.tools.schemas import ToolResult


def _plan() -> VerificationPlan:
    return VerificationPlan(
        commands=[VerificationCommand(command="pytest -q", label="pytest")],
        changed_paths=["app.py"],
        fingerprint="",
    )


def _timed_out_executor(command: str, workspace: Path, timeout: int) -> ToolResult:
    return ToolResult(
        status="timed_out",
        summary="[TIMED_OUT] 命令超时",
        exit_code=-9,
        output="",
    )


def test_a_timeout_is_not_reported_as_a_failure(tmp_path: Path) -> None:
    """The status enum had no room for it, so it fell into "failed"."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "app.py").write_text("x = 1\n", encoding="utf-8")

    verifier = Verifier(executor=_timed_out_executor)
    result = verifier.run(workspace, plan=_plan())

    assert result.status == "timed_out", result.to_dict()
    assert "超时" in result.actionable_hint, result.actionable_hint


def test_a_timeout_does_not_ask_the_model_to_repair_a_command(tmp_path: Path) -> None:
    """The hint must not say "fix the failing test"."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "app.py").write_text("x = 1\n", encoding="utf-8")

    verifier = Verifier(executor=_timed_out_executor)
    result = verifier.run(workspace, plan=_plan())

    assert "修复" not in result.actionable_hint, result.actionable_hint
    assert "失败测试" not in result.actionable_hint, result.actionable_hint


def test_a_real_failure_is_still_a_failure(tmp_path: Path) -> None:
    """The control: the ordinary path is unchanged."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "app.py").write_text("x = 1\n", encoding="utf-8")

    def failing(command: str, ws: Path, timeout: int) -> ToolResult:
        return ToolResult(status="error", summary="failed", exit_code=1, output="1 failed")

    verifier = Verifier(executor=failing)
    result = verifier.run(workspace, plan=_plan())
    assert result.status == "failed", result.to_dict()


def test_a_passing_run_is_still_passing(tmp_path: Path) -> None:
    """The control: the ordinary path is unchanged."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "app.py").write_text("x = 1\n", encoding="utf-8")

    def passing(command: str, ws: Path, timeout: int) -> ToolResult:
        return ToolResult(status="ok", summary="ok", exit_code=0, output="1 passed")

    verifier = Verifier(executor=passing)
    result = verifier.run(workspace, plan=_plan())
    assert result.status == "passed", result.to_dict()


def test_the_aggregated_exit_code_is_the_real_one(tmp_path: Path) -> None:
    """A blocked check carries no exit code, and it must not replace the real one.

    The aggregate used to take the **first** failure's exit code - and a
    blocked or cancelled check has ``None`` - so the real failure's code
    (1) never reached the evidence chain.
    """
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "app.py").write_text("x = 1\n", encoding="utf-8")

    calls = {"count": 0}

    def mixed(command: str, ws: Path, timeout: int) -> ToolResult:
        calls["count"] += 1
        if calls["count"] == 1:
            return ToolResult(status="error", summary="blocked", exit_code=None)
        return ToolResult(status="error", summary="failed", exit_code=1, output="1 failed")

    verifier = Verifier(executor=mixed)
    plan = VerificationPlan(
        commands=[
            VerificationCommand(command="python -m pytest -q", label="first"),
            VerificationCommand(command="python -m pytest -q tests/", label="second"),
        ],
        changed_paths=["app.py"],
        fingerprint="",
    )
    result = verifier.run(workspace, plan=plan)
    assert result.exit_code == 1, (
        f"the real exit code was replaced: {result.to_dict()}"
    )
