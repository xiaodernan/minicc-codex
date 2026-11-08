"""M8-T624 — missing-task authorization codes have one home.

The authorization code names `missing_task_write`, `missing_task_exec`, and
`missing_task_network` are part of the authorization vocabulary owned by
`minicc.audit`. Their string literals were duplicated in decision construction,
comparisons, and the `MISSING_TASK_AUTHORIZATIONS` set.

Behavior preserved: `MISSING_TASK_AUTHORIZATIONS` contains exactly write+exec
(not network), matching the existing web flow contract.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = PACKAGE / "audit.py"
SCOPED = {HOME, PACKAGE / "main.py"}

CODES = {"missing_task_write", "missing_task_exec", "missing_task_network"}
CONST_NAMES = {
    "AUTHORIZATION_MISSING_TASK_WRITE",
    "AUTHORIZATION_MISSING_TASK_EXEC",
    "AUTHORIZATION_MISSING_TASK_NETWORK",
}


def test_the_home_defines_missing_task_authorization_constants() -> None:
    import minicc.audit as a

    assert a.AUTHORIZATION_MISSING_TASK_WRITE == "missing_task_write"
    assert a.AUTHORIZATION_MISSING_TASK_EXEC == "missing_task_exec"
    assert a.AUTHORIZATION_MISSING_TASK_NETWORK == "missing_task_network"
    # Behavior contract: the set gates the interactive approval flow and must
    # contain only write/exec (network is handled separately).
    assert a.MISSING_TASK_AUTHORIZATIONS == frozenset({
        a.AUTHORIZATION_MISSING_TASK_WRITE,
        a.AUTHORIZATION_MISSING_TASK_EXEC,
    })
    assert a.AUTHORIZATION_MISSING_TASK_NETWORK not in a.MISSING_TASK_AUTHORIZATIONS


def _allowed(node: ast.Constant, parents: dict[int, ast.AST]) -> bool:
    parent = parents.get(id(node))
    if isinstance(parent, ast.Assign):
        for t in parent.targets:
            if isinstance(t, ast.Name) and t.id in CONST_NAMES:
                return True
    return False


def test_no_bare_missing_task_authorization_literals_in_scoped_modules() -> None:
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
        "bare missing-task authorization code literals - ask "
        "AUTHORIZATION_MISSING_TASK_* from minicc.audit:\n" + "\n".join(offenders)
    )
