"""Deterministic, whitelist-based verification for coding tasks."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..tools.bash import is_readonly_command, run_bash
from ..tools.schemas import ToolResult


FAILED_TEST_RE = re.compile(r"(?m)^FAILED\s+([^\s]+)")


@dataclass(frozen=True)
class VerificationCommand:
    command: str
    label: str = "pytest"
    timeout: int = 120


@dataclass
class VerificationResult:
    status: str
    command: str = ""
    label: str = ""
    exit_code: int | None = None
    output: str = ""
    failed_tests: list[str] = field(default_factory=list)
    actionable_hint: str = ""
    duration_seconds: float = 0.0
    skipped_reason: str | None = None

    @property
    def passed(self) -> bool:
        return self.status == "passed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "command": self.command,
            "label": self.label,
            "exit_code": self.exit_code,
            "output": self.output,
            "failed_tests": list(self.failed_tests),
            "actionable_hint": self.actionable_hint,
            "duration_seconds": round(self.duration_seconds, 3),
            "skipped_reason": self.skipped_reason,
        }

    def to_event(self) -> dict[str, Any]:
        status = "ok" if self.status == "passed" else "error" if self.status == "failed" else "ok"
        code = {
            "passed": "verification_passed",
            "failed": "verification_failed",
            "skipped": "verification_skipped",
            "blocked": "verification_blocked",
        }.get(self.status, "verification_finished")
        summary = {
            "passed": f"验证通过: {self.command}",
            "failed": f"验证失败: {self.command}",
            "skipped": f"验证跳过: {self.skipped_reason or '没有可用验证命令'}",
            "blocked": f"验证被阻止: {self.actionable_hint or self.command}",
        }.get(self.status, f"验证结束: {self.command}")
        return {
            "kind": "verification",
            "name": "verifier",
            "phase": "verify",
            "status": status,
            "code": code,
            "summary": summary,
            "command": self.command,
            "write": False,
            "detail": self.to_dict(),
        }


Executor = Callable[[str, Path, int], ToolResult]


class Verifier:
    """Run only approved local verification commands and normalize their output."""

    def __init__(self, executor: Executor = run_bash) -> None:
        self.executor = executor

    @staticmethod
    def default_commands(workspace: Path) -> list[VerificationCommand]:
        if (workspace / "tests").is_dir() or any(workspace.glob("test_*.py")):
            return [VerificationCommand("python -m pytest -q")]
        return []

    @staticmethod
    def _validate(command: VerificationCommand) -> str | None:
        if command.timeout < 1:
            return "验证超时必须至少为 1 秒"
        if not is_readonly_command(command.command):
            return "验证命令不在只读白名单中"
        return None

    def run(
        self,
        workspace: Path,
        commands: list[VerificationCommand] | None = None,
    ) -> VerificationResult:
        selected = list(commands) if commands is not None else self.default_commands(workspace)
        if not selected:
            return VerificationResult(status="skipped", skipped_reason="工作区没有配置可识别的验证命令")
        command = selected[0]
        invalid = self._validate(command)
        if invalid:
            return VerificationResult(
                status="blocked",
                command=command.command,
                label=command.label,
                actionable_hint=invalid,
            )
        started = time.monotonic()
        tool_result = self.executor(command.command, workspace, command.timeout)
        output = tool_result.render()
        failed_tests = FAILED_TEST_RE.findall(output)
        status = "passed" if tool_result.status == "ok" and tool_result.exit_code in (None, 0) else "failed"
        hint = ""
        if status == "failed":
            hint = (
                f"先修复失败测试: {', '.join(failed_tests[:8])}"
                if failed_tests
                else "查看验证输出，修复后重新运行同一命令"
            )
        return VerificationResult(
            status=status,
            command=command.command,
            label=command.label,
            exit_code=tool_result.exit_code,
            output=output,
            failed_tests=failed_tests,
            actionable_hint=hint,
            duration_seconds=time.monotonic() - started,
        )


__all__ = ["VerificationCommand", "VerificationResult", "Verifier"]
