"""M8-T620 — mention resolution statuses have one home.

@-mention records carry a `status` of injected/rejected/omitted. `minicc.mentions`
produces these records and `minicc.web` filters them; bare string literals in
both duplicate the same fact. The one home is `minicc.mentions`.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = PACKAGE / "mentions.py"
SCOPED = {HOME, PACKAGE / "web.py"}

STATUSES = {"injected", "rejected", "omitted"}
HOME_CONST_NAMES = {
    "MENTION_STATUS_INJECTED",
    "MENTION_STATUS_REJECTED",
    "MENTION_STATUS_OMITTED",
}


def test_the_home_defines_mention_status_constants() -> None:
    import minicc.mentions as m

    assert m.MENTION_STATUS_INJECTED == "injected"
    assert m.MENTION_STATUS_REJECTED == "rejected"
    assert m.MENTION_STATUS_OMITTED == "omitted"
    assert m.MENTION_STATUSES == {
        m.MENTION_STATUS_INJECTED,
        m.MENTION_STATUS_REJECTED,
        m.MENTION_STATUS_OMITTED,
    }


def _allowed_definition(node: ast.Constant, parents: dict[int, ast.AST]) -> bool:
    """Allow the literal only when it is the value of a MENTION_STATUS_* constant."""
    parent = parents.get(id(node))
    if isinstance(parent, ast.Assign):
        for t in parent.targets:
            if isinstance(t, ast.Name) and t.id in HOME_CONST_NAMES:
                return True
    return False


def test_no_bare_mention_status_literals_in_scoped_modules() -> None:
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
            if not isinstance(node, ast.Constant) or node.value not in STATUSES:
                continue
            if path == HOME and _allowed_definition(node, parents):
                continue
            offenders.append(f"{rel}:{node.lineno} bare mention status {node.value!r}")
    offenders = sorted(set(offenders))
    assert offenders == [], (
        "bare mention status literals in scoped modules - ask "
        "MENTION_STATUS_* from minicc.mentions:\n" + "\n".join(offenders)
    )
