"""M8-T487 — 批量取消判词两个家：任务管理器与 Web 面各拼一句

``批量任务已取消。`` 是「取消裁决」在批量场景下的句子：单个任务被取消读
``任务已取消。``（T479 已立家），一批任务被取消读这句。M8-T479 特意把它留
在原地——它确实是另一个事实。但「另一个事实」不等于「可以有两个家」：取消
出口在 task_manager，Web 面在 web.py，两边各手拼一遍，改一处漏一处，一张
脸读新句子、另一张脸读旧句子，没有任何测试会红。

家安在 ``minicc/agent/protocol.py``——取消裁决词汇表本来的家，两个消费者
本来都从那里 import。
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/agent/protocol.py"
MANAGER = "minicc/task_manager.py"
WEB = "minicc/web.py"


def test_the_home_owns_the_batch_notice() -> None:
    from minicc.agent.protocol import BATCH_CANCELLED_ANSWER

    assert BATCH_CANCELLED_ANSWER == "批量任务已取消。"


def test_the_batch_notice_is_spelled_exactly_once_in_the_package() -> None:
    """Census: one literal, in the home - a second one is a second wording."""
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        relative = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value == "批量任务已取消。":
                offenders.append(f"{relative}:{node.lineno}")
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the batch notice is spelled by hand outside its one home: "
        + ", ".join(offenders)
    )


def test_both_faces_ask_the_home() -> None:
    """The cancelled exit and the web face both pass the home's constant."""
    manager = (REPO / MANAGER).read_text(encoding="utf-8")
    web = (REPO / WEB).read_text(encoding="utf-8")
    assert manager.count("_orchestration_result(BATCH_CANCELLED_ANSWER") == 1, (
        "the manager's cancelled exit must ask the home for the notice"
    )
    assert web.count('"answer": BATCH_CANCELLED_ANSWER') == 1, (
        "the web face must ask the home for the notice"
    )


def test_both_faces_share_one_object() -> None:
    from minicc.agent import protocol
    from minicc import task_manager, web

    assert task_manager.BATCH_CANCELLED_ANSWER is protocol.BATCH_CANCELLED_ANSWER
    assert web.BATCH_CANCELLED_ANSWER is protocol.BATCH_CANCELLED_ANSWER


def test_the_batch_notice_is_a_different_fact_from_the_task_verdict() -> None:
    """A cancelled batch is not a cancelled task; the words must not merge."""
    from minicc.agent.protocol import (
        BATCH_CANCELLED_ANSWER,
        TASK_CANCELLED_ANSWER,
        TASK_CANCELLED_ERROR,
    )

    assert BATCH_CANCELLED_ANSWER != TASK_CANCELLED_ANSWER
    assert not BATCH_CANCELLED_ANSWER.startswith(TASK_CANCELLED_ERROR)
    assert BATCH_CANCELLED_ANSWER.endswith("。")


def test_the_notice_flows_into_the_orchestration_result() -> None:
    """The manager's cancelled exit answers with the home's sentence."""
    from minicc.agent.protocol import BATCH_CANCELLED_ANSWER
    from minicc.task_manager import _orchestration_result

    result = _orchestration_result(BATCH_CANCELLED_ANSWER, True, [{"id": 1}])
    assert result == {
        "answer": BATCH_CANCELLED_ANSWER,
        "cancelled": True,
        "children": [{"id": 1}],
    }
