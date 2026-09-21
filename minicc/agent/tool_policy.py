"""Authorization and verification policy helpers for the agent loop.

Kept separate from ``loop.py`` so the giant turn function can ask two
stable questions without inlining string lists:

- does this tool need ``should_allow`` before it runs?
- does this successful tool result count as post-write verification?
"""

from __future__ import annotations

from typing import Any
import re
from .check_commands import command_parts, checker_invocation

from ..audit import NETWORK_TOOL_NAMES, tool_requires_authorization
from ..tools.bash import split_command_argv

# M4-T1: a workspace write is not only the four explicit write tools. An agent
# that runs ``sed -i`` or ``python patch.py`` mutates the workspace just as much,
# so ``verification_required`` must trip for those too. Kept here (next to
# ``is_verification_evidence``) so loop.py asks one stable question.
WRITE_TOOL_NAMES = frozenset({"write_file", "edit_file", "worktree_create", "worktree_remove"})

# Programs whose normal use rewrites the filesystem.
_MUTATING_PROGRAMS = frozenset({
    "mv", "cp", "rm", "rmdir", "mkdir", "touch", "dd", "ln", "shred",
    "truncate", "tee", "patch", "rsync", "install", "unzip", "zip",
    "tar", "gzip", "gunzip", "bzip2", "xz", "7z", "make", "cmake", "cargo",
})
_GIT_MUTATING = frozenset({
    "add", "rm", "mv", "checkout", "restore", "reset", "clean", "commit",
    "apply", "stash", "rebase", "merge", "cherry-pick", "revert",
})
_PKG_MUTATING = frozenset({
    "install", "uninstall", "update", "upgrade", "add", "remove", "ci", "build", "link",
})
_INTERPRETERS = frozenset({
    "python", "python3", "py", "node", "ruby", "perl", "php",
    "bash", "sh", "zsh", "dash", "ksh",
})
_SCRIPT_EXT = (".py", ".js", ".mjs", ".cjs", ".sh", ".rb", ".pl", ".php", ".ts")


def _program_basename(token: str) -> str:
    return token.replace("\\", "/").rsplit("/", 1)[-1].casefold().removesuffix(".exe")


def command_may_modify_workspace(command: str) -> bool:
    """Conservative: True when a bash command could rewrite the workspace.

    Over-reporting only forces an extra verification pass; under-reporting lets
    a real write skip the verifier, so the heuristic errs toward True.
    """
    text = str(command or "")
    if not text.strip():
        return False
    # Output redirection writes a file no matter the program.
    if ">" in text:
        return True
    for argv in split_command_argv(text):
        if not argv:
            continue
        program = _program_basename(argv[0])
        rest = argv[1:]
        if program == "sed":
            if any(tok == "-i" or tok.startswith("-i") or tok.startswith("--in-place") for tok in rest):
                return True
            continue
        if program in _MUTATING_PROGRAMS:
            return True
        if program == "git" and rest and rest[0] in _GIT_MUTATING:
            return True
        if program in {"npm", "yarn", "pnpm", "pip", "pip3", "uv", "poetry", "go"} and any(
            tok in _PKG_MUTATING for tok in rest
        ):
            return True
        if program in _INTERPRETERS:
            flags = {tok for tok in rest if tok.startswith("-")}
            # ``-c``/``-m`` run inline code or a module, not a workspace script.
            if "-c" in flags or "-m" in flags:
                continue
            if any(tok.endswith(_SCRIPT_EXT) for tok in rest if not tok.startswith("-")):
                return True
    return False


def is_workspace_write(tool: str, arguments: dict[str, Any] | None, status: str) -> bool:
    """True when a successful tool call actually changed (or may change) files."""
    if status != "ok":
        return False
    if tool in WRITE_TOOL_NAMES:
        return True
    if tool == "bash":
        return command_may_modify_workspace(str((arguments or {}).get("command") or ""))
    return False


# Only bash evidence can clear ``verification_required``. git_status / read_file
# / grep are useful inspection but they do not prove the change works.
VERIFY_COMMAND_MARKERS = (
    "pytest",
    "unittest",
    "npm test",
    "npm run test",
    "pnpm test",
    "pnpm run test",
    "yarn test",
    "npm run check:",
    "npm run typecheck",
    "npm run lint",
    "npm run build",
    "ruff ",
    "ruff.exe",
    "mypy",
    "pyright",
    "tsc",
    "node --check",
    "python -m compileall",
    "python3 -m compileall",
)


def is_verification_evidence(tool: str, arguments: dict[str, Any] | None, status: str) -> bool:
    """True when a successful tool call is actual verification, not inspection."""
    if status != "ok" or tool != "bash":
        return False
    command = str((arguments or {}).get("command") or "")
    if not command.strip():
        return False
    # Merely printing a command, collecting tests or asking for --help cannot
    # prove anything about a change. Only actual checker executables count.
    if any(char in command for char in "&|;<>`$()%^!\n\r"):
        return False
    try:
        parts = command_parts(command)
    except ValueError:
        return False
    if not parts or any(part.split("=", 1)[0].lower() in {"--collect-only", "--co", "--help", "-h", "--version", "--showconfig", "--show-config", "--show-settings", "--show-files", "--listfilesonly", "--explainfiles", "--init"} for part in parts):
        return False
    executable, arguments = checker_invocation(command)
    if executable in {"pytest", "unittest", "mypy", "pyright", "tsc", "compileall"}:
        return True
    if executable == "ruff":
        return bool(arguments and (arguments[0] == "check" and "--fix" not in arguments or arguments[0] == "format" and "--check" in arguments))
    if executable == "node":
        return len(arguments) == 2 and arguments[0] == "--check"
    if executable in {"npm", "pnpm", "yarn"}:
        script = arguments[1] if len(arguments) >= 2 and arguments[0] == "run" else arguments[0] if arguments else ""
        return bool(re.fullmatch(r"(?:test(?::[\w-]+)?|check(?::[\w-]+)?|typecheck|lint|build)", script))
    return False


__all__ = [
    "NETWORK_TOOL_NAMES",
    "VERIFY_COMMAND_MARKERS",
    "WRITE_TOOL_NAMES",
    "command_may_modify_workspace",
    "is_verification_evidence",
    "is_workspace_write",
    "tool_requires_authorization",
]
