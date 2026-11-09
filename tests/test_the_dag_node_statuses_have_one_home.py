"""M8-T673 — the spelled DAG-node statuses have one home.

``DAGResult.status``, every ``outputs[*]["status"]`` and the ``AgentState.finish``
stamp on the same execution axis spell four lifecycle words:
``running`` / ``completed`` / ``failed`` / ``skipped``.  Home is
``minicc.agent.graph.NODE_STATUS_*``.

Distinct from the *verdict* sets (``SUCCESS_STATUSES`` / ``FAILED_NODE_STATUSES``,
the router's open vocabulary) and from the wire event labels on edges — though the
one node-status word that also names an edge (``"failed"``) is taken from the same
home, so there is nothing left to spell twice.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOME = REPO / "minicc" / "agent" / "graph.py"
SCOPED = {HOME}
DEFS = {
    "NODE_STATUS_RUNNING": "running",
    "NODE_STATUS_COMPLETED": "completed",
    "NODE_STATUS_FAILED": "failed",
    "NODE_STATUS_SKIPPED": "skipped",
}


def test_the_home_defines_the_four_node_statuses() -> None:
    import minicc.agent.graph as graph

    for name, value in DEFS.items():
        assert getattr(graph, name) == value
    assert graph.NODE_STATUSES == frozenset(DEFS.values())


def test_no_bare_node_status_literals_remain_outside_definitions() -> None:
    src = HOME.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(HOME))
    # Docstring/expression constants are prose, not node states.
    prose_ids = {
        id(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
    }
    prose_nodes = {
        id(child)
        for parent_id in prose_ids
        for parent in ast.walk(tree)
        if id(parent) == parent_id
        for child in ast.walk(parent)
    }
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or node.value not in DEFS.values():
            continue
        if id(node) in prose_nodes:
            continue
        line = src.splitlines()[node.lineno - 1]
        if line.startswith("NODE_STATUS_"):  # the home itself
            continue
        offenders.append(
            f"{HOME.name}:{node.lineno}: {line.strip()[:160]}"
        )
    assert offenders == [], (
        "bare DAG-node status literal - use NODE_STATUS_* from minicc.agent.graph:\n"
        + "\n".join(offenders)
    )
