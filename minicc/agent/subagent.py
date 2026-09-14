"""Bounded Task subagent tool: one-shot readonly research sub-runs.

Aligned with Claude Code's Task tool but deliberately narrower (see
docs/AGENT_LLM_ROADMAP.md: experts are only justified by distinct
constraints, never for demos):

- the subagent sees a *restricted registry* (readonly evidence tools only —
  no write/exec/bash/network, and no ``task`` tool, so recursion is
  structurally impossible);
- each run has its own turn budget and wall-clock timeout inside the parent's
  single tool call, so the parent keeps control of cost and cancellation;
- the sub-loop runs in a worker thread with its own event loop, because tool
  handlers execute synchronously inside the parent's running loop;
- a module-level semaphore bounds concurrent subagents per process;
- results come back as an untrusted ToolResult with a bounded tool log — the
  parent never receives the child's raw transcript.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import threading
import time
from pathlib import Path
from typing import Any, Callable

from .loop import AgentCancelled, Budget, run_agent
from ..tools.registry import ToolError, ToolRegistry, ToolSpec
from ..tools.schemas import ToolResult

SUBAGENT_TOOL_NAME = "task"
# Readonly evidence tools only. No network (parent research stays in the
# parent loop), no todo_write (todos.json is shared parent/child state),
# and crucially no "task" — a subagent cannot spawn subagents.
SUBAGENT_TOOLS = frozenset({
    "read_file", "glob", "grep", "tree", "git_status", "git_diff",
    "git_summary", "git_merge_precheck",
})
DEFAULT_MAX_TURNS = 24
DEFAULT_TIMEOUT_SECONDS = 600.0
MAX_CONCURRENT_SUBAGENTS = 3
MAX_TOOL_LOG_ENTRIES = 32
_TOOL_LOG = ("tool", "summary")

_SUBAGENT_SLOTS = threading.BoundedSemaphore(MAX_CONCURRENT_SUBAGENTS)

TaskToolProviderFactory = Callable[[], Any]


def build_task_tool_spec(
    *,
    provider_factory: TaskToolProviderFactory,
    workspace: Path,
    system_prompt: str,
    base_registry: ToolRegistry,
    max_turns: int = DEFAULT_MAX_TURNS,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    cancel_event: threading.Event | None = None,
) -> ToolSpec:
    """Create the ``task`` ToolSpec bound to one parent task's context."""
    runner = _SubagentRunner(
        provider_factory=provider_factory,
        workspace=Path(workspace),
        system_prompt=system_prompt,
        base_registry=base_registry,
        max_turns=max(1, int(max_turns)),
        timeout_seconds=max(5.0, float(timeout_seconds)),
        cancel_event=cancel_event,
    )
    return ToolSpec(
        SUBAGENT_TOOL_NAME,
        (
            "派生一个受限的只读侦察子代理并等待其完成（独立上下文，不会继承本对话历史）。"
            "适用：大范围代码调研、多目录排查、需要一次性集中阅读的场景。"
            "子代理只有只读工具，不能写文件、不能执行命令、不能联网，也不能再派生子代理。"
            "description 写一行目标，prompt 写完整自包含的任务说明。"
        ),
        "readonly",
        (),
        runner.run,
        input_schema={
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "minLength": 4,
                    "maxLength": 120,
                    "description": "子代理目标的一句话概括",
                },
                "prompt": {
                    "type": "string",
                    "minLength": 8,
                    "maxLength": 8000,
                    "description": "给子代理的完整自包含任务说明（结论要求、检查范围、输出格式）",
                },
            },
            "required": ["description", "prompt"],
        },
    )


