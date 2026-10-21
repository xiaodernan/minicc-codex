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

from .allowlist import match_session_allowlist, path_rule_matches
from .permissions import load_permission_rules, match_permission_rule
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
    *,
    arguments: dict[str, Any] | None = None,
) -> bool:
    """True when the agent loop must consult ``should_allow`` before running.

    Network tools are registered as ``readonly`` so they stay off the write
    path, but they still need the task-level ``allow_network`` gate. Matching
    only ``write``/``exec`` (plus a hardcoded ``web_search`` name) used to
    let ``webfetch`` skip the policy.

    A plugin that *declares* the ``network`` capability (M8-T3) is routed
    through the same gate, so a third-party readonly tool cannot reach the
    internet without the task's network grant.

    M8-T304: the arguments take part in the question, because one tool's
    target depends on them - a call that writes outside the workspace is a
    write, whatever the tool declared.
    """
    if effective_risk(tool, risk, arguments) in {"write", "exec"}:
        return True
    return is_network_tool(tool, capabilities)


def is_network_tool(tool: str, capabilities: Iterable[str] = ()) -> bool:
    """True when this tool reaches the network.

    M8-T307: the rule has **two** halves - the well-known names, and the
    ``network`` **capability** a tool may declare (M8-T3).  The gate asked
    both; the agent loop asked only the names, at four places:

    * a network call's result was **cached and replayed** as if it were a
      local read (the cache exists to reuse *reproducible* observations,
      and a network answer is neither);
    * a failing network tool did not count toward the **circuit breaker**,
      so a plugin that kept failing was retried for ever.

    Both are the same defect as M8-T303 (a stale second copy of a rule):
    the copy that nobody maintained was the weaker one.  The rule now has
    one home, and the loop asks it.
    """
    return str(tool or "") in NETWORK_TOOL_NAMES or "network" in set(capabilities or ())


def tool_denied_by_rule(
    workspace: Path | str | None,
    tool: str,
    arguments: dict[str, Any] | None = None,
) -> bool:
    """True when a ``permissions.json`` deny rule covers this call.

    M8-T267: ``tool_requires_authorization`` only fires for write/exec/network
    risks, so a readonly call never reached the gate - and the deny rules live
    inside it.  A deny rule on ``secrets/*`` therefore protected nothing on
    the read path, even though the Web face already documented the opposite
    ("denying a path like ``.env`` blocks reads too").

    This is the read-side half of that promise: the caller asks the rule
    directly, without asking the user for a verdict.  A deny rule is an
    absolute veto, not a question.
    """
    if not workspace:
        return False
    try:
        return match_permission_rule(Path(workspace), tool, arguments or {}) == "deny"
    except OSError:
        return False


def deny_rule_names_paths(workspace: Path | str | None) -> bool:
    """True when the deny side carries a path rule at all.

    M8-T290: a workspace-wide read - a diff of everything - carries the
    content of every path, including the ones a deny rule covers.  Such a
    read therefore has to be refused whenever the deny side names any path,
    even though no particular path was asked for.
    """
    if not workspace:
        return False
    try:
        rules, _error = load_permission_rules(Path(workspace))
    except OSError:
        return False
    return bool(rules["deny"]["paths"])


#: M8-T338: the tools whose own target can be the **whole workspace** - the
#: reads that carry the content (or the names) of every path, including the
#: ones a deny rule covers.
WORKSPACE_WIDE_READ_TOOLS = frozenset({"git_diff", "grep", "tree"})


def path_rule_denies_call(
    workspace: Path | str | None,
    tool: str,
    arguments: dict[str, Any] | None = None,
) -> bool:
    """True when the deny side refuses this call for a **path** reason.

    Two halves, one verdict:

    * the call's **own target** is denied (M8-T267) - a deny rule on
      ``secrets/*`` refuses a read of ``secrets/k.txt``;
    * the call is a **workspace-wide** read (M8-T290) - ``git_diff`` without
      a path returns the whole working-tree diff, ``grep``'s path is a
      directory, ``tree`` lists everything - so it carries the denied paths
      too and has to be refused whenever the deny side names any path.

    M8-T338: this rule had **one** reader - the model's own call, inline in
    the agent loop - while the agent's own **recovery probe** ran a
    workspace-wide ``git_diff`` and ``tree`` without asking, and the probe's
    results went straight into the conversation the model reads.  The rule now
    has one home, and every reader asks it.
    """
    if not workspace:
        return False
    args = arguments if isinstance(arguments, dict) else {}
    if tool_denied_by_rule(workspace, tool, args):
        return True
    if str(tool or "") not in WORKSPACE_WIDE_READ_TOOLS:
        return False
    return deny_rule_names_paths(workspace)


