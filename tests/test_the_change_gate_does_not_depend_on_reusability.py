"""M8-T294 — 「指纹不可信」与「指纹不可比较」是两件事

`verification_fingerprint` 用**返回空串**表达"这次扫描不可信、不能复用缓存"。
而验证器把同一个值当成了两件事的开关：

* **缓存键** —— 不可信就不许复用（这是本意：密钥输入没有被读进来，所以检测不到它的变化）；
* **「验证期间工作区变了」这道闸** —— 而空串让这道闸**整条短路**，从未执行过。

于是任何持有 `.env`（本仓库根目录就有一个）、符号链接或超过 2MB 文件的工作区里，
一次"跑着跑着工作区被人改了"的验证仍然报 ``passed`` —— 证据链认证了一个
已经不存在的状态。

本门禁钉住：闸门与可复用性**分开**；可信工作区的行为不变。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from minicc.agent.verifier import Verifier
from minicc.agent.verification_plan import (
    VerificationCommand,
    VerificationPlan,
    verification_state,
)
from minicc.tools.schemas import ToolResult


def _plan() -> VerificationPlan:
    return VerificationPlan(
        commands=[VerificationCommand(command="pytest -q", label="pytest")],
        changed_paths=["app.py"],
        fingerprint="",
    )


def _mutating_executor(workspace: Path):
    def executor(command: str, ws: Path, timeout: int) -> ToolResult:
        # The workspace moves while the check is running.
        (ws / "app.py").write_text("x = 2\n", encoding="utf-8")
        return ToolResult(status="ok", summary="ok", exit_code=0)

    return executor


def test_the_change_gate_runs_in_a_workspace_with_a_secret_file(tmp_path: Path) -> None:
    """The gate must not be switched off by an untrustworthy scan."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / ".env").write_text("SECRET=1\n", encoding="utf-8")
    (workspace / "app.py").write_text("x = 1\n", encoding="utf-8")

    verifier = Verifier(executor=_mutating_executor(workspace))
    result = verifier.run(workspace, plan=_plan())

    assert result.status == "failed", (
        f"the workspace changed during the verification and it still passed: {result.to_dict()}"
    )
    assert "发生变化" in result.actionable_hint, result.actionable_hint


def test_the_change_gate_runs_in_a_plain_workspace_too(tmp_path: Path) -> None:
    """The control: the trusted case behaved this way all along."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "app.py").write_text("x = 1\n", encoding="utf-8")

    verifier = Verifier(executor=_mutating_executor(workspace))
    result = verifier.run(workspace, plan=_plan())

    assert result.status == "failed"
    assert "发生变化" in result.actionable_hint


def test_an_unchanged_workspace_still_passes(tmp_path: Path) -> None:
    """The control: nothing moved, so the run passes."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / ".env").write_text("SECRET=1\n", encoding="utf-8")
    (workspace / "app.py").write_text("x = 1\n", encoding="utf-8")

    def executor(command: str, ws: Path, timeout: int) -> ToolResult:
        return ToolResult(status="ok", summary="ok", exit_code=0)

    verifier = Verifier(executor=executor)
    result = verifier.run(workspace, plan=_plan())
    assert result.status == "passed", result.to_dict()


def test_an_untrustworthy_scan_is_still_not_reusable_as_a_cache_key(
    tmp_path: Path,
) -> None:
    """The other half: "not trustworthy" still means "do not replay a pass"."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / ".env").write_text("SECRET=1\n", encoding="utf-8")
    (workspace / "app.py").write_text("x = 1\n", encoding="utf-8")

    digest, cacheable = verification_state(workspace, ["app.py"], _plan().commands)
    assert digest, "the identity must still be comparable"
    assert cacheable is False, (
        "a workspace with a secret input must not be reusable as a cache key"
    )
