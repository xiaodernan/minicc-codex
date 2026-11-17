"""The only stdout writer in ``minicc/`` (M8-T5).

Diagnostics belong in ``logging`` (see :mod:`minicc.logging_setup`), user-facing
CLI/REPL lines belong here. Keeping one call site for ``print`` means the
terminal protocol stays on stdout while every other message can be redirected,
leveled and redacted.

M12: the CLI is bilingual. ``MINICC_LOCALE=zh_cn|en_us`` selects the message
table (``zh_cn`` is the default, matching this repository's copy culture);
``get_locale`` / ``set_locale`` are the programmatic switches and ``tr`` is the
one translation function every user-facing line asks. The two tables are held
to each other by ``tests/test_cli_i18n.py``: every key exists in both, no
message is unformatted garbage, and keys nobody reads are counted by a ratchet
that only ever shrinks.
"""

from __future__ import annotations

import os
import sys
from typing import Any

__all__ = ["cli_out", "tr", "get_locale", "set_locale"]

# Current locale: "zh_cn" or "en_us". Anything unrecognized falls back to zh_cn.
_CURRENT_LOCALE: str = os.environ.get("MINICC_LOCALE", "zh_cn").lower()
if _CURRENT_LOCALE not in ("zh_cn", "en_us"):
    _CURRENT_LOCALE = "zh_cn"


def get_locale() -> str:
    return _CURRENT_LOCALE


def set_locale(locale: str) -> None:
    global _CURRENT_LOCALE
    locale = str(locale).lower()
    if locale in ("zh_cn", "en_us"):
        _CURRENT_LOCALE = locale


