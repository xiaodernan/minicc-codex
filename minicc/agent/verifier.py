"""Deterministic, whitelist-based verification for coding tasks."""

from __future__ import annotations

import re
import time
import threading
import inspect
import math
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from copy import deepcopy

from ..tools.bash import run_bash
from ..tools.schemas import ToolResult
from ..tools.registry import redact_text
from .verification_plan import VerificationCommand, VerificationPlan, build_verification_plan, safe_verification_command, verification_state


FAILED_TEST_RE = re.compile(r"(?m)^FAILED\s+([^\s]+)")


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
    checks: list[dict[str, Any]] = field(default_factory=list)
    cached: bool = False
    fingerprint: str = ""

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
            "checks": self.checks,
            "cached": self.cached,
            "fingerprint": self.fingerprint,
        }

    def to_event(self) -> dict[str, Any]:
        status = "ok" if self.status in {"passed", "skipped"} else "cancelled" if self.status == "cancelled" else "error"
        code = {
            "passed": "verification_passed",
            "failed": "verification_failed",
            "skipped": "verification_skipped",
            "blocked": "verification_blocked",
            "cancelled": "verification_cancelled",
            "timed_out": "verification_timed_out",
        }.get(self.status, "verification_finished")
        summary = {
            "passed": f"验证通过: {self.command}",
            "failed": f"验证失败: {self.command}",
            "skipped": f"验证跳过: {self.skipped_reason or '没有可用验证命令'}",
            "blocked": f"验证被阻止: {self.actionable_hint or self.command}",
            "cancelled": "验证已取消，后续检查未执行",
            "timed_out": f"验证超时: {self.command}",
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
        self._passed: OrderedDict[str, VerificationResult] = OrderedDict()

    @staticmethod
    def default_commands(workspace: Path) -> list[VerificationCommand]:
        return build_verification_plan(workspace).commands

    @staticmethod
    def _validate(command: VerificationCommand, allow_project_scripts: bool = False) -> str | None:
        if not isinstance(command.timeout, (int, float)) or not math.isfinite(command.timeout) or command.timeout < 1:
            return "验证超时必须至少为 1 秒"
        if not safe_verification_command(command.command, allow_project_scripts=allow_project_scripts):
            return "验证命令不在只读白名单中"
        return None

    def run(
        self,
        workspace: Path,
        commands: list[VerificationCommand] | None = None,
        *,
        plan: VerificationPlan | None = None,
        allow_project_scripts: bool = False,
        cancel_event: threading.Event | None = None,
    ) -> VerificationResult:
        if cancel_event is not None and cancel_event.is_set():
            return VerificationResult(status="cancelled")
        selected = list(commands) if commands is not None else (plan.commands if plan else self.default_commands(workspace))
        if not selected:
            return VerificationResult(status="skipped", skipped_reason=plan.reason if plan else "工作区没有配置可识别的验证命令")
        # Authorization is part of the cache key. A permitted npm check must
        # never be replayed as evidence under a task that cannot run it.
        #
        # M8-T294: the identity and its **reusability** are two answers.
        # The old code had one value (``""`` for an untrustworthy scan)
        # and used it for both the cache key and the "the workspace changed
        # during verification" gate - so in a workspace holding a ``.env``
        # file, a symlink, or a file over 2 MB, the gate short-circuited and
        # never ran, and a verification that raced an edit still reported
        # ``passed``.
        current, cacheable = verification_state(workspace, plan.changed_paths, selected) if plan else ("", False)
        if cancel_event is not None and cancel_event.is_set():
            return VerificationResult(status="cancelled")
        fingerprint = f"{current}:{allow_project_scripts}" if current and cacheable else ""
        if fingerprint and fingerprint in self._passed:
            result = deepcopy(self._passed[fingerprint])
            result.cached = True
            result.duration_seconds = 0.0
            return result
        results = []
        for command in selected:
            if cancel_event is not None and cancel_event.is_set():
                results.append(VerificationResult(status="cancelled", command=command.command))
                break
            results.append(self._run_one(workspace, command, allow_project_scripts, cancel_event))
            if results[-1].status == "cancelled":
                break
        if len(results) == 1:
            result = results[0]
        else:
            failures = [item for item in results if item.status != "passed"]
            result = VerificationResult(
                status="cancelled" if any(item.status == "cancelled" for item in failures) else "failed" if any(item.status == "failed" for item in failures) else "timed_out" if any(item.status == "timed_out" for item in failures) else "blocked" if failures else "passed",
                command="\n".join(item.command for item in results), label="verification plan",
                # M8-T331: the aggregated exit code was the **first**
                # failure's - and a blocked or cancelled check carries no
                # exit code at all (``None``), so it replaced the real one
                # (1) in the evidence chain.  The first failure that
                # actually has an exit code wins.
                #
                # And when **no** failure has one, the aggregate used to
                # write ``0`` - which in an evidence chain reads as "the
                # command succeeded", next to a status that says
                # "blocked".  ``None`` is the honest value: no conclusion.
                exit_code=next(
                    (item.exit_code for item in failures if item.exit_code is not None),
                    None,
                ),
                output="\n\n".join(f"[{item.label}] {item.command}\n{item.output}" for item in results)[-32000:],
                failed_tests=[test for item in results for test in item.failed_tests],
                actionable_hint="\n".join(item.actionable_hint for item in failures),
                duration_seconds=sum(item.duration_seconds for item in results),
            )
        checks = [item.to_dict() for item in results]
        result.checks = checks
        result.fingerprint = fingerprint
        if result.passed and current and plan:
            # The gate is independent of reusability: an untrustworthy scan
            # still has a comparable identity, so the workspace moving under
            # the run is still detected.
            after, _after_cacheable = verification_state(
                workspace, plan.changed_paths, selected
            )
            if after != current:
                result.status = "failed"
                result.actionable_hint = "验证期间工作区输入发生变化；请检查改动并重新验证当前版本"
                result.fingerprint = ""
        if cancel_event is not None and cancel_event.is_set():
            result.status = "cancelled"
        if result.passed and fingerprint:
            self._passed[fingerprint] = deepcopy(result)
            while len(self._passed) > 16:
                self._passed.popitem(last=False)
        return result

    def _run_one(self, workspace: Path, command: VerificationCommand, allow_project_scripts: bool, cancel_event: threading.Event | None) -> VerificationResult:
        invalid = self._validate(command, allow_project_scripts)
        if invalid:
            return VerificationResult(
                status="blocked",
                command=command.command,
                label=command.label,
                actionable_hint=invalid,
            )
        started = time.monotonic()
        parameters = inspect.signature(self.executor).parameters
        kwargs = {"cancel_event": cancel_event} if "cancel_event" in parameters else {}
        tool_result = self.executor(command.command, workspace, command.timeout, **kwargs)
        output = redact_text(tool_result.render())[0][-32000:]
        failed_tests = FAILED_TEST_RE.findall(output)
        # M8-T300: a command that ran out of time is **not** a failing test.
        # The status enum had no room for it, so ``timed_out`` fell into
        # "failed" - and the hint degraded to the generic "look at the
        # output, fix it and run it again".  The model was then sent to
        # repair a command that had not failed at all, and the repair loop
        # kept re-running it until the cap.
        if tool_result.status == "cancelled":
            status = "cancelled"
        elif tool_result.status == "timed_out":
            status = "timed_out"
        elif tool_result.status == "ok" and tool_result.exit_code in (None, 0):
            status = "passed"
        else:
            status = "failed"
        hint = ""
        if status == "failed":
            hint = (
                f"先修复失败测试: {', '.join(failed_tests[:8])}"
                if failed_tests
                else "查看验证输出，修复后重新运行同一命令"
            )
        elif status == "timed_out":
            hint = (
                f"验证命令超时（{command.timeout}s）被终止，没有产生测试结论；"
                "请缩小检查范围或提高超时后再验证，不要把它当成测试失败"
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
