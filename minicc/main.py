"""Command-line entry point for the minicc coding agent."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, NoReturn

from .agent.loop import TurnResult, run_agent
from .agent.state import Budget
from .agent.subagent import build_task_tool_spec
from .allowlist import AllowlistError, add_session_rule
from .audit import authorize_tool
from .cli_io import cli_out
from .config import MAX_TIMEOUT_SECONDS, Config, ConfigError, load_config, normalize_model_name
from .commands import discover_commands, expand_slash_command
from .hooks import HookRunner
from .llm.base import system_msg, user_msg
from .llm.openai_provider import OpenAICompatibleProvider
from .logging_setup import (
    configure_logging,
    log_task_event,
    quiet_loop_teardown,
    register_secret,
)
from .prompt import build_system_prompt
from .session import SessionError, SessionStore, list_sessions
from .tools import Editor, ToolCall, ToolRegistry, ToolResult, build_registry


class StreamWriter:
    """Write streamed assistant text without duplicating the final answer."""

    def __init__(self) -> None:
        self.started = False
        self.written = ""

    def __call__(self, delta: str) -> None:
        if not self.started:
            sys.stdout.write("\nassistant> ")
            self.started = True
        self.written += delta
        sys.stdout.write(delta)
        sys.stdout.flush()

    def matches(self, answer: str) -> bool:
        """Whether what the user already saw is the answer that got stored.

        Once anything had streamed, the CLI used to suppress the final print
        unconditionally - so a stream that fell short left a wrong answer on
        screen while the session file held the right one.
        """
        return self.written.strip() == str(answer or "").strip()


class CliView:
    """Keep a compact, expandable CLI transcript anchored to a session."""

    def __init__(self, session: SessionStore, *, verbose_tools: bool = False, announce_resume: bool = False) -> None:
        self.session = session
        saved = session.load_view()
        self.last_item = int(saved.get("last_item") or 0)
        self.last_tool = int(saved.get("last_tool") or 0)
        self.compact_tools = False if verbose_tools else bool(saved.get("compact_tools", True))
        self.tool_history: list[dict[str, Any]] = list(saved.get("tool_history") or [])
        if announce_resume and self.last_item:
            mode = "紧凑工具摘要" if self.compact_tools else "展开工具输出"
            cli_out(f"[view] 已恢复到第 {self.last_item} 个输出项；当前为{mode}。输入 /view 查看阅读位置。")

    @staticmethod
    def _shorten(value: object, limit: int = 180) -> str:
        text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
        return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"

    def _save(self) -> None:
        try:
            self.session.save_view({
                "last_item": self.last_item,
                "last_tool": self.last_tool,
                "compact_tools": self.compact_tools,
                "tool_history": self.tool_history[-24:],
            })
        except SessionError as exc:
            # A view checkpoint is helpful but must never interrupt the agent.
            cli_out(f"[view] 阅读位置暂时无法保存：{exc}", file=sys.stderr)

    def record_tool(self, call: ToolCall, result: ToolResult) -> None:
        self.last_item += 1
        self.last_tool += 1
        command = call.arguments.get("command") if call.tool == "bash" else ""
        entry = {
            "index": self.last_tool,
            "tool": call.tool,
            "summary": result.summary,
            "command": self._shorten(command, 1000) if command else "",
            "output": result.render()[:6000],
        }
        self.tool_history = [*self.tool_history, entry][-24:]
        preview = self._shorten(command) if command else self._shorten(call.arguments.get("path") or "")
        suffix = f" · {preview}" if preview else ""
        cli_out(f"\n[tool {self.last_tool}] {call.tool}{suffix} · {self._shorten(result.summary)}")
        if not self.compact_tools:
            cli_out(result.render())
        self._save()

    def record_answer(self) -> None:
        self.last_item += 1
        self._save()

    def show(self) -> None:
        mode = "compact" if self.compact_tools else "expanded"
        cli_out(f"[view] item={self.last_item} tool={self.last_tool} mode={mode} saved={self.session.path}")
        if self.tool_history:
            cli_out("最近工具：")
            for item in self.tool_history[-8:]:
                cli_out(f"  #{item.get('index', '?')} {item.get('tool', 'tool')} · {self._shorten(item.get('summary'))}")
        else:
            cli_out("最近没有工具记录。")

    def set_compact(self, value: bool) -> None:
        self.compact_tools = bool(value)
        self._save()
        cli_out("工具输出已折叠。" if self.compact_tools else "工具输出已展开。")

    def expand(self, raw_index: str = "") -> None:
        if not self.tool_history:
            cli_out("没有可展开的工具记录。")
            return
        try:
            index = int(raw_index) if raw_index else int(self.tool_history[-1].get("index") or 0)
        except ValueError:
            cli_out("用法：/expand [工具编号]")
            return
        item = next((entry for entry in self.tool_history if int(entry.get("index") or 0) == index), None)
        if item is None:
            cli_out(f"未找到工具 #{index}；输入 /view 查看最近记录。")
            return
        cli_out(f"\n[tool {index}] {item.get('tool', 'tool')} · {item.get('summary', '')}")
        if item.get("command"):
            cli_out(f"command: {item['command']}")
        cli_out(item.get("output") or "（该工具没有额外输出）")

    def reset(self) -> None:
        self.last_item = 0
        self.last_tool = 0
        self.tool_history = []
        self._save()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="minicc",
        description="一个工作区受限、支持工具调用的 Claude Code/Codex 风格 coding agent",
    )
    parser.add_argument("prompt", nargs="*", help="一次性任务；不传则进入交互模式")
    parser.add_argument("--workspace", type=Path, default=Path.cwd(), help="工作区目录，默认当前目录")
    parser.add_argument("--base-url", help="OpenAI 兼容接口地址")
    parser.add_argument("--api-key", help="接口密钥；也可通过 MINICC_API_KEY 设置")
    parser.add_argument("--model", help="模型名")
    parser.add_argument("--reasoning-effort", choices=("low", "mid", "high", "xhigh", "max", "ultra"), help="推理强度")
    parser.add_argument("--tool-mode", choices=("auto", "native", "envelope"), help="工具调用模式")
    parser.add_argument("--compact-threshold", type=int, help="上下文压缩字符阈值")
    parser.add_argument("--max-turns", type=int, help="显式设置硬轮数预算（默认不限）")
    parser.add_argument("--timeout", type=float, help="单次 provider 调用超时秒数")
    parser.add_argument("--context-window", type=int, help="上下文窗口 token 数")
    parser.add_argument("--soft-max-tokens", type=int, help="软 token 预算（触发收尾，不硬中断）")
    parser.add_argument("--max-concurrent-tasks", type=int, help="并发任务上限 (1-64)")
    parser.add_argument("--sandbox", choices=("auto", "host", "docker"), help="命令执行沙箱模式")
    parser.add_argument("--provider-type", choices=("auto", "openai", "anthropic"), help="provider 协议类型")
    parser.add_argument("--fallback-models", help="逗号分隔的降级模型列表")
    parser.add_argument("--task-executor", choices=("thread", "process"), help="任务执行器")
    parser.add_argument("--auto-resume", action="store_true", help="web 启动时自动重排中断任务")
    parser.add_argument("--yolo", action="store_true", help="自动允许写文件和执行命令")
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="允许本会话的联网工具（web_search / webfetch）",
    )
    parser.add_argument(
        "--permission-mode",
        choices=("default", "plan", "acceptEdits", "yolo"),
        default="default",
        help="权限模式：plan 只读规划；acceptEdits 自动接受文件写入（命令仍需确认）；yolo 全部放行",
    )
    parser.add_argument("--no-stream", action="store_true", help="关闭流式输出")
    parser.add_argument("--verbose-tools", action="store_true", help="默认展开工具输出；可在交互中用 /compact 切回摘要")
    parser.add_argument("--resume", action="store_true", help="恢复上次保存的会话")
    parser.add_argument(
        "--list-sessions",
        action="store_true",
        help="列出已保存的会话与 fork 分支后退出（配合 --session-id <名称> --resume 恢复）",
    )
    parser.add_argument(
        "--fork-from",
        metavar="MESSAGE",
        help="从 --session-id 会话的某条消息分叉出新会话后退出：消息序号（保留条数，system=1）或消息 id（m-…）",
    )
    parser.add_argument("--new-session-id", metavar="NAME", help="--fork-from 生成的新会话名（可选，默认自动命名）")
    parser.add_argument("--session-id", default="latest", help="会话名称，默认 latest")
    parser.add_argument("--print-config", action="store_true", help="打印解析后的配置并退出")
    parser.add_argument("--version", action="version", version="minicc 0.1.0")
    return parser


def _load(args: argparse.Namespace, workspace: Path | None = None) -> Config:
    config = load_config(
        base_url=args.base_url,
        api_key=args.api_key,
        model=args.model,
        reasoning_effort=args.reasoning_effort,
        tool_mode=args.tool_mode,
        yolo=True if args.yolo else None,
        workspace=workspace,
    )
    return _apply_cli_overrides(config, args)


def _apply_cli_overrides(config: Config, args: argparse.Namespace) -> Config:
    """M7-T4: explicit CLI flags override any config layer or raise ConfigError."""
    updates: dict[str, Any] = {}

    def _positive(name: str, value: Any, *, number: type = int) -> Any:
        try:
            parsed = number(value)
        except (TypeError, ValueError):
            raise ConfigError(f"--{name} 不是有效数字: {value!r}") from None
        if parsed <= 0:
            raise ConfigError(f"--{name} 必须为正数，得到 {parsed}")
        return parsed

    if args.compact_threshold is not None:
        updates["compact_threshold"] = max(10_000, int(args.compact_threshold))
    if args.max_turns is not None:
        updates["max_turns"] = _positive("max-turns", args.max_turns)
    if args.timeout is not None:
        seconds = _positive("timeout", args.timeout, number=float)
        if seconds > MAX_TIMEOUT_SECONDS:
            raise ConfigError(f"--timeout 超过上限 {MAX_TIMEOUT_SECONDS:g} 秒: {seconds}")
        updates["timeout"] = seconds
    if args.context_window is not None:
        updates["context_window_tokens"] = _positive("context-window", args.context_window)
    if args.soft_max_tokens is not None:
        updates["soft_max_tokens"] = _positive("soft-max-tokens", args.soft_max_tokens)
    if args.max_concurrent_tasks is not None:
        tasks = _positive("max-concurrent-tasks", args.max_concurrent_tasks)
        if tasks > 64:
            raise ConfigError(f"--max-concurrent-tasks 超过上限 64: {tasks}")
        updates["max_concurrent_tasks"] = tasks
    if args.sandbox:
        updates["sandbox_mode"] = args.sandbox
    if args.task_executor:
        updates["task_executor"] = args.task_executor
    if args.provider_type:
        if args.provider_type == "auto":
            haystack = f"{config.base_url} {config.model}".lower()
            updates["provider_type"] = (
                "anthropic" if "anthropic" in haystack or config.model.startswith("claude")
                else "openai"
            )
        else:
            updates["provider_type"] = args.provider_type
    if args.fallback_models:
        models: list[str] = []
        for raw_model in args.fallback_models.replace(";", ",").split(","):
            name = raw_model.strip()
            if not name or name == config.model or name in models:
                continue
            try:
                models.append(normalize_model_name(name))
            except ValueError as exc:
                raise ConfigError(f"--fallback-models 含非法模型名: {exc}") from None
        updates["fallback_models"] = tuple(models)
    if args.auto_resume:
        updates["auto_resume_on_start"] = True
    return replace(config, **updates) if updates else config


def _tool_preview(call: ToolCall) -> str:
    if call.tool == "bash":
        return f"command={call.arguments.get('command', '')!r}"
    path = call.arguments.get("path")
    if path is not None:
        return f"path={path!r}"
    return json.dumps(call.arguments, ensure_ascii=False)[:240]


def _describe_tool(registry: ToolRegistry, name: str) -> str:
    """One /tools line: name plus the declared risk and capabilities."""
    spec = registry.spec(name)
    if spec is None:
        return name
    caps = f" {'+'.join(spec.capabilities)}" if spec.capabilities else ""
    return f"{name} [{spec.risk}{caps}]"


def _permission_gate(
    config: Config,
    registry: ToolRegistry,
    permission_mode: str = "default",
    *,
    allow_network: bool = False,
    session_id: str = "",
    workspace: Path | None = None,
) -> Callable[[str, ToolCall], bool]:
    def should_allow(name: str, call: ToolCall) -> bool:
        risk = registry.risk_of(name)
        decision = authorize_tool(
            name,
            risk,
            call.arguments,
            allow_changes=bool(config.yolo),
            allow_network=bool(allow_network or config.yolo),
            permission_mode="yolo" if config.yolo else permission_mode,
            session_id=session_id,
            workspace=workspace,
            capabilities=registry.capabilities_of(name),
        )
        if decision.allowed:
            return True
        if decision.authorization in {"plan_mode_write", "plan_mode_exec", "unknown_risk"}:
            cli_out(f"\n[minicc] 已拒绝 {name} ({_tool_preview(call)}): {decision.reason}")
            return False
        if decision.authorization == "missing_task_network":
            cli_out(f"\n[minicc] 联网工具需要 --allow-network：{name} ({_tool_preview(call)})")
            return False
        if risk not in {"write", "exec"}:
            cli_out(f"\n[minicc] 已拒绝 {name} ({_tool_preview(call)}): {decision.reason}")
            return False
        cli_out(f"\n[minicc] 即将调用高风险工具 {name} ({_tool_preview(call)})")
        try:
            answer = input("允许此次操作？[y/N/a] ").strip().lower()
        except EOFError:
            return False
        if answer in {"a", "always", "always allow"}:
            if workspace is not None and session_id:
                try:
                    kwargs: dict[str, str] = {"tool": name}
                    if name == "bash":
                        kwargs["command"] = str(call.arguments.get("command") or "").strip()
                    path = call.arguments.get("path")
                    if isinstance(path, str) and path.strip():
                        kwargs["path"] = path.strip()
                    add_session_rule(workspace, session_id, **kwargs)
                    cli_out("[minicc] 已写入本会话 allowlist")
                except AllowlistError as exc:
                    cli_out(f"[minicc] allowlist 写入失败: {exc}")
            return True
        return answer in {"y", "yes", "是"}

    return should_allow


def _print_tool(call: ToolCall, result: ToolResult, view: CliView | None = None) -> None:
    if view is not None:
        view.record_tool(call, result)
        return
    cli_out(f"\n[tool] {call.tool}: {result.summary}")


async def _turn(
    provider: OpenAICompatibleProvider,
    registry: ToolRegistry,
    messages: list[dict[str, Any]],
    config: Config,
    prompt: str,
    session: SessionStore | None = None,
    view: CliView | None = None,
    *,
    stream: bool,
    permission_mode: str = "default",
    allow_network: bool = False,
    workspace: Path | None = None,
) -> TurnResult:
    messages.append(user_msg(prompt))
    if permission_mode == "plan":
        messages.append(system_msg(
            "[计划模式] 本任务是只读规划模式：写入与命令工具会被拒绝。"
            "请完成调研后输出实施计划（目标、步骤、涉及文件、验证方式、风险）。"
        ))
    writer = StreamWriter() if stream else None
    session_id = session.path.stem if session is not None else ""
    result = await run_agent(
        provider,
        registry,
        messages,
        max_turns=config.max_turns,
        budget=Budget(
            max_turns=config.max_turns,
            max_tool_calls=config.max_tool_calls,
            max_duration_seconds=config.max_duration_seconds,
            soft_max_tokens=getattr(config, "soft_max_tokens", None),
            soft_max_duration_seconds=getattr(config, "soft_max_duration_seconds", None),
        ),
        compact_threshold=config.compact_threshold,
        on_stream=writer,
        # M8-T5: the CLI has no task event funnel, so loop traces (run_started,
        # tool rounds, budget, run_finished) go straight to the structured log.
        on_trace=lambda event: log_task_event(event, task_id=session_id or "cli"),
        on_tool=(lambda call, result: _print_tool(call, result, view)),
        should_allow=_permission_gate(
            config,
            registry,
            permission_mode,
            allow_network=allow_network,
            session_id=session_id,
            workspace=workspace,
        ),
        hooks=HookRunner(workspace),
    )
    if writer is None or not writer.started or not writer.matches(result.answer):
        cli_out(f"\nassistant> {result.answer}")
    else:
        cli_out()
    if result.tokens_used.get("total_tokens"):
        cli_out(f"[usage] total_tokens={result.tokens_used['total_tokens']}")
    if view is not None:
        view.record_answer()
    if session is not None:
        session.save(messages)
    return result


async def _interactive(
    provider: OpenAICompatibleProvider,
    registry: ToolRegistry,
    messages: list[dict[str, Any]],
    config: Config,
    session: SessionStore | None = None,
    view: CliView | None = None,
    *,
    stream: bool,
    permission_mode: str = "default",
    allow_network: bool = False,
    workspace: Path | None = None,
) -> None:
    cli_out("minicc 已启动。输入 /help 查看命令，输入 /exit 退出。")
    while True:
        try:
            raw = input("\nminicc> ")
        except (EOFError, KeyboardInterrupt):
            cli_out()
            return
        prompt = raw.strip()
        if not prompt:
            continue
        if prompt in {"/exit", "/quit"}:
            return
        if prompt == "/help":
            cli_out("/help  /tools  /status  /view  /compact  /expand [n]  /clear  /exit")
            custom = discover_commands(workspace or Path.cwd())
            if custom:
                cli_out("自定义命令：")
                for command in custom:
                    hint = f" {command.argument_hint}" if command.argument_hint else ""
                    cli_out(f"  /{command.name}{hint} — {command.description} [{command.scope}]")
            continue
        if prompt == "/tools":
            cli_out("\n".join(_describe_tool(registry, name) for name in registry.names()))
            continue
        if prompt == "/status":
            cli_out(config.describe())
            if session is not None:
                cli_out(f"session={session.path}")
            continue
        if prompt == "/clear":
            del messages[1:]
            if view is not None:
                view.reset()
            if session is not None:
                session.save(messages)
            cli_out("会话上下文已清空。")
            continue
        if prompt == "/view":
            if view is not None:
                view.show()
            continue
        if prompt == "/compact":
            if view is not None:
                view.set_compact(True)
            continue
        if prompt == "/collapse":
            if view is not None:
                view.set_compact(True)
            continue
        if prompt.startswith("/expand"):
            if view is not None:
                view.expand(prompt.removeprefix("/expand").strip())
            continue
        if prompt.startswith("/"):
            expanded = expand_slash_command(prompt, workspace or Path.cwd())
            if expanded is None:
                cli_out(f"未知命令：{prompt.split(' ', 1)[0]}（/help 查看内置与自定义命令）")
                continue
            prompt = expanded
        await _turn(
            provider,
            registry,
            messages,
            config,
            prompt,
            session,
            view,
            stream=stream,
            permission_mode=permission_mode,
            allow_network=allow_network,
            workspace=workspace,
        )


def _fatal(message: str) -> NoReturn:
    cli_out(f"minicc: {message}", file=sys.stderr)
    raise SystemExit(2)


def _print_sessions(workspace: Path) -> int:
    """Render the session forest (one line per session; forks show lineage)."""
    sessions = list_sessions(workspace)
    if not sessions:
        cli_out("（该工作区暂无保存的会话）")
        return 0
    known = {item["session_id"] for item in sessions}
    for item in sessions:
        if item.get("error"):
            cli_out(f"{item['session_id']:28} [错误] {item['error']}")
            continue
        mark = ""
        lineage = item.get("forked_from")
        if isinstance(lineage, dict):
            source = str(lineage.get("session") or "?")
            at = lineage.get("from_message_id") or lineage.get("keep_messages") or "?"
            mark = f"   |- fork of {source} @ {at}"
            if source not in known:
                mark += "（源会话已不在列表中）"
        title = str(item.get("title") or "")
        cli_out(
            f"{item['session_id']:28} {item['messages']:>4} 条  {item.get('updated_at', '')}"
            f"{mark}{('  ' + title) if title else ''}"
        )
    return 0


def _warn_unrun_prompt(prompt: list[str], flag: str) -> None:
    """Say so when a one-shot task is dropped by a session subcommand.

    ``minicc --fork-from 4 "do X"`` used to fork, print a hint and exit 0 while
    the task never ran - to a script that reads as success.
    """
    if not prompt:
        return
    text = " ".join(prompt).strip()
    if not text:
        return
    cli_out(f"注意：{flag} 只操作会话文件，本次任务文本没有执行（{len(text)} 字）。")
    cli_out("要执行它，请在目标分支上重新提交，例如 minicc --resume --session-id <分支名> <任务>")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    # M7-T4: resolve the workspace before loading config so the project
    # layer (<workspace>/.minicc/config.json) participates in resolution.
    workspace = args.workspace.expanduser().resolve()
    if not workspace.is_dir():
        _fatal(f"工作区不是目录: {workspace}")

    if args.list_sessions:
        _warn_unrun_prompt(args.prompt, "--list-sessions")
        return _print_sessions(workspace)

    if args.fork_from:
        raw_point = str(args.fork_from).strip()
        point: int | str = int(raw_point) if raw_point.isdigit() else raw_point
        try:
            source_store = SessionStore(workspace, args.session_id)
            target_store = source_store.fork(
                point,
                new_session_id=(str(args.new_session_id).strip() or None)
                if args.new_session_id
                else None,
            )
        except SessionError as exc:
            _fatal(str(exc))
        cli_out(f"已 fork：{source_store.session_id} -> {target_store.session_id}（{target_store.path.name}）")
        cli_out(f"恢复该分支: minicc --resume --session-id {target_store.session_id}")
        _warn_unrun_prompt(args.prompt, "--fork-from")
        return 0

    try:
        config = _load(args, workspace)
    except ConfigError as exc:
        _fatal(str(exc))
    # M8-T5: logging is configured only once the config exists, so a config
    # error cannot be swallowed by a half-set-up handler stack; the key is
    # registered before any provider log line can carry it.
    configure_logging()
    register_secret(config.api_key)

    if args.print_config:
        cli_out(config.describe())
        cli_out(f"workspace={workspace}")
        return 0

    editor = Editor(workspace, audit_path=workspace / ".minicc" / "audit.jsonl")
    registry = build_registry(editor, yolo=config.yolo)
    system_prompt = build_system_prompt(workspace)
    try:
        session = SessionStore(workspace, args.session_id)
        messages = session.load(system_prompt) if args.resume else [system_msg(system_prompt)]
        view = CliView(session, verbose_tools=args.verbose_tools, announce_resume=args.resume)
    except SessionError as exc:
        _fatal(str(exc))
    if str(getattr(config, "provider_type", "openai")) == "anthropic":
        from .llm.anthropic_provider import AnthropicProvider

        provider = AnthropicProvider(
            api_key=config.api_key,
            model=config.model,
            base_url=str(getattr(config, "anthropic_base_url", "") or config.base_url),
            timeout=config.timeout,
            max_retries=int(getattr(config, "provider_retries", 4)),
        )
    else:
        provider = OpenAICompatibleProvider(
            base_url=config.base_url,
            api_key=config.api_key,
            model=config.model,
            plan_base_url=str(getattr(config, "plan_base_url", "") or ""),
            plan_api_key=str(getattr(config, "plan_api_key", "") or ""),
            timeout=config.timeout,
            max_retries=config.provider_retries,
            tool_mode=config.tool_mode,
            protocol=config.llm_protocol,
            reasoning_effort=config.reasoning_effort,
        )

    # Bounded Task subagent for the CLI: same restricted readonly toolset and
    # no recursion, sharing the parent's provider instance (requests are
    # strictly sequential because the parent loop blocks on the sub-run).
    registry.register(build_task_tool_spec(
        provider_factory=lambda: provider,
        workspace=workspace,
        system_prompt=system_prompt,
        base_registry=registry,
    ))

    async def run() -> None:
        quiet_loop_teardown()
        try:
            prompt = " ".join(args.prompt).strip()
            if prompt:
                await _turn(
                    provider,
                    registry,
                    messages,
                    config,
                    expand_slash_command(prompt, workspace) or prompt,
                    session,
                    view,
                    stream=not args.no_stream,
                    permission_mode=args.permission_mode,
                    allow_network=args.allow_network,
                    workspace=workspace,
                )
            else:
                await _interactive(
                    provider,
                    registry,
                    messages,
                    config,
                    session,
                    view,
                    stream=not args.no_stream,
                    permission_mode=args.permission_mode,
                    allow_network=args.allow_network,
                    workspace=workspace,
                )
        finally:
            await provider.close()

    asyncio.run(run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