# Translation tables. One key, two messages, both in the same shape: the
# en_us text is written to stand alone, not to mirror zh_cn word order.
_MESSAGES = {
    "zh_cn": {
        # main.py — REPL and view
        "starting": "minicc 已启动。输入 /help 查看命令，输入 /exit 退出。",
        "help_line": "/help  /tools  /status  /view  /compact (压缩上下文)  /collapse (折叠工具输出)  /expand [n]  /clear  /cost  /doctor  /exit",
        "custom_commands": "自定义命令：",
        "unknown_command": "未知命令：{cmd}。/help 查看内置与自定义命令。",
        "session_cleared": "会话上下文已清空。",
        "no_tool_history": "最近没有工具记录。",
        "recent_tools": "最近工具：",
        "tool_output_collapsed": "工具输出已折叠。",
        "tool_output_expanded": "工具输出已展开。",
        "no_tool_to_expand": "没有可展开的工具记录。",
        "expand_usage": "用法：/expand [工具编号]",
        "tool_not_found": "未找到工具 #{index}；输入 /view 查看最近记录。",
        "tool_no_output": "（该工具没有额外输出）",
        "view_restored": "[view] 已恢复到第 {item} 个输出项；当前为{mode}。输入 /view 查看阅读位置。",
        "view_save_failed": "阅读位置暂时无法保存：{exc}",
        "compact_mode": "紧凑工具摘要",
        "expanded_mode": "展开工具输出",
        "assistant_prefix": "\nassistant> ",
        "usage": "[usage] total_tokens={tokens}",
        # main.py — tool calls and allowlist
        "denied_tool": "已拒绝 {tool} ({preview}): {reason}",
        "denied_ctrl_c": "已拒绝（Ctrl-C）",
        "denied_ctrl_c_turn": "已中断本轮（Ctrl-C）。",
        "need_network": "联网工具需要 --allow-network：{tool} ({preview})",
        "high_risk_tool": "即将调用高风险工具 {tool} ({preview})",
        "allow_prompt": "允许此次操作？[y/N/a/A] ",
        "allowlist_written": "[minicc] 已写入本会话 allowlist",
        "allowlist_written_tool": "[minicc] 已写入本会话 allowlist：{tool} 的全部用法都将自动放行",
        "allowlist_failed": "[minicc] allowlist 写入失败: {exc}",
        # main.py — sessions, doctor, digest
        "session_error": "SessionError",
        "session_not_found": "会话不存在: {name}",
        "session_format_error": "session 格式错误: {path}",
        "fork_created": "已 fork：{source} -> {target}（{name}）",
        "fork_resume": "恢复该分支: minicc --resume --session-id {target}",
        "prompt_not_run": "注意：{flag} 只操作会话文件，本次任务文本没有执行（{len} 字）。",
        "resume_instruction": "要执行它，请在目标分支上重新提交，例如 minicc --resume --session-id <分支名> <任务>",
        "fork_invalid_point": "会话 {session} 中没有消息 id {point!r}（fork 点无效）",
        "fork_min_keep": "fork 点至少为 1（保留 system 消息）",
        "fork_max_keep": "fork 点 {keep} 超出会话消息数 {total}",
        "rewind_min": "keep_messages 至少为 1（保留 system 消息）",
        "rewind_no_session": "会话不存在: {name}",
        "rewind_no_user": "会话中没有第 {n} 条 user 消息",
        "user_index_min": "user_index 至少为 1",
        "no_saved_sessions": "（该工作区暂无保存的会话）",
        "error_tag": "[错误]",
        "channel_unavailable": "通道状态不可用（{type}）",
        "channel_plan_note": "通道: {active}（套餐通道{plan_note}）",
        # audit.py / permissions
        "denied_write": "已拒绝 {tool} ({preview}): {reason}",
        "denied_exec": "已拒绝 {tool} ({preview}): {reason}",
        # config
        "config_error": "minicc: {message}",
        "workspace_not_dir": "工作区不是目录: {path}",
        # tools
        "tool_denied": "[{code}] {message}",
        "tool_error": "[TOOL_ERROR] {message}",
        "unknown_tool": "[UNKNOWN_TOOL] 未知工具 {tool!r} (已注册: {registered})",
        "invalid_args": "[INVALID_ARGUMENTS] {message}",
        "system_io_error": "[TOOL_ERROR] 系统 IO 错误: {exc}",
        "tool_exception": "[TOOL_ERROR] 工具 {tool!r} 未处理异常: {type}: {exc}",
        # git
        "git_failed": "git 命令失败: {exc}",
        "branch_invalid": "branch 参数非法",
        "path_outside": "路径越界: {path} 超出 workspace 根",
        "absolute_path": "路径越界: 不允许绝对路径 ({path})",
        # memory
        "memory_written": "记忆已写入",
        "memory_not_found": "记忆未找到: {id}",
        "memory_list_empty": "暂无记忆条目",
        # mcp
        "mcp_config_error": "MCP 配置错误: {message}",
        "mcp_server_failed": "MCP server {name} 启动失败: {reason}",
        "mcp_sampling_denied": "Sampling denied: {reason}",
        "mcp_no_provider": "No provider configured for sampling",
        "mcp_sampling_failed": "Sampling failed: {exc}",
        # cost
        "no_snapshots": "本会话暂无任务快照",
        "session_cost": "本会话累计: {count} 个任务快照",
        "session_tokens": "  total_tokens: {tokens}",
        "session_cost_usd": "  cost_usd: ${cost:.6f}",
        "session_cost_none": "  cost_usd: 无价格数据（模型未计价）",
        "session_cost_unavailable": "非会话模式无累计成本",
        "snapshots_read_failed": "读取快照失败: {exc}",
    },
    "en_us": {
        # main.py — REPL and view
        "starting": "minicc started. Type /help for commands, /exit to quit.",
        "help_line": "/help  /tools  /status  /view  /compact (compact context)  /collapse (collapse tool output)  /expand [n]  /clear  /cost  /doctor  /exit",
        "custom_commands": "Custom commands:",
        "unknown_command": "Unknown command: {cmd} (/help for built-in and custom commands)",
        "session_cleared": "Session context cleared.",
        "no_tool_history": "No recent tool records.",
        "recent_tools": "Recent tools:",
        "tool_output_collapsed": "Tool output collapsed.",
        "tool_output_expanded": "Tool output expanded.",
        "no_tool_to_expand": "No tool records to expand.",
        "expand_usage": "Usage: /expand [tool_index]",
        "tool_not_found": "Tool #{index} not found; type /view to see recent records.",
        "tool_no_output": "(no extra output from this tool)",
        "view_restored": "[view] Restored to item #{item}; current mode is {mode}. Type /view for reading position.",
        "view_save_failed": "Could not save reading position: {exc}",
        "compact_mode": "compact tool summary",
        "expanded_mode": "expanded tool output",
        "assistant_prefix": "\nassistant> ",
        "usage": "[usage] total_tokens={tokens}",
        # main.py — tool calls and allowlist
        "denied_tool": "Denied {tool} ({preview}): {reason}",
        "denied_ctrl_c": "Denied (Ctrl-C)",
        "denied_ctrl_c_turn": "Turn interrupted (Ctrl-C).",
        "need_network": "Network tool requires --allow-network: {tool} ({preview})",
        "high_risk_tool": "About to call high-risk tool {tool} ({preview})",
        "allow_prompt": "Allow this operation? [y/N/a/A] ",
        "allowlist_written": "[minicc] Written to session allowlist",
        "allowlist_written_tool": "[minicc] Written to session allowlist: all uses of {tool} will be auto-approved",
        "allowlist_failed": "[minicc] Allowlist write failed: {exc}",
        # main.py — sessions, doctor, digest
        "session_error": "SessionError",
        "session_not_found": "Session not found: {name}",
        "session_format_error": "Session format error: {path}",
        "fork_created": "Forked: {source} -> {target} ({name})",
        "fork_resume": "Resume branch: minicc --resume --session-id {target}",
        "prompt_not_run": "Note: {flag} only operates on session files; task text not executed ({len} chars).",
        "resume_instruction": "To run it, resubmit on the target branch, e.g. minicc --resume --session-id <branch> <task>",
        "fork_invalid_point": "Session {session} has no message id {point!r} (invalid fork point)",
        "fork_min_keep": "Fork point must be at least 1 (keep system message)",
        "fork_max_keep": "Fork point {keep} exceeds session message count {total}",
        "rewind_min": "keep_messages must be at least 1 (keep system message)",
        "rewind_no_session": "Session not found: {name}",
        "rewind_no_user": "Session has no #{n} user message",
        "user_index_min": "user_index must be at least 1",
        "no_saved_sessions": "(no saved sessions in this workspace)",
        "error_tag": "[error]",
        "channel_unavailable": "Channel status unavailable ({type})",
        "channel_plan_note": "Channel: {active} (plan channel{plan_note})",
        # audit.py / permissions
        "denied_write": "Denied {tool} ({preview}): {reason}",
        "denied_exec": "Denied {tool} ({preview}): {reason}",
        # config
        "config_error": "minicc: {message}",
        "workspace_not_dir": "Workspace is not a directory: {path}",
        # tools
        "tool_denied": "[{code}] {message}",
        "tool_error": "[TOOL_ERROR] {message}",
        "unknown_tool": "[UNKNOWN_TOOL] Unknown tool {tool!r} (registered: {registered})",
        "invalid_args": "[INVALID_ARGUMENTS] {message}",
        "system_io_error": "[TOOL_ERROR] System IO error: {exc}",
        "tool_exception": "[TOOL_ERROR] Tool {tool!r} unhandled exception: {type}: {exc}",
        # git
        "git_failed": "Git command failed: {exc}",
        "branch_invalid": "Invalid branch parameter",
        "path_outside": "Path outside workspace: {path}",
        "absolute_path": "Path outside: absolute paths not allowed ({path})",
        # memory
        "memory_written": "Memory written",
        "memory_not_found": "Memory not found: {id}",
        "memory_list_empty": "No memory entries",
        # mcp
        "mcp_config_error": "MCP config error: {message}",
        "mcp_server_failed": "MCP server {name} failed to start: {reason}",
        "mcp_sampling_denied": "Sampling denied: {reason}",
        "mcp_no_provider": "No provider configured for sampling",
        "mcp_sampling_failed": "Sampling failed: {exc}",
        # cost
        "no_snapshots": "No task snapshots in this session",
        "session_cost": "Session total: {count} task snapshots",
        "session_tokens": "  total_tokens: {tokens}",
        "session_cost_usd": "  cost_usd: ${cost:.6f}",
        "session_cost_none": "  cost_usd: No pricing data (model unpriced)",
        "session_cost_unavailable": "No cumulative cost outside a session",
        "snapshots_read_failed": "Failed to read snapshots: {exc}",
    },
}


def tr(key: str, **kwargs: Any) -> str:
    """Translate a message key for the current locale.

    Falls back to the raw key when neither table carries it — an absent key is
    a visible bug, not silent English — and to zh_cn when the kwargs do not
    match the message shape, so a mis-shaped format never raises mid-CLI.
    """
    locale = _CURRENT_LOCALE
    if locale not in _MESSAGES:
        locale = "zh_cn"
    msg = _MESSAGES[locale].get(key) or _MESSAGES["zh_cn"].get(key) or key
    if kwargs:
        try:
            return msg.format(**kwargs)
        except (KeyError, ValueError):
            return msg
    return msg


def cli_out(*parts: Any, file: Any = None, sep: str = " ", end: str = "\n") -> None:
    print(*parts, sep=sep, end=end, file=file or sys.stdout, flush=True)
