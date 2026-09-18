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
    "is_verification_evidence",
    "tool_requires_authorization",
]
