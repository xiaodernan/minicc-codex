"""M8-T630 — the bash tool name has one home.

The built-in shell tool is identified as `"bash"` across authorization,
allowlist, permissions, CLI/web dispatch, and agent loop/policy/completion
logic. Bare literals in tool/name comparison contexts duplicate the same fact.
The one home is `minicc.tools.names`.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = PACKAGE / "tools" / "names.py"
SCOPED = {
    PACKAGE / "agent" / "completion.py",
    PACKAGE / "agent" / "loop.py",
    PACKAGE / "agent" / "tool_policy.py",
    PACKAGE / "allowlist.py",
    PACKAGE / "audit.py",
    PACKAGE / "main.py",
    PACKAGE / "permissions.py",
    PACKAGE / "web.py",
}


def test_the_home_defines_tool_name_bash() -> None:
    from minicc.tools.names import TOOL_NAME_BASH

    assert TOOL_NAME_BASH == "bash"


def _is_tool_name_context(line: str) -> bool:
    lower = line.lower()
    return "tool" in lower or "name" in lower


def test_no_bare_bash_tool_name_literals_in_scoped_modules() -> None:
    offenders: list[str] = []
    for path in sorted(SCOPED):
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(path))
        lines = src.splitlines()
        rel = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or node.value != "bash":
                continue
            if path == HOME:
                continue
            line = lines[node.lineno - 1] if node.lineno <= len(lines) else ""
            if not _is_tool_name_context(line):
                continue
            offenders.append(f"{rel}:{node.lineno}: {line.strip()[:160]}")
    offenders = sorted(set(offenders))
    assert offenders == [], (
        "bare bash tool-name literal in scoped modules - ask TOOL_NAME_BASH from minicc.tools.names:\n"
        + "\n".join(offenders)
    )
