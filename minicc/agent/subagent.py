"""Bounded Task subagent tool: one-shot research (and, opt-in, delegation) runs.

Aligned with Claude Code's Task tool but deliberately narrower (see
docs/AGENT_LLM_ROADMAP.md: experts are only justified by distinct
constraints, never for demos):

- the subagent sees a *restricted registry* chosen by a tier (M6-T1): the
  default ``readonly`` evidence set, or — only when the server enables
  ``subagent_writable`` AND the session's permission_mode already auto-accepts
  edits — a ``write`` (adds write_file/edit_file) or ``exec`` (adds bash) tier.
  No tier exposes network tools, and ``task`` is never part of a tier;
- depth is bounded (default 2): a writable child may spawn one grandchild, but
  the depth-2 grandchild is structurally denied the ``task`` tool, so a 3rd
  level — unbounded recursive multi-agent — is impossible;
- each run has its own turn/token/wall-clock budget inside the parent's single
  tool call, so the parent keeps control of cost and cancellation, and a child
  that exhausts its budget ends as a structured failure rather than taking the
  parent down;
- the sub-loop runs in a worker thread with its own event loop, because tool
  handlers execute synchronously inside the parent's running loop;
- the parent waits on the child with bounded polling (M6-T2) instead of one
  blocking ``future.result(600)``, so it can honor cancellation promptly and
  bubble the child's trace events to its own sink as ``parent_id``-tagged
  progress rather than running blind;
- a module-level semaphore bounds concurrent subagents per process;
- results come back as an untrusted ToolResult with a bounded tool log — the
  parent never receives the child's raw transcript, and must re-verify output.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from .loop import AgentCancelled, Budget, run_agent
from .state import BudgetExceeded
from ..logging_setup import quiet_loop_teardown
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
# M6-T1: layered tool tiers for bounded writable delegation. Each tier is a
# strict superset of the one before it; ``task`` is NEVER part of a tier (it is
# added separately, depth-gated, so unbounded recursion stays structurally
# impossible). No tier grants network tools.
WRITE_TOOLS = SUBAGENT_TOOLS | frozenset({"write_file", "edit_file"})
EXEC_TOOLS = WRITE_TOOLS | frozenset({"bash"})
SUBAGENT_TOOL_TIERS = {
    "readonly": SUBAGENT_TOOLS,
    "write": WRITE_TOOLS,
    "exec": EXEC_TOOLS,
}
# Permission modes that authorize a subagent to write without an interactive
# approval prompt (a subagent cannot prompt the user mid-run).
WRITABLE_PERMISSION_MODES = frozenset({"acceptEdits", "yolo", "bypassPermissions"})
EXEC_PERMISSION_MODES = frozenset({"yolo", "bypassPermissions"})
DEFAULT_MAX_TURNS = 24
DEFAULT_TIMEOUT_SECONDS = 600.0
MAX_CONCURRENT_SUBAGENTS = 3
MAX_TOOL_LOG_ENTRIES = 32
#: Parent runs at depth 0; a subagent runs at depth 1; with MAX_DEPTH 2 a
#: writable subagent may spawn one grandchild (depth 2) but that grandchild
#: gets no ``task`` tool, so depth 3 is structurally unreachable.
DEFAULT_MAX_DEPTH = 2
#: M6-T2: the parent waits on the child with bounded polling slices so it can
#: observe progress and honor cancellation instead of blocking on a single
#: 600s ``future.result``.
WAIT_POLL_SECONDS = 0.25
PROGRESS_EMIT_SECONDS = 5.0
_TOOL_LOG = ("tool", "summary")

_SUBAGENT_SLOTS = threading.BoundedSemaphore(MAX_CONCURRENT_SUBAGENTS)

TaskToolProviderFactory = Callable[[], Any]


def resolve_subagent_tier(*, writable: bool, permission_mode: str) -> str:
    """Pick the tool tier a subagent may use (M6-T1).

    Writable delegation is opt-in (``writable``) AND only honored inside a
    session whose ``permission_mode`` already auto-accepts edits — a subagent
    cannot ask the user for approval mid-run. ``exec`` (bash) requires the
    explicitly-authorized yolo/bypass modes; everything else stays readonly.
    """
    mode = str(permission_mode or "default")
    if not writable or mode not in WRITABLE_PERMISSION_MODES:
        return "readonly"
    if mode in EXEC_PERMISSION_MODES:
        return "exec"
    return "write"


def build_task_tool_spec(
    *,
    provider_factory: TaskToolProviderFactory,
    workspace: Path,
    system_prompt: str,
    base_registry: ToolRegistry,
    max_turns: int = DEFAULT_MAX_TURNS,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    cancel_event: threading.Event | None = None,
    depth: int = 0,
    max_depth: int = DEFAULT_MAX_DEPTH,
    writable: bool = False,
    permission_mode: str = "default",
    allow_network: bool = False,
    max_tokens: int | None = None,
    soft_max_tokens: int | None = None,
    soft_max_duration_seconds: float | None = None,
    on_trace: Callable[[dict[str, Any]], None] | None = None,
    parent_trace_id: str | None = None,
) -> ToolSpec:
    """Create the ``task`` ToolSpec bound to one parent task's context.

    M6-T1: ``writable`` (config-gated, default off) plus the session's
    ``permission_mode`` select a readonly / write / exec tool tier. ``depth``
    bounds nesting: a writable subagent may spawn one deeper level until
    ``max_depth``, after which the ``task`` tool is structurally absent.

    M6-T2: ``on_trace`` is the parent's event sink (web SSE / CLI). The runner
    bubbles the child's own trace events to it, each tagged with the subagent
    run id as ``parent_id`` and its ``depth``, so the parent UI can show what
    the subagent is doing without ever seeing the raw transcript.
    """
    tier = resolve_subagent_tier(writable=writable, permission_mode=permission_mode)
    runner = _SubagentRunner(
        provider_factory=provider_factory,
        workspace=Path(workspace),
        system_prompt=system_prompt,
        base_registry=base_registry,
        max_turns=max(1, int(max_turns)),
        timeout_seconds=max(5.0, float(timeout_seconds)),
        cancel_event=cancel_event,
        depth=max(0, int(depth)),
        max_depth=max(1, int(max_depth)),
        tier=tier,
        permission_mode=str(permission_mode or "default"),
        allow_network=bool(allow_network),
        max_tokens=max_tokens,
        soft_max_tokens=soft_max_tokens,
        soft_max_duration_seconds=soft_max_duration_seconds,
        on_trace=on_trace,
        parent_trace_id=parent_trace_id,
    )
    if tier == "readonly":
        capability = (
            "子代理只有只读工具，不能写文件、不能执行命令、不能联网，也不能再派生子代理。"
        )
    elif tier == "write":
        capability = (
            "子代理可读写文件（write_file/edit_file），但不能执行命令、不能联网；"
            "其产出按不可信结果回传，父任务必须自行复核。"
        )
    else:
        capability = (
            "子代理可读写文件并执行命令（bash），但不能联网；"
            "其产出按不可信结果回传，父任务必须自行复核。"
        )
    return ToolSpec(
        SUBAGENT_TOOL_NAME,
        (
            "派生一个受限子代理并等待其完成（独立上下文，不会继承本对话历史）。"
            "适用：大范围代码调研、多目录排查、需要一次性集中阅读的场景，"
            "或在已授权写入的会话里把一块边界清晰、互不重叠的改造委派出去。"
            + capability
            + "description 写一行目标，prompt 写完整自包含的任务说明。"
        ),
        "readonly" if tier == "readonly" else "write",
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
        depth: int = 0,
        max_depth: int = DEFAULT_MAX_DEPTH,
        tier: str = "readonly",
        permission_mode: str = "default",
        allow_network: bool = False,
        max_tokens: int | None = None,
        soft_max_tokens: int | None = None,
        soft_max_duration_seconds: float | None = None,
        on_trace: Callable[[dict[str, Any]], None] | None = None,
        parent_trace_id: str | None = None,
    ) -> None:
        self.provider_factory = provider_factory
        self.workspace = workspace
        self.system_prompt = system_prompt
        self.base_registry = base_registry
        self.max_turns = max_turns
        self.timeout_seconds = timeout_seconds
        self.cancel_event = cancel_event
        self.depth = depth
        self.max_depth = max_depth
        self.tier = tier if tier in SUBAGENT_TOOL_TIERS else "readonly"
        self.permission_mode = permission_mode
        self.allow_network = allow_network
        self.max_tokens = max_tokens
        self.soft_max_tokens = soft_max_tokens
        self.soft_max_duration_seconds = soft_max_duration_seconds
        self.on_trace = on_trace
        self.parent_trace_id = parent_trace_id
        # Set at the start of each run so nested task specs can attribute
        # grandchild traces to this run's id.
        self._run_id = ""

    def _emit(self, event: dict[str, Any]) -> None:
        """Forward one structured event to the parent sink, never raising.

        Subagent progress is best-effort telemetry: a failure in the parent's
        callback must not abort the child run.
        """
        if self.on_trace is None:
            return
        try:
            self.on_trace(event)
        except Exception:  # noqa: BLE001 - telemetry must not break the run
            pass

    def _child_registry(self) -> ToolRegistry:
        """Restrict to this runner's tier; depth-gate a nested ``task`` tool.

        A child runs at ``depth + 1``. It may itself spawn (i.e. carry a nested
        ``task`` tool) only when ``depth + 2 <= max_depth`` AND the tier is
        writable — so with ``max_depth == 2`` a depth-2 grandchild has no
        ``task`` tool and depth 3 is structurally impossible. The readonly
        reconnaissance tier never carries ``task``.
        """
        registry = self.base_registry.restrict(SUBAGENT_TOOL_TIERS[self.tier])
        can_delegate = self.tier != "readonly" and (self.depth + 2) <= self.max_depth
        if can_delegate:
            registry.register(build_task_tool_spec(
                provider_factory=self.provider_factory,
                workspace=self.workspace,
                system_prompt=self.system_prompt,
                base_registry=self.base_registry,
                max_turns=self.max_turns,
                timeout_seconds=self.timeout_seconds,
                cancel_event=self.cancel_event,
                depth=self.depth + 1,
                max_depth=self.max_depth,
                writable=True,
                permission_mode=self.permission_mode,
                allow_network=self.allow_network,
                max_tokens=self.max_tokens,
                soft_max_tokens=self.soft_max_tokens,
                soft_max_duration_seconds=self.soft_max_duration_seconds,
                on_trace=self.on_trace,
                parent_trace_id=self._run_id or None,
            ))
        return registry

    def _child_budget(self) -> Budget:
        return Budget(
            max_turns=self.max_turns,
            max_tokens=self.max_tokens,
            soft_max_tokens=self.soft_max_tokens,
            soft_max_duration_seconds=self.soft_max_duration_seconds,
        )

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
        self._run_id = f"sub-{uuid.uuid4().hex[:10]}"
        run_id = self._run_id

        def on_tool(call: Any, result: ToolResult) -> None:
            if len(tool_log) < MAX_TOOL_LOG_ENTRIES:
                tool_log.append({
                    "tool": str(call.tool),
                    "summary": str(result.summary or "")[:200],
                })

        def lifecycle(code: str, status: str, summary: str, **detail: Any) -> None:
            self._emit({
                "kind": "trace",
                "name": "subagent",
                "status": status,
                "phase": "execution",
                "code": code,
                "summary": summary,
                "parent_id": run_id,
                "subagent": True,
                "depth": self.depth + 1,
                "detail": {
                    "description": description,
                    "tier": self.tier,
                    "tool_calls": len(tool_log),
                    **detail,
                },
            })

        def bubble(event: dict[str, Any]) -> None:
            # M6-T2: forward the child's own trace/tool events to the parent
            # sink, tagged so the UI can group them under this subagent run.
            tagged = dict(event)
            tagged["parent_id"] = run_id
            tagged["subagent"] = True
            tagged["depth"] = self.depth + 1
            self._emit(tagged)

        child_registry = self._child_registry()
        mode_note = {
            "readonly": (
                "[子代理模式] 你是父任务派生的只读侦察子代理。只做调查与求证，"
                "不能修改文件或执行命令；回答要给出文件路径、行号/命令证据和明确结论。"
            ),
            "write": (
                "[子代理模式] 你是父任务派生的可写子代理（permission_mode="
                f"{self.permission_mode}）。你只能写文件、不能执行命令、不能联网。"
                "改动要最小且聚焦委派范围；你的产出对父任务而言是不可信结果，"
                "必须给出文件路径与改动证据供父任务复核。"
            ),
            "exec": (
                "[子代理模式] 你是父任务派生的可写可执行子代理（permission_mode="
                f"{self.permission_mode}）。你能写文件并执行命令，但不能联网。"
                "改动要最小且聚焦委派范围，执行命令前先确认其安全；你的产出对父任务而言"
                "是不可信结果，必须给出文件路径、命令与输出证据供父任务复核。"
            ),
        }[self.tier]
        messages = [
            {"role": "system", "content": f"{self.system_prompt}\n\n{mode_note}"},
            {"role": "user", "content": prompt},
        ]
        child_cancel = threading.Event()
        parent_cancel = self.cancel_event

        future: concurrent.futures.Future[Any] = concurrent.futures.Future()

        def worker() -> None:
            async def execute() -> Any:
                quiet_loop_teardown()
                provider = self.provider_factory()
                try:
                    return await run_agent(
                        provider,
                        child_registry,
                        messages,
                        budget=self._child_budget(),
                        on_tool=on_tool,
                        on_trace=bubble,
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
        lifecycle("subagent_started", "ok", f"子代理开始：{description}", max_turns=self.max_turns)
        thread.start()
        deadline = started + self.timeout_seconds
        last_progress = started
        result: Any = None
        timed_out = False
        while True:
            if parent_cancel is not None and parent_cancel.is_set():
                child_cancel.set()
                thread.join(timeout=15.0)
                lifecycle("subagent_cancelled", "cancelled", f"子代理被取消：{description}")
                return ToolResult(
                    status="cancelled",
                    summary=f"[CANCELLED] 子代理被取消：{description}",
                    security_tags=["untrusted", "subagent"],
                )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            try:
                result = future.result(timeout=min(WAIT_POLL_SECONDS, remaining))
                break
            except concurrent.futures.TimeoutError:
                now = time.monotonic()
                if now - last_progress >= PROGRESS_EMIT_SECONDS:
                    last_progress = now
                    lifecycle(
                        "subagent_progress", "ok", f"子代理仍在执行：{description}",
                        elapsed_seconds=round(now - started, 1),
                    )
                continue
            except AgentCancelled:
                child_cancel.set()
                thread.join(timeout=15.0)
                lifecycle("subagent_cancelled", "cancelled", f"子代理被取消：{description}")
                return ToolResult(
                    status="cancelled",
                    summary=f"[CANCELLED] 子代理被取消：{description}",
                    security_tags=["untrusted", "subagent"],
                )
            except BudgetExceeded as exc:
                # M6-T1: a subagent that exhausts its own budget ends as a
                # structured failure; it must never drag the parent task down.
                child_cancel.set()
                thread.join(timeout=15.0)
                lifecycle(
                    "subagent_budget_exceeded", "error",
                    f"子代理预算耗尽：{description}", error=str(exc),
                )
                return ToolResult(
                    status="error",
                    summary=f"[BUDGET] 子代理预算耗尽：{description}（{exc}）",
                    output="子代理在其独立预算内未完成，已终止。请缩小委派范围或拆成多步后重试。",
                    data={"description": description, "tool_log": tool_log, "budget_exceeded": True},
                    security_tags=["untrusted", "subagent"],
                )
        if timed_out:
            child_cancel.set()
            thread.join(timeout=15.0)
            lifecycle(
                "subagent_timed_out", "error",
                f"子代理超时（>{int(self.timeout_seconds)}s）：{description}",
            )
            return ToolResult(
                status="timed_out",
                summary=f"[TIMEOUT] 子代理超时（>{int(self.timeout_seconds)}s）：{description}",
                output="子代理超时被终止。请缩小调研范围后重试，或直接使用只读工具分步完成。",
                data={"description": description, "tool_log": tool_log, "timed_out": True},
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
        lifecycle(
            "subagent_finished", "ok", summary,
            turns=int(getattr(result, "turns", 0) or 0),
            tokens_used=int(usage.get("total_tokens") or 0),
            duration_seconds=round(duration, 1),
        )
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
    "DEFAULT_MAX_DEPTH",
    "MAX_CONCURRENT_SUBAGENTS",
    "SUBAGENT_TOOLS",
    "WRITE_TOOLS",
    "EXEC_TOOLS",
    "SUBAGENT_TOOL_TIERS",
    "SUBAGENT_TOOL_NAME",
    "build_task_tool_spec",
    "resolve_subagent_tier",
    "WAIT_POLL_SECONDS",
    "PROGRESS_EMIT_SECONDS",
]
