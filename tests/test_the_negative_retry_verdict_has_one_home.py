"""M8-T502 — 节点重试判词两个家：StateGraph 与 DAGPlan 各拼一句

「节点重试次数不能为负数: X」有两个家：`StateGraph.add_node` 的节点注册
校验和 `DAGPlan.validate` 的任务表校验。两处逐字相同（只有主语不同）。
一个负的 max_retries 从哪扇门进去，读到的就是哪份拼写——一处改了措词
其余没跟上，没有任何测试会红。

家安在 `minicc/agent/graph.py` 模块层，紧挨 `StateGraph`——两个调用点都
在这个模块。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/agent/graph.py"
SENTENCE = "节点重试次数不能为负数: "


def _literal_shapes():
    for path in sorted(PACKAGE.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        inside_fstring: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                for child in ast.iter_child_nodes(node):
                    inside_fstring.add(id(child))
        for node in ast.walk(tree):
            if id(node) in inside_fstring:
                continue
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                yield path, node.lineno, node.value
            elif isinstance(node, ast.JoinedStr):
                parts = [
                    part.value
                    for part in node.values
                    if isinstance(part, ast.Constant) and isinstance(part.value, str)
                ]
                yield path, node.lineno, "".join(parts)


def test_the_home_pins_the_sentence() -> None:
    from minicc.agent.graph import negative_retries_message

    assert negative_retries_message("node-x") == f"节点重试次数不能为负数: node-x"


def test_the_sentence_is_spelled_exactly_once_in_the_package() -> None:
    offenders = [
        f"{path.relative_to(REPO).as_posix()}:{lineno}"
        for path, lineno, text in _literal_shapes()
        if text == SENTENCE
    ]
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the negative-retry sentence is spelled by hand outside its one home: "
        + ", ".join(offenders)
    )


def test_both_validators_ask_the_home() -> None:
    source = (REPO / HOME).read_text(encoding="utf-8")
    assert source.count("negative_retries_message(") == 3, (
        "graph.py asks the home "
        f"{source.count('negative_retries_message(')} times, expected 3 "
        "(one definition plus two validators)"
    )


def test_the_node_registry_validator_emits_the_homes_sentence() -> None:
    from minicc.agent.graph import GraphNode, GraphValidationError, StateGraph

    graph = StateGraph()
    with pytest.raises(GraphValidationError) as excinfo:
        graph.add_node(GraphNode(name="retry-node", phase="plan", max_retries=-1))
    assert str(excinfo.value) == f"节点重试次数不能为负数: retry-node", excinfo.value


def test_the_dag_plan_validator_emits_the_homes_sentence() -> None:
    from minicc.agent.graph import DAGPlan, GraphValidationError, PlanTask

    plan = DAGPlan(
        name="p",
        tasks=(PlanTask(id="dag-node", kind="read", max_retries=-1),),
    )
    with pytest.raises(GraphValidationError) as excinfo:
        plan.validate()
    assert str(excinfo.value) == f"节点重试次数不能为负数: dag-node", excinfo.value