def _pattern_covers_container(pattern: str, rel: str) -> bool:
    """True when a deny path pattern covers this path as its **container**.

    A pattern like ``data/*`` denies everything under ``data/``, so the
    directory itself is part of what the rule protects - listing it would
    point at the protected container.  A pattern that names one file
    (``data/secret.txt``) does not: the directory around it holds other
    files the rule never mentioned.
    """
    head, sep, tail = str(pattern or "").rpartition("/")
    if not sep or not head:
        return False
    if not any(ch in tail for ch in "*?["):
        return False
    return rel == head or rel.startswith(head + "/")


def deny_rule_covers_path(workspace: Path | str | None, rel_path: str) -> bool:
    """True when the deny side covers this workspace-relative path.

    M8-T337: the Web face's file tree is a read of the workspace, and a deny
    rule has to reach it.  The preview and diff routes were fixed in M8-T290;
    the tree route was missed - so a browser panel listed the very paths
    ``permissions.json`` denies, while the agent's own ``tree`` call was
    refused outright by the same rule.

    The verdict is asked per entry, and a container directory is covered too
    (see :func:`_pattern_covers_container`): the point is that a denied path
    is not *visible* through any surface, not that the panel dies.
    """
    if not workspace or not rel_path:
        return False
    try:
        rules, _error = load_permission_rules(Path(workspace))
    except OSError:
        return False
    patterns = rules["deny"]["paths"]
    if not patterns:
        return False
    rel = str(rel_path).replace("\\", "/").strip()
    if not rel:
        return False
    if path_rule_matches(rel, patterns):
        return True
    return any(_pattern_covers_container(pattern, rel) for pattern in patterns)


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


def _writes_outside_workspace(tool: str, arguments: dict[str, Any] | None) -> bool:
    """True when this call's target is **outside** the workspace.

    M8-T304: a tool's target is usually fixed by the tool itself, but
    ``memory_write`` picks between the workspace and the user's home by an
    argument.  The tool is registered as ``readonly`` because the project
    scope writes agent state *inside* the workspace - so the write gate
    never saw the other scope, and the agent appended to a file in the
    user's home (shared by every project) with no prompt at all.

    Only the argument-carrying case is handled here.  A tool that writes
    outside the workspace has to say so; this one says it by argument.
    """
    if tool != "memory_write":
        return False
    scope = str((arguments or {}).get("scope") or "").strip().lower()
    return scope == "user"


def effective_risk(
    tool: str,
    risk: str | None,
    arguments: dict[str, Any] | None = None,
) -> str:
    """The risk a call **actually** carries.

    M8-T304: a tool's declared risk is usually the whole story, but
    ``memory_write``'s target depends on an argument, and its ``user`` scope
    writes into the user's home - outside the workspace, and shared by every
    project.  That is a write whatever the tool says, so the declared risk
    is not the whole story and every consumer has to ask this question the
    same way.
    """
    if risk == "readonly" and _writes_outside_workspace(tool, arguments):
        return "write"
    return risk or "unknown"


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
    # M7-T3 promises that a deny rule is absolute: it short-circuits before the
    # interactive prompt and no task flag overrides it. That promise only holds
    # where the rule is asked, and authorize_tool never asked it -- so the CLI
    # gate and the plan-node gate executed tools the checked-in project policy
    # refuses, and audited the reason as default_readonly or task_yolo. The veto
    # belongs in the shared decision function, above every flag branch.
    if workspace is not None and match_permission_rule(workspace, tool, arguments) == "deny":
        return AuthorizationDecision(
            False,
            risk or "unknown",
            "permissions.json deny 规则拒绝",
            "permission_rule_deny",
        )
    mode = normalize_permission_mode(permission_mode)
    declared = set(capabilities or ())
    network_tool = is_network_tool(tool, declared)
    # M8-T304: a call that writes outside the workspace is judged as the
    # write it is - the plan mode's "read only" promise, and the write
    # grant, both have to reach it.  The tool's declared risk cannot see
    # this, because the target depends on an argument.
    risk = effective_risk(tool, risk, arguments)

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
    "WORKSPACE_WIDE_READ_TOOLS",
    "AuthorizationDecision",
    "authorize_tool",
    "command_uses_network",
    "deny_rule_covers_path",
    "deny_rule_names_paths",
    "effective_risk",
    "is_network_tool",
    "normalize_permission_mode",
    "path_rule_denies_call",
    "tool_denied_by_rule",
    "tool_requires_authorization",
]
