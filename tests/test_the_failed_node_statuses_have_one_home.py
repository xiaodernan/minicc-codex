"""M8-T403 — 节点失败态两个家：路由判定与节点执行判定各写一份 {"failed", "error"}"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/agent/graph.py"

FAILED = frozenset({"failed", "error"})


def test_the_home_exists_in_graph() -> None:
    """graph.py owns the known failure statuses beside SUCCESS_STATUSES."""
    from minicc.agent.graph import FAILED_NODE_STATUSES, SUCCESS_STATUSES

    assert FAILED_NODE_STATUSES == FAILED
    assert not (FAILED_NODE_STATUSES & SUCCESS_STATUSES), (
        "a status cannot be both a success and a failure"
    )


def test_no_module_inlines_the_failed_statuses() -> None:
    """No module spells the failure statuses as a literal outside the declaration."""
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        relative = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Set | ast.Tuple | ast.List):
                continue
            elements = frozenset(
                element.value
                for element in node.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            )
            if len(node.elts) >= 2 and elements == FAILED:
                offenders.append(f"{relative}:{node.lineno}")
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the failed node statuses are spelled inline outside the one declaration: "
        + ", ".join(offenders)
    )


def test_a_failing_node_still_fails_the_dag() -> None:
    """Behavior unchanged: a handler returning a failure status fails the run."""
    import asyncio

    from minicc.agent.graph import DAGPlan, PlanTask, execute_dag

    plan = DAGPlan(
        "failing",
        (
            PlanTask("a", "readonly"),
            PlanTask("b", "readonly", ("a",)),
        ),
    )
    result = asyncio.run(execute_dag(plan, lambda task: {"status": "failed", "error": "boom"}))
    assert result.status == "failed"
    assert result.failed == ["a"]
    assert result.outputs["a"]["error"] == "boom"
