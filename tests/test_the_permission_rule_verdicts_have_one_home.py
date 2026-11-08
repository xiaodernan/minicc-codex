"""M8-T634 — permission rule verdict/side vocabulary has one home.

`minicc.permissions` produces rule-match verdicts (`allow`/`deny`/`None`) and
uses `allow`/`deny` rule-side keys. `minicc.audit` consumes `match_rules`
verdicts. Bare literals duplicate the same permission-rule fact.

Distinct from hook decisions (hooks domain) and from user approval decisions
(`APPROVAL_DECISIONS` in audit, different fact).
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = PACKAGE / "permissions.py"
SCOPED = {HOME, PACKAGE / "audit.py"}

VALS = {"allow", "deny"}
CONST_NAMES = {"PERMISSION_RULE_VERDICT_ALLOW", "PERMISSION_RULE_VERDICT_DENY"}


def test_the_home_defines_permission_rule_verdict_constants() -> None:
    import minicc.permissions as p

    assert p.PERMISSION_RULE_VERDICT_ALLOW == "allow"
    assert p.PERMISSION_RULE_VERDICT_DENY == "deny"


def _allowed(node: ast.Constant, parents: dict[int, ast.AST]) -> bool:
    parent = parents.get(id(node))
    if isinstance(parent, ast.Assign):
        for t in parent.targets:
            if isinstance(t, ast.Name) and t.id in CONST_NAMES:
                return True
    return False


def _is_permission_verdict_context(path: Path, node: ast.AST, src: str, parents: dict[int, ast.AST]) -> bool:
    if path == HOME:
        return True
    # audit.py: only match_rules verdict comparisons and verdict variable comparisons;
    # exclude APPROVAL_DECISIONS / PERMITTING_APPROVAL_DECISIONS definitions.
    line = src.splitlines()[node.lineno - 1] if node.lineno <= len(src.splitlines()) else ""
    if "APPROVAL_DECISIONS" in src.splitlines()[max(0, node.lineno - 3):node.lineno + 1].__str__():
        return False
    # find enclosing context
    if "match_rules" in line or "verdict" in line:
        # but not authorization code strings or approval constants
        if "APPROVAL" in line or "permission_rule_" in line:
            return False
        return True
    return False


def test_no_bare_permission_rule_verdict_literals_in_scoped_modules() -> None:
    offenders: list[str] = []
    for path in sorted(SCOPED):
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(path))
        parents: dict[int, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parents[id(child)] = parent
        rel = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or node.value not in VALS:
                continue
            if path == HOME and _allowed(node, parents):
                continue
            if not _is_permission_verdict_context(path, node, src, parents):
                continue
            line = src.splitlines()[node.lineno - 1].strip()[:160]
            offenders.append(f"{rel}:{node.lineno}: {line}")
    offenders = sorted(set(offenders))
    assert offenders == [], (
        "bare permission-rule verdict/side literal - ask PERMISSION_RULE_VERDICT_* "
        "from minicc.permissions (distinct from hook/approval decisions):\n"
        + "\n".join(offenders)
    )
