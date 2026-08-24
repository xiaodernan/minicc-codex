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

NETWORK_TOOL_NAMES = frozenset({"web_search"})


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
) -> AuthorizationDecision:
    """Return an auditable authorization decision before executing a tool."""
    if tool in NETWORK_TOOL_NAMES:
        if allow_network:
            return AuthorizationDecision(True, "network_readonly", "本任务已明确授权联网查询", "task_network")
        return AuthorizationDecision(False, "network_readonly", "联网查询需要当前任务单独授权", "missing_task_network")
    if risk == "readonly":
        return AuthorizationDecision(True, "readonly", "只读工具已允许", "default_readonly")
    if risk == "write":
        if allow_changes:
            return AuthorizationDecision(True, "write", "本任务已明确授权写入", "task_write")
        return AuthorizationDecision(False, "write", "写入工具需要当前任务明确授权", "missing_task_write")
    if risk == "exec":
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


__all__ = ["AuthorizationDecision", "authorize_tool", "command_uses_network"]
