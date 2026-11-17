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
        # main.py — argparse (--help face)
        "arg_description": "一个工作区受限、支持工具调用的 Claude Code/Codex 风格 coding agent",
        "arg_prompt": "一次性任务；不传则进入交互模式",
        "arg_workspace": "工作区目录，默认当前目录",
        "arg_base_url": "OpenAI 兼容接口地址",
        "arg_api_key": "接口密钥；也可通过 MINICC_API_KEY 设置",
        "arg_model": "模型名",
        "arg_reasoning_effort": "推理强度",
        "arg_tool_mode": "工具调用模式",
        "arg_output_style": "输出风格：preset（concise/explanatory）或自定义文字；覆盖配置与环境变量",
        "arg_compact_threshold": "上下文压缩字符阈值",
        "arg_max_turns": "显式设置硬轮数预算（默认不限）",
        "arg_timeout": "单次 provider 调用超时秒数",
        "arg_context_window": "上下文窗口 token 数",
        "arg_soft_max_tokens": "软 token 预算（触发收尾，不硬中断）",
        "arg_max_concurrent_tasks": "并发任务上限 (1-64)",
        "arg_sandbox": "命令执行沙箱模式",
        "arg_provider_type": "provider 协议类型",
        "arg_fallback_models": "逗号分隔的降级模型列表",
        "arg_task_executor": "任务执行器",
        "arg_auto_resume": "web 启动时自动重排中断任务",
        "arg_yolo": "自动允许写文件和执行命令",
        "arg_allow_network": "允许本会话的联网工具（web_search / webfetch）",
        "arg_permission_mode": "权限模式：plan 只读规划；acceptEdits 自动接受文件写入（命令仍需确认）；yolo 全部放行",
        "arg_subagent_writable": "允许 task 子代理在已授权写入的会话里委派写文件（acceptEdits）或写+命令（yolo）；默认/plan 模式下子代理保持只读（M6-T1）",
        "arg_no_stream": "关闭流式输出",
        "arg_verbose_tools": "默认展开工具输出；可在交互中用 /collapse 切回折叠",
        "arg_resume": "恢复上次保存的会话",
        "arg_list_sessions": "列出已保存的会话与 fork 分支后退出（配合 --session-id <名称> --resume 恢复）",
        "arg_fork_from": "从 --session-id 会话的某条消息分叉出新会话后退出：消息序号（保留条数，system=1）或消息 id（m-…）",
        "arg_new_session_id": "--fork-from 生成的新会话名（可选，默认自动命名）",
        "arg_session_id": "会话名称，默认 latest",
        "arg_print_config": "打印解析后的配置并退出",
        "arg_setup": "创建 .minicc/ 骨架（permissions.json + web_token.json）并退出",
        "arg_doctor": "运行工作区自检并退出（不调网络、不跑模型）",
        "arg_doctor_strict": "同 --doctor，但 warning 也按 fatal 处理（CI 风险守门）",
        "arg_stats": "只读打印工作区现状清单（不调网络、不跑模型）",
        "arg_digest": "只读打印工作区的仓库考古学读数：分支 / 提交 / 首次提交 / 批次手稿（不调网络、不跑模型）",
        "arg_capabilities": "打印注册表里的工具能力清单（JSON）并退出（不调网络、不跑模型）",
        "arg_json": "与 --doctor / --doctor-strict / --stats / --capabilities 搭配：输出机器可读 JSON",
        "arg_version": "打印版本并退出；与 --json 搭配输出 name/version JSON",
        # audit.py — authorization decision reasons
        "audit_perm_unreadable": "permissions.json 读不出来: {exc}",
        "audit_perm_deny_tool": "permissions.json 读不出来，先拒绝此操作 ({tool}): {error}",
        "audit_perm_deny_rule": "permissions.json deny 规则拒绝了此操作 ({tool})",
        "audit_perm_invalid": "permission_mode 非法: {value!r} (default|plan|acceptEdits|yolo)",
        "audit_policy_unreadable": "permissions.json 读不出来，先拒绝此操作（{policy_error}）",
        "audit_deny_rule": "permissions.json deny 规则拒绝",
        "audit_allow_rule": "permissions.json allow 规则放行",
        "audit_session_allow": "本会话 allowlist 已放行",
        "audit_git_reconly": "git_stage/git_commit 只能由人类在会话中授权；yolo / allow_changes / acceptEdits 都不放行",
        "audit_yolo_readonly": "任务为 yolo 模式，工具已放行",
        "audit_yolo_writes": "任务为 yolo 模式，写入与命令已放行",
        "audit_task_network_readonly": "本任务已明确授权联网查询",
        "audit_task_network_missing": "联网查询需要当前任务单独授权",
        "audit_default_readonly": "只读工具已允许",
        "audit_plan_mode_write": "计划模式只允许只读工具，写入已拒绝",
        "audit_network_needs_task": "该工具声明了联网能力，需要先获得本任务的联网授权",
        "audit_task_write": "本任务已明确授权写入",
        "audit_task_write_missing": "写入工具需要当前任务明确授权",
        "audit_plan_mode_exec": "计划模式只允许只读工具，命令已拒绝",
        "audit_task_network_exec": "本任务已明确授权网络命令",
        "audit_task_network_exec_missing": "网络命令需要单独授权",
        "audit_safe_verification": "受限只读验证命令已允许",
        "audit_task_exec": "本任务已明确授权命令执行",
        "audit_task_exec_missing": "命令执行需要当前任务明确授权",
        "audit_unknown_risk": "未知工具风险，已拒绝执行",
        # doctor.py — advice lines
        "doctor_python": "升级到 python>=3.11 (当前: {major}.{minor}.{micro})",
        "doctor_reinstall": "重装 wheel 或 `pip install -e .`",
        "doctor_write": "检查目录的写权限",
        "doctor_owner": "检查 .minicc/ 的所有者与权限",
        # commands.py — command-file failure face
        "commands_undecodable": "编码读不出来",
        "commands_os_unreadable": "操作系统不给读",
        "commands_file_broken": "自定义命令 /{head} 的定义文件在 {scope} 级存在，但{reason_text}（{path}：{detail}）。这条输入不会作为普通消息发给模型——请先修好这个文件（存成 UTF-8，或释放占用它的进程）。",
        "commands_skills_header": "可用技能（仅列出名称与说明，正文不常驻上下文；需要时先用 read_file 读取对应 SKILL.md）：",
        "commands_skills_dir": "技能文件目录：{path}",
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
        # main.py — argparse (--help face)
        "arg_description": "A workspace-scoped, tool-calling Claude Code/Codex-style coding agent",
        "arg_prompt": "One-shot task; omit for interactive mode",
        "arg_workspace": "Workspace directory (default: current directory)",
        "arg_base_url": "OpenAI-compatible endpoint URL",
        "arg_api_key": "API key; can also be set via MINICC_API_KEY",
        "arg_model": "Model name",
        "arg_reasoning_effort": "Reasoning effort",
        "arg_tool_mode": "Tool-call mode",
        "arg_output_style": "Output style: preset (concise/explanatory) or custom text; overrides config and env",
        "arg_compact_threshold": "Context compaction character threshold",
        "arg_max_turns": "Explicit round-budget ceiling (default: unbounded)",
        "arg_timeout": "Timeout in seconds for one provider call",
        "arg_context_window": "Context window size in tokens",
        "arg_soft_max_tokens": "Soft token budget (triggers wrap-up, never a hard cutoff)",
        "arg_max_concurrent_tasks": "Concurrent task limit (1-64)",
        "arg_sandbox": "Command execution sandbox mode",
        "arg_provider_type": "Provider protocol type",
        "arg_fallback_models": "Comma-separated fallback model list",
        "arg_task_executor": "Task executor",
        "arg_auto_resume": "Auto-reschedule interrupted tasks on web start",
        "arg_yolo": "Auto-approve file writes and command execution",
        "arg_allow_network": "Allow this session's network tools (web_search / webfetch)",
        "arg_permission_mode": "Permission mode: plan (read-only); acceptEdits (file writes auto-accepted, commands still confirmed); yolo (everything allowed)",
        "arg_subagent_writable": "Let task subagents delegate writes in this session (acceptEdits) or writes+commands (yolo); under default/plan they stay readonly (M6-T1)",
        "arg_no_stream": "Disable streaming output",
        "arg_verbose_tools": "Expand tool output by default; /collapse in-session switches back",
        "arg_resume": "Resume the last saved session",
        "arg_list_sessions": "List saved sessions and fork branches, then exit (use with --session-id <name> and --resume to restore)",
        "arg_fork_from": "Fork a new session from one message of --session-id and exit: message index (keep count, system=1) or message id (m-…)",
        "arg_new_session_id": "Name for the session created by --fork-from (optional, auto-named by default)",
        "arg_session_id": "Session name (default: latest)",
        "arg_print_config": "Print the resolved config and exit",
        "arg_setup": "Create the .minicc/ skeleton (permissions.json + web_token.json) and exit",
        "arg_doctor": "Run the workspace self-check and exit (no network, no model)",
        "arg_doctor_strict": "Like --doctor, but warnings are fatal too (CI risk gate)",
        "arg_stats": "Read-only rollup of workspace state (no network, no model)",
        "arg_digest": "Read-only repo archaeology: branch / commits / first commit / batch manuscripts (no network, no model)",
        "arg_capabilities": "Print the tool capability roster (JSON) and exit (no network, no model)",
        "arg_json": "Machine-readable JSON, paired with --doctor / --doctor-strict / --stats / --capabilities",
        "arg_version": "Print the version and exit; with --json outputs name/version JSON",
        # audit.py — authorization decision reasons
        "audit_perm_unreadable": "Cannot read permissions.json: {exc}",
        "audit_perm_deny_tool": "Cannot read permissions.json; denying first ({tool}): {error}",
        "audit_perm_deny_rule": "permissions.json deny rule blocked this operation ({tool})",
        "audit_perm_invalid": "Invalid permission_mode: {value!r} (default|plan|acceptEdits|yolo)",
        "audit_policy_unreadable": "Cannot read permissions.json; denying first ({policy_error})",
        "audit_deny_rule": "Denied by permissions.json deny rule",
        "audit_allow_rule": "Allowed by permissions.json allow rule",
        "audit_session_allow": "Allowed by this session's allowlist",
        "audit_git_reconly": "git_stage/git_commit need a human approval in-session; yolo / allow_changes / acceptEdits do not unlock them",
        "audit_yolo_readonly": "yolo session; tool allowed",
        "audit_yolo_writes": "yolo session; writes and commands allowed",
        "audit_task_network_readonly": "This task explicitly allowed read-only web access",
        "audit_task_network_missing": "Read-only web access needs this task's own permission",
        "audit_default_readonly": "Read-only tool allowed",
        "audit_plan_mode_write": "Plan mode allows read-only tools; write denied",
        "audit_network_needs_task": "This tool declares network ability; it needs this task's own web authorization",
        "audit_task_write": "This task explicitly allowed writes",
        "audit_task_write_missing": "Write tools need this task's explicit permission",
        "audit_plan_mode_exec": "Plan mode allows read-only tools; command denied",
        "audit_task_network_exec": "This task explicitly allowed network commands",
        "audit_task_network_exec_missing": "Network commands need their own task permission",
        "audit_safe_verification": "Restricted read-only verification command allowed",
        "audit_task_exec": "This task explicitly allowed command execution",
        "audit_task_exec_missing": "Command execution needs this task's explicit permission",
        "audit_unknown_risk": "Unknown tool risk; execution denied",
        # doctor.py — advice lines
        "doctor_python": "Upgrade to python>=3.11 (current: {major}.{minor}.{micro})",
        "doctor_reinstall": "Reinstall the wheel or `pip install -e .`",
        "doctor_write": "Check the directory's write permission",
        "doctor_owner": "Check the owner and permissions of .minicc/",
        # commands.py — command-file failure face
        "commands_undecodable": "Cannot decode the file",
        "commands_os_unreadable": "The OS refuses to read it",
        "commands_file_broken": "The definition file for custom command /{head} exists at the {scope} level, but {reason_text} ({path}: {detail}). This input will not go to the model as an ordinary message — fix the file first (save as UTF-8, or release whatever process holds it).",
        "commands_skills_header": "Available skills (names and summaries only; bodies are not pinned in context — read the SKILL.md with read_file when needed):",
        "commands_skills_dir": "Skill file directory: {path}",
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
