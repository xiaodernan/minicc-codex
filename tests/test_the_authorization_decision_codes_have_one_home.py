"""M8-T626 — authorization decision codes have one home.

AuthorizationDecision.authorization code names (plan/mode/task/rule outcomes and
related allow/deny codes) are owned by `minicc.audit`. Bare literals in audit,
main, and web duplicate the same fact.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = PACKAGE / "audit.py"
SCOPED = {HOME, PACKAGE / "main.py", PACKAGE / "web.py"}

CODES = {
    "unknown_risk",
    "task_yolo",
    "default_readonly",
    "permission_policy_unreadable",
    "session_allowlist",
    "task_network",
    "plan_mode_write",
    "task_write",
    "plan_mode_exec",
    "safe_verification",
    "task_exec",
    "user_approved",
}
CONST_NAMES = {
    "AUTHORIZATION_UNKNOWN_RISK",
    "AUTHORIZATION_TASK_YOLO",
    "AUTHORIZATION_DEFAULT_READONLY",
    "AUTHORIZATION_PERMISSION_POLICY_UNREADABLE",
    "AUTHORIZATION_SESSION_ALLOWLIST",
    "AUTHORIZATION_TASK_NETWORK",
    "AUTHORIZATION_PLAN_MODE_WRITE",
    "AUTHORIZATION_TASK_WRITE",
    "AUTHORIZATION_PLAN_MODE_EXEC",
    "AUTHORIZATION_SAFE_VERIFICATION",
    "AUTHORIZATION_TASK_EXEC",
    "AUTHORIZATION_USER_APPROVED",
}


def test_the_home_defines_authorization_decision_code_constants() -> None:
    import minicc.audit as a

    assert a.AUTHORIZATION_UNKNOWN_RISK == "unknown_risk"
    assert a.AUTHORIZATION_TASK_YOLO == "task_yolo"
    assert a.AUTHORIZATION_DEFAULT_READONLY == "default_readonly"
    assert a.AUTHORIZATION_PERMISSION_POLICY_UNREADABLE == "permission_policy_unreadable"
    assert a.AUTHORIZATION_SESSION_ALLOWLIST == "session_allowlist"
    assert a.AUTHORIZATION_TASK_NETWORK == "task_network"
    assert a.AUTHORIZATION_PLAN_MODE_WRITE == "plan_mode_write"
    assert a.AUTHORIZATION_TASK_WRITE == "task_write"
    assert a.AUTHORIZATION_PLAN_MODE_EXEC == "plan_mode_exec"
    assert a.AUTHORIZATION_SAFE_VERIFICATION == "safe_verification"
    assert a.AUTHORIZATION_TASK_EXEC == "task_exec"
    assert a.AUTHORIZATION_USER_APPROVED == "user_approved"


def _allowed(node: ast.Constant, parents: dict[int, ast.AST]) -> bool:
    parent = parents.get(id(node))
    if isinstance(parent, ast.Assign):
        for t in parent.targets:
            if isinstance(t, ast.Name) and t.id in CONST_NAMES:
                return True
    return False


def test_no_bare_authorization_decision_code_literals_in_scoped_modules() -> None:
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
        "bare authorization decision code literals - ask AUTHORIZATION_* from minicc.audit:\n"
        + "\n".join(offenders)
    )
