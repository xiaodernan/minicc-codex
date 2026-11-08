"""M8-T633 — hook decision vocabulary (allow/deny) has one home.

Hook execution produces/consumes `allow`/`deny` decisions in `minicc.hooks` and
`minicc.agent.loop` reads hook entry decisions. Bare literals duplicate the
same hook-domain fact. The one home is `minicc.hooks`. Distinct from
permission-rule decision codes (e.g. `permission_rule_deny` in audit).
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = PACKAGE / "hooks.py"
SCOPED = {HOME, PACKAGE / "agent" / "loop.py"}

DECISIONS = {"allow", "deny"}
CONST_NAMES = {"HOOK_DECISION_ALLOW", "HOOK_DECISION_DENY"}


def test_the_home_defines_hook_decision_constants() -> None:
    import minicc.hooks as h

    assert h.HOOK_DECISION_ALLOW == "allow"
    assert h.HOOK_DECISION_DENY == "deny"


def _allowed(node: ast.Constant, parents: dict[int, ast.AST]) -> bool:
    parent = parents.get(id(node))
    if isinstance(parent, ast.Assign):
        for t in parent.targets:
            if isinstance(t, ast.Name) and t.id in CONST_NAMES:
                return True
    return False


def test_no_bare_hook_decision_literals_in_scoped_modules() -> None:
    offenders: list[str] = []
    for path in sorted(SCOPED):
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(path))
        parents: dict[int, ast.AST] = {}
        lines = src.splitlines()
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parents[id(child)] = parent
        rel = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or node.value not in DECISIONS:
                continue
            if path == HOME and _allowed(node, parents):
                continue
            if path != HOME:
                line = lines[node.lineno - 1] if node.lineno <= len(lines) else ""
                # only hook-decision consumption in loop
                if "decision" not in line.lower() and "hook" not in line.lower():
                    continue
            offenders.append(f"{rel}:{node.lineno}: {lines[node.lineno-1].strip()[:160]}")
    offenders = sorted(set(offenders))
    assert offenders == [], (
        "bare hook decision literal - ask HOOK_DECISION_* from minicc.hooks:\n"
        + "\n".join(offenders)
    )
