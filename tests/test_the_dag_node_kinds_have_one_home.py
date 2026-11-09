"""M8-T676 — the spelled DAG-node kinds have one home.

The five words a DAG node is allowed to be filed under —
``readonly`` / ``write`` / ``exec`` / ``review`` / ``merge`` — live in
``minicc.agent.graph.DAG_KIND_*`` (with ``DAG_KINDS`` as their frozenset).
Both consumers (the executor's readonly boundary and the planner's kind
vocabulary) ask the same home; a hand-spelled copy on either side would
re-drift the boundary the executor draws.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCOPED = (
    REPO / "minicc" / "agent" / "graph.py",
    REPO / "minicc" / "agent" / "planner.py",
)
HOME = REPO / "minicc" / "agent" / "graph.py"
KINDS = {"readonly", "write", "exec", "review", "merge"}
DEF_NAMES = {
    "DAG_KIND_READONLY": "readonly",
    "DAG_KIND_WRITE": "write",
    "DAG_KIND_EXEC": "exec",
    "DAG_KIND_REVIEW": "review",
    "DAG_KIND_MERGE": "merge",
}


def test_the_home_defines_the_kinds() -> None:
    import minicc.agent.graph as graph

    for name, value in DEF_NAMES.items():
        assert getattr(graph, name) == value
    assert graph.DAG_KINDS == frozenset(DEF_NAMES.values())
    assert graph.READONLY_DAG_KINDS == frozenset({"readonly", "review", "merge"})


def test_planner_consumes_the_same_home() -> None:
    import minicc.agent.planner as planner
    import minicc.agent.graph as graph

    assert planner.PLANNER_KINDS == graph.DAG_KINDS
    for kind in graph.DAG_KINDS:
        assert kind in planner.PLANNER_KIND_TOOLS


def test_no_bare_kind_literals_remain_outside_definitions() -> None:
    offenders: list[str] = []
    for path in SCOPED:
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(path))
        prose: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                for child in ast.walk(node):
                    prose.add(id(child))
        parents: dict[int, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parents[id(child)] = parent
        depends_on_ids: set[int] = set()
        for parent in ast.walk(tree):
            if (
                isinstance(parent, ast.Call)
                and isinstance(parent.func, ast.Name)
                and parent.func.id == "PlanTask"
            ):
                for keyword in parent.keywords:
                    if keyword.arg == "depends_on":
                        for child in ast.walk(keyword.value):
                            depends_on_ids.add(id(child))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or node.value not in KINDS:
                continue
            if id(node) in prose:
                continue
            parent = parents.get(id(node))
            if (
                isinstance(parent, ast.Call)
                and isinstance(parent.func, ast.Name)
                and parent.func.id == "PlanTask"
                and parent.args
                and parent.args[0] is node
            ):
                # PlanTask's first positional is the node *instance id*,
                # not the kind — the "merge" node of the fixed template is
                # a task id, and renaming it would be a workflow change.
                continue
            if id(node) in depends_on_ids:
                # depends_on holds task instance ids, not kinds.
                continue
            line = src.splitlines()[node.lineno - 1]
            if line.startswith("DAG_KIND_"):
                continue
            offenders.append(f"{path.name}:{node.lineno}: {line.strip()[:160]}")
    assert offenders == [], (
        "bare DAG kind literal - use DAG_KIND_* from minicc.agent.graph:\n"
        + "\n".join(offenders)
    )
