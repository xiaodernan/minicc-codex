"""M8-T628 — work-tree verdict kinds have one home.

`gitprobe.work_tree_verdict` returns `(kind, detail)` where kind is
yes/no/unknown. The kind vocabulary is produced in `minicc.gitprobe` and
compared in `minicc.changes` and `minicc.agent.loop`; bare literals duplicate
the same fact.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = PACKAGE / "gitprobe.py"
SCOPED = {HOME, PACKAGE / "changes.py", PACKAGE / "agent" / "loop.py"}

KINDS = {"yes", "no", "unknown"}
CONST_NAMES = {
    "WORK_TREE_VERDICT_YES",
    "WORK_TREE_VERDICT_NO",
    "WORK_TREE_VERDICT_UNKNOWN",
}


def test_the_home_defines_work_tree_verdict_kind_constants() -> None:
    import minicc.gitprobe as g

    assert g.WORK_TREE_VERDICT_YES == "yes"
    assert g.WORK_TREE_VERDICT_NO == "no"
    assert g.WORK_TREE_VERDICT_UNKNOWN == "unknown"


def _allowed(node: ast.Constant, parents: dict[int, ast.AST]) -> bool:
    parent = parents.get(id(node))
    if isinstance(parent, ast.Assign):
        for t in parent.targets:
            if isinstance(t, ast.Name) and t.id in CONST_NAMES:
                return True
    return False


def test_no_bare_work_tree_verdict_kind_literals_in_scoped_modules() -> None:
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
            if not isinstance(node, ast.Constant) or node.value not in KINDS:
                continue
            if path == HOME and _allowed(node, parents):
                continue
            # In gitprobe, "yes"/"no"/"unknown" in non-verdict contexts would be lookalikes;
            # but gitprobe is small and these are the verdict values - gate all, allow defs.
            offenders.append(f"{rel}:{node.lineno} bare {node.value!r}")
    offenders = sorted(set(offenders))
    assert offenders == [], (
        "bare work-tree verdict kind literals - ask WORK_TREE_VERDICT_* from minicc.gitprobe:\n"
        + "\n".join(offenders)
    )
