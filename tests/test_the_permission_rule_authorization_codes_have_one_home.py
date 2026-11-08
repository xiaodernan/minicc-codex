"""M8-T625 — permission-rule/user-denied authorization codes have one home.

Authorization decision codes `permission_rule_allow`, `permission_rule_deny`,
and `user_denied` are part of the authorization vocabulary owned by
`minicc.audit`. Audit produces rule decisions; web consumes `permission_rule_allow`
and reports `user_denied` on approval denial. Bare literals duplicate the fact.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = PACKAGE / "audit.py"
SCOPED = {HOME, PACKAGE / "web.py"}

CODES = {"permission_rule_allow", "permission_rule_deny", "user_denied"}
CONST_NAMES = {
    "AUTHORIZATION_PERMISSION_RULE_ALLOW",
    "AUTHORIZATION_PERMISSION_RULE_DENY",
    "AUTHORIZATION_USER_DENIED",
}


def test_the_home_defines_permission_rule_authorization_constants() -> None:
    import minicc.audit as a

    assert a.AUTHORIZATION_PERMISSION_RULE_ALLOW == "permission_rule_allow"
    assert a.AUTHORIZATION_PERMISSION_RULE_DENY == "permission_rule_deny"
    assert a.AUTHORIZATION_USER_DENIED == "user_denied"


def _allowed(node: ast.Constant, parents: dict[int, ast.AST]) -> bool:
    parent = parents.get(id(node))
    if isinstance(parent, ast.Assign):
        for t in parent.targets:
            if isinstance(t, ast.Name) and t.id in CONST_NAMES:
                return True
    return False


def test_no_bare_permission_rule_authorization_literals_in_scoped_modules() -> None:
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
            if not isinstance(node, ast.Constant) or node.value not in CODES:
                continue
            if path == HOME and _allowed(node, parents):
                continue
            offenders.append(f"{rel}:{node.lineno} bare {node.value!r}")
    offenders = sorted(set(offenders))
    assert offenders == [], (
        "bare permission-rule/user-denied authorization literals - ask "
        "AUTHORIZATION_PERMISSION_RULE_* / AUTHORIZATION_USER_DENIED from minicc.audit:\n"
        + "\n".join(offenders)
    )