class _SubagentRunner:
    def __init__(
        self,
        *,
        provider_factory: TaskToolProviderFactory,
        workspace: Path,
        system_prompt: str,
        base_registry: ToolRegistry,
        max_turns: int,
        timeout_seconds: float,
        cancel_event: threading.Event | None,
    ) -> None:
        self.provider_factory = provider_factory
        self.workspace = workspace
        self.system_prompt = system_prompt
        self.base_registry = base_registry
        self.max_turns = max_turns
        self.timeout_seconds = timeout_seconds
        self.cancel_event = cancel_event

    def run(self, args: dict[str, Any]) -> ToolResult:
        description = str(args.get("description") or "").strip()
        prompt = str(args.get("prompt") or "").strip()
        if len(description) < 4:
            raise ToolError("description 至少 4 个字符")
        if len(prompt) < 8:
            raise ToolError("prompt 至少 8 个字符")
        if not _SUBAGENT_SLOTS.acquire(timeout=1.0):
            raise ToolError(
                f"子代理并发已达上限（{MAX_CONCURRENT_SUBAGENTS}），请等当前侦察完成或改为直接使用只读工具。"
            )
        try:
            return self._run_bounded(description, prompt)
        finally:
            _SUBAGENT_SLOTS.release()

    def _run_bounded(self, description: str, prompt: str) -> ToolResult:
        tool_log: list[dict[str, str]] = []

        def on_tool(call: Any, result: ToolResult) -> None:
            if len(tool_log) < MAX_TOOL_LOG_ENTRIES:
                tool_log.append({
                    "tool": str(call.tool),
                    "summary": str(result.summary or "")[:200],
                })

        child_registry = self.base_registry.restrict(SUBAGENT_TOOLS)
        messages = [
            {"role": "system", "content": (
                f"{self.system_prompt}\n\n"
                "[子代理模式] 你是父任务派生的只读侦察子代理。只做调查与求证，"
                "不能修改文件或执行命令；回答要给出文件路径、行号/命令证据和明确结论。"
            )},
            {"role": "user", "content": prompt},
        ]
        child_cancel = threading.Event()
        parent_cancel = self.cancel_event

        future: concurrent.futures.Future[Any] = concurrent.futures.Future()

        def worker() -> None:
            async def execute() -> Any:
                provider = self.provider_factory()
                try:
                    return await run_agent(
                        provider,
                        child_registry,
                        messages,
                        budget=Budget(max_turns=self.max_turns),
                        on_tool=on_tool,
                        cancel_event=child_cancel,
                        should_cancel=(lambda: bool(parent_cancel and parent_cancel.is_set())),
                    )
                finally:
                    close = getattr(provider, "close", None)
                    if close is not None:
                        try:
                            if asyncio.iscoroutinefunction(close):
                                await close()
                            else:
                                close()
                        except Exception:  # noqa: BLE001 - best-effort cleanup
                            pass

            try:
                future.set_result(asyncio.run(execute()))
            except BaseException as exc:  # noqa: BLE001 - forwarded to parent handler
                future.set_exception(exc)

        started = time.monotonic()
        thread = threading.Thread(target=worker, daemon=True, name="minicc-subagent")
        thread.start()
        try:
            result = future.result(timeout=self.timeout_seconds)
        except concurrent.futures.TimeoutError:
            child_cancel.set()
            thread.join(timeout=15.0)
            return ToolResult(
                status="timed_out",
                summary=f"[TIMEOUT] 子代理超时（>{int(self.timeout_seconds)}s）：{description}",
                output="子代理超时被终止。请缩小调研范围后重试，或直接使用只读工具分步完成。",
                data={"description": description, "tool_log": tool_log, "timed_out": True},
                security_tags=["untrusted", "subagent"],
            )
        except AgentCancelled:
            return ToolResult(
                status="cancelled",
                summary=f"[CANCELLED] 子代理被取消：{description}",
                security_tags=["untrusted", "subagent"],
            )
        duration = time.monotonic() - started
        answer = str(getattr(result, "answer", "") or "")
        usage = dict(getattr(result, "tokens_used", {}) or {})
        head, tail, truncated = _bounded_output(answer)
        summary = (
            f"子代理完成 {description}：{getattr(result, 'turns', 0)} 轮、"
            f"{getattr(result, 'tool_calls_total', len(tool_log))} 次工具调用，用时 {duration:.1f}s"
        )
        parts = [summary, "", answer if not truncated else f"{head}\n…[输出截断]…\n{tail}"]
        return ToolResult(
            status="ok",
            summary=summary,
            output="\n".join(parts)[: 60000],
            head="",
            tail="",
            truncated=truncated,
            duration=duration,
            data={
                "description": description,
                "turns": int(getattr(result, "turns", 0) or 0),
                "tool_calls": int(getattr(result, "tool_calls_total", 0) or 0),
                "tokens_used": usage,
                "tool_log": tool_log,
                "timed_out": False,
            },
            security_tags=["untrusted", "subagent"],
        )


def _bounded_output(text: str, limit: int = 12000) -> tuple[str, str, bool]:
    if len(text) <= limit:
        return text, "", False
    keep = limit // 2
    return text[:keep], text[-keep:], True


__all__ = [
    "DEFAULT_MAX_TURNS",
    "DEFAULT_TIMEOUT_SECONDS",
    "MAX_CONCURRENT_SUBAGENTS",
    "SUBAGENT_TOOLS",
    "SUBAGENT_TOOL_NAME",
    "build_task_tool_spec",
]
