"""M8-T629 — tool risk level names have one home.

The risk level vocabulary (readonly, write, exec) is compared in authorization
and agent-loop gating. `minicc.audit` owns risk semantics (`effective_risk`,
authorization); bare literals in risk comparisons duplicate the same fact.

Scoped to comparisons on lines involving `risk`/`effective_risk` to avoid
lookalikes (e.g. executor/mode names in other domains).
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = PACKAGE / "audit.py"
SCOPED = {HOME, PACKAGE / "agent" / "loop.py"}

RISKS = {"readonly", "write", "exec"}
CONST_NAMES = {"RISK_READONLY", "RISK_WRITE", "RISK_EXEC"}


def test_the_home_defines_risk_level_constants() -> None:
    import minicc.audit as a

    assert a.RISK_READONLY == "readonly"
    assert a.RISK_WRITE == "write"
    assert a.RISK_EXEC == "exec"


def _allowed(node: ast.Constant, parents: dict[int, ast.AST]) -> bool:
    parent = parents.get(id(node))
    if isinstance(parent, ast.Assign):
        for t in parent.targets:
            if isinstance(t, ast.Name) and t.id in CONST_NAMES:
                return True
    return False


def test_no_bare_risk_level_literals_in_scoped_risk_comparisons() -> None:
    offenders: list[str] = []
    for path in sorted(SCOPED):
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(path))
        lines = src.splitlines()
        parents: dict[int, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parents[id(child)] = parent
        rel = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            line = lines[node.lineno - 1] if node.lineno <= len(lines) else ""
            start = max(0, node.lineno - 3)
            window = "\n".join(lines[start:node.lineno])
            if "risk" not in window.lower() and "effective_risk" not in window:
                continue
            for comp in [node.left] + list(node.comparators):
                if isinstance(comp, ast.Constant) and comp.value in RISKS:
                    if path == HOME and _allowed(comp, parents):
                        continue
                    offenders.append(f"{rel}:{comp.lineno} bare risk {comp.value!r}: {line.strip()[:130]}")
    offenders = sorted(set(offenders))
    assert offenders == [], (
        "bare risk level literals in scoped risk comparisons - ask RISK_* from minicc.audit:\n"
        + "\n".join(offenders)
    )
