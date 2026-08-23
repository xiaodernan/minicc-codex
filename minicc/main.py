"""Command-line entry point for the minicc coding agent."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Callable, NoReturn

from .agent.loop import TurnResult, run_agent
from .config import Config, ConfigError, load_config
from .llm.base import system_msg, user_msg
from .llm.openai_provider import OpenAICompatibleProvider
from .prompt import build_system_prompt
from .session import SessionError, SessionStore
from .tools import Editor, ToolCall, ToolRegistry, ToolResult, build_registry


class StreamWriter:
    """Write streamed assistant text without duplicating the final answer."""

    def __init__(self) -> None:
        self.started = False

    def __call__(self, delta: str) -> None:
        if not self.started:
            sys.stdout.write("\nassistant> ")
            self.started = True
        sys.stdout.write(delta)
        sys.stdout.flush()


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
    parser.add_argument("--reasoning-effort", choices=("standard", "high", "max"), help="推理预算")
    parser.add_argument("--tool-mode", choices=("auto", "native", "envelope"), help="工具调用模式")
    parser.add_argument("--max-turns", type=int, help="单次任务最多模型轮次")
    parser.add_argument("--compact-threshold", type=int, help="上下文压缩字符阈值")
    parser.add_argument("--yolo", action="store_true", help="自动允许写文件和执行命令")
    parser.add_argument("--no-stream", action="store_true", help="关闭流式输出")
    parser.add_argument("--resume", action="store_true", help="恢复上次保存的会话")
    parser.add_argument("--session-id", default="latest", help="会话名称，默认 latest")
    parser.add_argument("--print-config", action="store_true", help="打印解析后的配置并退出")
    parser.add_argument("--version", action="version", version="minicc 0.1.0")
    return parser


def _load(args: argparse.Namespace) -> Config:
    return load_config(
        base_url=args.base_url,
        api_key=args.api_key,
        model=args.model,
        reasoning_effort=args.reasoning_effort,
        tool_mode=args.tool_mode,
        yolo=True if args.yolo else None,
    )


def _tool_preview(call: ToolCall) -> str:
    if call.tool == "bash":
        return f"command={call.arguments.get('command', '')!r}"
    path = call.arguments.get("path")
    if path is not None:
        return f"path={path!r}"
    return json.dumps(call.arguments, ensure_ascii=False)[:240]


def _permission_gate(config: Config, registry: ToolRegistry) -> Callable[[str, ToolCall], bool]:
    def should_allow(name: str, call: ToolCall) -> bool:
        risk = registry.risk_of(name)
        if risk not in ("write", "exec"):
            return True
        if config.yolo:
            return True
        print(f"\n[minicc] 即将调用高风险工具 {name} ({_tool_preview(call)})")
        try:
            answer = input("允许此次操作？[y/N] ").strip().lower()
        except EOFError:
            return False
        return answer in {"y", "yes", "是"}

    return should_allow


def _print_tool(call: ToolCall, result: ToolResult) -> None:
    print(f"\n[tool] {call.tool}: {result.summary}")


async def _turn(
    provider: OpenAICompatibleProvider,
    registry: ToolRegistry,
    messages: list[dict[str, Any]],
    config: Config,
    prompt: str,
    session: SessionStore | None = None,
    *,
    stream: bool,
) -> TurnResult:
    messages.append(user_msg(prompt))
    writer = StreamWriter() if stream else None
    result = await run_agent(
        provider,
        registry,
        messages,
        max_turns=config.max_turns,
        compact_threshold=config.compact_threshold,
        on_stream=writer,
        on_tool=_print_tool,
        should_allow=_permission_gate(config, registry),
    )
    if writer is None or not writer.started:
        print(f"\nassistant> {result.answer}")
    else:
        print()
    if result.tokens_used.get("total_tokens"):
        print(f"[usage] total_tokens={result.tokens_used['total_tokens']}")
    if session is not None:
        session.save(messages)
    return result


async def _interactive(
    provider: OpenAICompatibleProvider,
    registry: ToolRegistry,
    messages: list[dict[str, Any]],
    config: Config,
    session: SessionStore | None = None,
    *,
    stream: bool,
) -> None:
    print("minicc 已启动。输入 /help 查看命令，输入 /exit 退出。")
    while True:
        try:
            raw = input("\nminicc> ")
        except (EOFError, KeyboardInterrupt):
            print()
            return
        prompt = raw.strip()
        if not prompt:
            continue
        if prompt in {"/exit", "/quit"}:
            return
        if prompt == "/help":
            print("/help  /tools  /status  /clear  /exit")
            continue
        if prompt == "/tools":
            print("\n".join(registry.names()))
            continue
        if prompt == "/status":
            print(config.describe())
            if session is not None:
                print(f"session={session.path}")
            continue
        if prompt == "/clear":
            del messages[1:]
            if session is not None:
                session.save(messages)
            print("会话上下文已清空。")
            continue
        await _turn(provider, registry, messages, config, prompt, session, stream=stream)


def _fatal(message: str) -> NoReturn:
    print(f"minicc: {message}", file=sys.stderr)
    raise SystemExit(2)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        config = _load(args)
    except ConfigError as exc:
        _fatal(str(exc))

    workspace = args.workspace.expanduser().resolve()
    if not workspace.is_dir():
        _fatal(f"工作区不是目录: {workspace}")
    if args.compact_threshold is not None:
        config.compact_threshold = max(10_000, args.compact_threshold)
    if args.max_turns is not None:
        config.max_turns = max(1, args.max_turns)
    if args.print_config:
        print(config.describe())
        print(f"workspace={workspace}")
        return 0

    editor = Editor(workspace, audit_path=workspace / ".minicc" / "audit.jsonl")
    registry = build_registry(editor, yolo=config.yolo)
    system_prompt = build_system_prompt(workspace)
    try:
        session = SessionStore(workspace, args.session_id)
        messages = session.load(system_prompt) if args.resume else [system_msg(system_prompt)]
    except SessionError as exc:
        _fatal(str(exc))
    provider = OpenAICompatibleProvider(
        base_url=config.base_url,
        api_key=config.api_key,
        model=config.model,
        timeout=config.timeout,
        tool_mode=config.tool_mode,
        reasoning_effort=config.reasoning_effort,
    )

    async def run() -> None:
        try:
            prompt = " ".join(args.prompt).strip()
            if prompt:
                await _turn(
                    provider,
                    registry,
                    messages,
                    config,
                    prompt,
                    session,
                    stream=not args.no_stream,
                )
            else:
                await _interactive(
                    provider,
                    registry,
                    messages,
                    config,
                    session,
                    stream=not args.no_stream,
                )
        finally:
            await provider.close()

    asyncio.run(run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
