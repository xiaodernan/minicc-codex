"""Machine-readable authorization policy for local agent tasks.

The policy is intentionally small and deterministic: it records why a tool was
allowed or denied without storing command arguments or credentials.  Tool
output remains untrusted and is redacted by the registry before it reaches the
task history.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .tools.bash import is_readonly_command


NETWORK_COMMAND_MARKERS = (
    "curl", "wget", "invoke-webrequest", "invoke-restmethod", "git clone",
    "git fetch", "git pull", "npm install", "pnpm install", "yarn add",
    "pip install", "uv pip install",
)

NETWORK_TOOL_NAMES = frozenset({"web_search", "webfetch"})

# Task-level permission modes, aligned with Claude Code:
# - default:     readonly auto; writes/exec need the task write authorization.
# - plan:        research mode; writes and exec are denied outright.
# - acceptEdits: file writes are auto-accepted; exec still needs authorization.
# - yolo:        everything allowed for this task (implies both flags).
PERMISSION_MODES = frozenset({"default", "plan", "acceptEdits", "yolo"})
# lowercase aliases for wire/UI input (camelCase is accepted too)
_PERMISSION_MODE_ALIASES = {
    "": "default",
    "normal": "default",
    "standard": "default",
    "default": "default",
    "plan": "plan",
    "acceptedits": "acceptEdits",
    "accept-edits": "acceptEdits",
    "accept_edits": "acceptEdits",
    "yolo": "yolo",
}


def normalize_permission_mode(value: object) -> str:
    raw = str(value or "default").strip().lower()
    mode = _PERMISSION_MODE_ALIASES.get(raw)
    if mode is None:
        raise ValueError(f"permission_mode 非法: {value!r} (default|plan|acceptEdits|yolo)")
    return mode


@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    risk: str
    reason: str
    authorization: str

    def to_event(self, tool: str) -> dict[str, str]:
        return {
            "kind": "authorization",
            "name": tool,
            "status": "ok" if self.allowed else "denied",
            "phase": "permission",
            "code": "tool_authorized" if self.allowed else "tool_denied_by_policy",
            "summary": self.reason,
            "risk": self.risk,
            "authorization": self.authorization,
        }


def command_uses_network(command: object) -> bool:
    normalized = str(command or "").casefold()
    return any(marker in normalized for marker in NETWORK_COMMAND_MARKERS)


def authorize_tool(
    tool: str,
    risk: str | None,
    arguments: dict[str, Any],
    *,
    allow_changes: bool,
    allow_network: bool,
    permission_mode: str = "default",
) -> AuthorizationDecision:
    """Return an auditable authorization decision before executing a tool."""
    mode = normalize_permission_mode(permission_mode)
    if mode == "yolo":
        if risk == "readonly" or tool in NETWORK_TOOL_NAMES:
            return AuthorizationDecision(True, risk or "unknown", "任务为 yolo 模式，工具已放行", "task_yolo")
        return AuthorizationDecision(True, risk or "unknown", "任务为 yolo 模式，写入与命令已放行", "task_yolo")
    if tool in NETWORK_TOOL_NAMES:
        if allow_network:
            return AuthorizationDecision(True, "network_readonly", "本任务已明确授权联网查询", "task_network")
        return AuthorizationDecision(False, "network_readonly", "联网查询需要当前任务单独授权", "missing_task_network")
    if risk == "readonly":
        return AuthorizationDecision(True, "readonly", "只读工具已允许", "default_readonly")
    if risk == "write":
        if mode == "plan":
            return AuthorizationDecision(False, "write", "计划模式只允许只读工具，写入已拒绝", "plan_mode_write")
        if mode == "acceptEdits" or allow_changes:
            return AuthorizationDecision(True, "write", "本任务已明确授权写入", "task_write")
        return AuthorizationDecision(False, "write", "写入工具需要当前任务明确授权", "missing_task_write")
    if risk == "exec":
        if mode == "plan":
            return AuthorizationDecision(False, "exec", "计划模式只允许只读工具，命令已拒绝", "plan_mode_exec")
        command = arguments.get("command", "")
        if command_uses_network(command):
            if allow_changes and allow_network:
                return AuthorizationDecision(True, "network_exec", "本任务已明确授权网络命令", "task_network")
            return AuthorizationDecision(False, "network_exec", "网络命令需要单独授权", "missing_task_network")
        if tool == "bash" and is_readonly_command(str(command)):
            return AuthorizationDecision(True, "readonly_exec", "受限只读验证命令已允许", "safe_verification")
        if allow_changes:
            return AuthorizationDecision(True, "exec", "本任务已明确授权命令执行", "task_exec")
        return AuthorizationDecision(False, "exec", "命令执行需要当前任务明确授权", "missing_task_exec")
    return AuthorizationDecision(False, "unknown", "未知工具风险，已拒绝执行", "unknown_risk")


__all__ = [
    "PERMISSION_MODES",
    "AuthorizationDecision",
    "authorize_tool",
    "command_uses_network",
    "normalize_permission_mode",
]
