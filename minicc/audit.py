"""Machine-readable authorization policy for local agent tasks.

The policy is intentionally small and deterministic: it records why a tool was
allowed or denied without storing command arguments or credentials.  Tool
output remains untrusted and is redacted by the registry before it reaches the
task history.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .allowlist import match_session_allowlist
from .tools.bash import is_readonly_command, split_command_argv


# M3-T4: argv-aware network detection. The old substring blacklist missed
# ``pip3 install``, ``apt-get install nginx``, ``ssh``, ``nc``, ``rsync`` and
# matched inside unrelated text (``git log --grep="git clone"``).
NETWORK_EXECUTABLES = frozenset({
    "curl", "wget", "http", "httpie", "aria2c", "nc", "ncat", "netcat", "telnet",
    "ssh", "scp", "sftp", "rsync", "ftp", "tftp", "dig", "nslookup", "host",
    "invoke-webrequest", "invoke-restmethod", "iwr", "irm",
})
# Package managers / build tools that reach the network for specific verbs.
NETWORK_SUBCOMMANDS = {
    "pip": {"install", "download", "wheel", "search"},
    "pip3": {"install", "download", "wheel", "search"},
    # python/python3/py: only `-m pip|uv|poetry|conda` counts (special-cased
    # in command_uses_network); `python -m pytest` must stay non-network.
    "python": set(),
    "python3": set(),
    "py": set(),
    "uv": {"pip", "add", "sync", "tool", "run"},
    "npm": {"install", "i", "ci", "add", "publish", "update", "exec", "x"},
    "pnpm": {"install", "add", "i", "update", "dlx", "publish"},
    "yarn": {"add", "install", "upgrade", "publish", "dlx"},
    "apt": {"install", "update", "upgrade", "get"},
    "apt-get": {"install", "update", "upgrade"},
    "apk": {"add", "update", "upgrade"},
    "yum": {"install", "update", "upgrade"},
    "dnf": {"install", "update", "upgrade"},
    "brew": {"install", "upgrade", "update", "tap"},
    "choco": {"install", "upgrade"},
    "winget": {"install", "upgrade"},
    "scoop": {"install", "update"},
    "gem": {"install", "update"},
    "cargo": {"install", "add", "update", "publish", "login"},
    "go": {"get", "install", "mod", "download"},
    "dotnet": {"restore", "add", "tool", "nuget"},
    "git": {"clone", "fetch", "pull", "push", "remote", "submodule", "ls-remote"},
    "hg": {"clone", "pull", "push", "incoming"},
    "svn": {"checkout", "update", "commit", "export"},
    "docker": {"pull", "push", "login", "build"},
    "kubectl": {"apply", "create", "delete", "get", "logs", "exec"},
    "helm": {"install", "upgrade", "repo", "pull"},
    "mvn": {"dependency", "deploy"},
    "gradle": {"dependencies"},
    "npx": set(),  # npx always resolves from the registry
    "pipx": {"install", "run", "upgrade"},
    "conda": {"install", "update", "create"},
    "poetry": {"install", "add", "update", "publish"},
    "powershell": {"invoke-webrequest", "invoke-restmethod", "iwr", "irm"},
    "pwsh": {"invoke-webrequest", "invoke-restmethod", "iwr", "irm"},
}

# Wrappers whose arguments are themselves command lines: recurse into them so
# ``sudo curl …`` / ``cmd /c wget …`` / ``powershell -Command "pip install …"``
# cannot slip through by hiding the real executable one level down.
SHELL_WRAPPERS = frozenset({
    "cmd", "powershell", "pwsh", "sh", "bash", "zsh", "fish",
    "sudo", "doas", "runas", "wsl", "xargs", "env",
})

_PYTHON_EXECUTABLES = frozenset({"python", "python3", "py", "pythonw"})
_PYTHON_NETWORK_MODULES = frozenset({"pip", "pip3", "uv", "poetry", "conda"})

NETWORK_TOOL_NAMES = frozenset({"web_search", "webfetch"})


def tool_requires_authorization(
    tool: str,
    risk: str | None,
    capabilities: Iterable[str] = (),
) -> bool:
    """True when the agent loop must consult ``should_allow`` before running.

    Network tools are registered as ``readonly`` so they stay off the write
    path, but they still need the task-level ``allow_network`` gate. Matching
    only ``write``/``exec`` (plus a hardcoded ``web_search`` name) used to
    let ``webfetch`` skip the policy.

    A plugin that *declares* the ``network`` capability (M8-T3) is routed
    through the same gate, so a third-party readonly tool cannot reach the
    internet without the task's network grant.
    """
    if risk in {"write", "exec"}:
        return True
    return _is_network_tool(tool, capabilities)


def _is_network_tool(tool: str, capabilities: Iterable[str] = ()) -> bool:
    return str(tool or "") in NETWORK_TOOL_NAMES or "network" in set(capabilities or ())

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


def _executable_name(token: str) -> str:
    name = str(token).replace("\\", "/").rsplit("/", 1)[-1].casefold()
    for suffix in (".exe", ".cmd", ".bat", ".com"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def command_uses_network(command: object) -> bool:
    """Argv-aware network detection (M3-T4).

    Every shell segment is inspected independently: bare executables in
    ``NETWORK_EXECUTABLES`` always count; package/build tools count only when
    one of their network verbs appears as a whole token (``pip3 install``
    yes; ``git log --grep="git clone"`` no; ``git  clone`` with doubled
    space yes). Shell wrappers recurse into their arguments so ``sudo curl``
    cannot hide the real executable.
    """
    for argv in split_command_argv(str(command or "")):
        if not argv:
            continue
        executable = _executable_name(argv[0])
        if executable in NETWORK_EXECUTABLES:
            return True
        if executable == "npx":
            return True
        rest = [token.casefold() for token in argv[1:]]
        if executable in _PYTHON_EXECUTABLES:
            for position, token in enumerate(rest):
                if token == "-m" and position + 1 < len(rest):
                    module = rest[position + 1].rsplit(".", 1)[-1]
                    if module in _PYTHON_NETWORK_MODULES:
                        return True
        verbs = NETWORK_SUBCOMMANDS.get(executable)
        if verbs and any(token in verbs for token in rest):
            return True
        if executable in SHELL_WRAPPERS:
            for token in rest:
                if command_uses_network(token):
                    return True
    return False


def authorize_tool(
    tool: str,
    risk: str | None,
    arguments: dict[str, Any],
    *,
    allow_changes: bool,
    allow_network: bool,
    permission_mode: str = "default",
    session_id: str = "",
    workspace: Path | None = None,
    capabilities: Iterable[str] = (),
) -> AuthorizationDecision:
    """Return an auditable authorization decision before executing a tool.

    ``capabilities`` is the tool's own declaration from
    :class:`minicc.tools.registry.ToolSpec`; it can only add constraints, and
    a tool that declares nothing behaves exactly as before.
    """
    mode = normalize_permission_mode(permission_mode)
    declared = set(capabilities or ())
    network_tool = _is_network_tool(tool, declared)

    def _allowlist_override(denied: AuthorizationDecision) -> AuthorizationDecision:
        if mode == "plan":
            return denied
        if workspace is None or not str(session_id or "").strip():
            return denied
        if match_session_allowlist(workspace, session_id, tool, arguments):
            return AuthorizationDecision(
                True,
                denied.risk,
                "本会话 allowlist 已放行",
                "session_allowlist",
            )
        return denied

    if mode == "yolo":
        if risk == "readonly" or tool in NETWORK_TOOL_NAMES:
            return AuthorizationDecision(True, risk or "unknown", "任务为 yolo 模式，工具已放行", "task_yolo")
        return AuthorizationDecision(True, risk or "unknown", "任务为 yolo 模式，写入与命令已放行", "task_yolo")
    if network_tool and risk == "readonly":
        if allow_network:
            return AuthorizationDecision(True, "network_readonly", "本任务已明确授权联网查询", "task_network")
        return _allowlist_override(
            AuthorizationDecision(False, "network_readonly", "联网查询需要当前任务单独授权", "missing_task_network")
        )
    if risk == "readonly":
        return AuthorizationDecision(True, "readonly", "只读工具已允许", "default_readonly")
    if risk == "write":
        if mode == "plan":
            return AuthorizationDecision(False, "write", "计划模式只允许只读工具，写入已拒绝", "plan_mode_write")
        if network_tool and not allow_network:
            return _allowlist_override(
                AuthorizationDecision(False, "write", "该工具声明了联网能力，需要先获得本任务的联网授权", "missing_task_network")
            )
        if mode == "acceptEdits" or allow_changes:
            return AuthorizationDecision(True, "write", "本任务已明确授权写入", "task_write")
        return _allowlist_override(
            AuthorizationDecision(False, "write", "写入工具需要当前任务明确授权", "missing_task_write")
        )
    if risk == "exec":
        if mode == "plan":
            return AuthorizationDecision(False, "exec", "计划模式只允许只读工具，命令已拒绝", "plan_mode_exec")
        command = arguments.get("command", "")
        if command_uses_network(command) or network_tool:
            if allow_changes and allow_network:
                return AuthorizationDecision(True, "network_exec", "本任务已明确授权网络命令", "task_network")
            return _allowlist_override(
                AuthorizationDecision(False, "network_exec", "网络命令需要单独授权", "missing_task_network")
            )
        if tool == "bash" and is_readonly_command(str(command)):
            return AuthorizationDecision(True, "readonly_exec", "受限只读验证命令已允许", "safe_verification")
        if allow_changes:
            return AuthorizationDecision(True, "exec", "本任务已明确授权命令执行", "task_exec")
        return _allowlist_override(
            AuthorizationDecision(False, "exec", "命令执行需要当前任务明确授权", "missing_task_exec")
        )
    return AuthorizationDecision(False, "unknown", "未知工具风险，已拒绝执行", "unknown_risk")


__all__ = [
    "NETWORK_TOOL_NAMES",
    "PERMISSION_MODES",
    "AuthorizationDecision",
    "authorize_tool",
    "command_uses_network",
    "normalize_permission_mode",
    "tool_requires_authorization",
]
