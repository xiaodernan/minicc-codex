"""M8-T377 — 计划节点的工具名单只有一个家

**兜底计划不经规划器校验 ✓，所以它的名单无人核对 ✓。** ✓

一个动态计划有**两个来源** ✓：

* **规划器提议的** ✓——它的节点工具要过
  ``planner.py`` 的**按 kind 校验** ✓（`PLANNER_KIND_TOOLS[kind]` ✓）；
* **固定模板兜底的** ✓（`fixed_plan` ✓，`planner.py` 在规划器失败时用它 ✓）——
  它**直接构造** ✓，**不经过那个校验** ✓。

于是"**一个写节点能用哪些工具**"这个事实 ✓，
在**两个模块**里各写了一份 ✓：

| 位置 | 名单 | 谁问它 |
| --- | --- | --- |
| `minicc/agent/planner.py` ✓ | `WRITE_PLANNER_TOOLS` ✓ | 规划器校验提议的节点 ✓ |
| `minicc/agent/graph.py` × 2 ✓ | 手写 ✓ | 固定模板的 implement 节点 ✓ |

而**兜底那份不经过校验** ✓ → **没有任何东西比较过它们** ✓ →
它们可以**各说各话** ✓ → 兜底计划就会是那个**异类** ✓。

只读那一侧**早就修好了** ✓：`READONLY_PLANNER_TOOLS = READONLY_DAG_TOOLS` ✓
是**再导出** ✓（注释明说"one home … cannot drift again" ✓）✓——
**写的那一侧没跟上** ✓。

M8-T402 补批 ✓：verify 节点的名单 `{"bash", "git_diff"}` 当时漏收 ✓——
同样是手写形状 ✓、只是只有两处 ✓，已并入 `VERIFY_DAG_TOOLS` ✓。

这一批 ✓：把模板的工具名单收进 `graph.py` ✓（执行器那一层 ✓，
`planner.py` 本来就 import 它 ✓）✓，规划器**再导出** ✓——
与只读那一侧**同一个做法** ✓。
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"

#: The tools a fixed template's inspect node may use.
INSPECT = frozenset({"read_file", "grep", "git_status"})
#: The tools a fixed template's write node may use.
WRITE = frozenset({"write_file", "edit_file"})
#: The tools a fixed template's verify node may use (M8-T402).
VERIFY = frozenset({"bash", "git_diff"})


def test_the_template_tool_lists_have_one_home() -> None:
    """The home exists, and it holds the two lists."""
    from minicc.agent.graph import INSPECT_DAG_TOOLS, VERIFY_DAG_TOOLS, WRITE_DAG_TOOLS

    assert INSPECT_DAG_TOOLS == INSPECT
    assert WRITE_DAG_TOOLS == WRITE
    assert VERIFY_DAG_TOOLS == VERIFY


def test_the_planner_re_exports_the_write_tier() -> None:
    """The same move the readonly tier already makes.

    Equality is not enough: two equal frozensets are two rules that drift
    apart the next time somebody adds a tool.
    """
    from minicc.agent import graph, planner

    assert planner.WRITE_PLANNER_TOOLS is graph.WRITE_DAG_TOOLS, (
        "the planner's write tier must be the executor's list itself, not a "
        "copy of it"
    )
    assert planner.READONLY_PLANNER_TOOLS is graph.READONLY_DAG_TOOLS, (
        "the control: the readonly tier still re-exports the executor's list"
    )


def test_no_plan_node_spells_its_tool_list_out_by_hand() -> None:
    """A second copy is a second answer to the same question.

    The check is scoped to the **plan node's** tool list - the question
    "which tools may this node use?".  Two other lists in the tree happen to
    hold the same two names and ask **different** questions: the
    parallel-safe write tools (which writes may run at the same time) and the
    subagent's write tier (what a child agent may use).  Those are not the
    plan's business, and a content match cannot tell them apart - so this
    gate reads the *plan node* itself instead.
    """
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name != "PlanTask":
                continue
            for keyword in node.keywords:
                if keyword.arg != "allowed_tools":
                    continue
                # The literal may be written bare (``{...}``) or wrapped in
                # ``frozenset({...})`` - both spell the list out by hand.
                value = keyword.value
                if (
                    isinstance(value, ast.Call)
                    and getattr(value.func, "id", None) == "frozenset"
                    and len(value.args) == 1
                ):
                    value = value.args[0]
                if isinstance(value, ast.Set):
                    members = frozenset(
                        element.value
                        for element in value.elts
                        if isinstance(element, ast.Constant)
                        and isinstance(element.value, str)
                    )
                    if members in (INSPECT, WRITE, VERIFY):
                        offenders.append(
                            f"{path.relative_to(REPO).as_posix()}:{node.lineno}"
                        )
    assert not offenders, (
        "a plan node spells its tool list out by hand; the one home for the "
        "fixed templates' lists is minicc/agent/graph.py: " + ", ".join(offenders)
    )


def test_the_planner_does_not_write_the_write_tier_out_by_hand() -> None:
    """The planner's tier must be the executor's list, not a copy of it."""
    import ast

    tree = ast.parse((PACKAGE / "agent" / "planner.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name) or target.id != "WRITE_PLANNER_TOOLS":
                continue
            assert not isinstance(node.value, ast.Set), (
                "the planner's write tier must be re-exported from the "
                "executor, not written out again"
            )


def test_the_templates_still_grant_what_they_used_to() -> None:
    """The control: the fallback plan is unchanged.

    A fallback plan that grants fewer tools than the planner may propose is
    the odd one out - so the templates must keep granting exactly what they
    granted before.
    """
    from minicc.agent.graph import fixed_plan

    for name in ("inspect_implement_verify", "parallel_inspect"):
        plan = fixed_plan(name, task_count=3)
        for task in plan.tasks:
            if task.id == "inspect" or task.id.startswith("inspect-"):
                assert task.allowed_tools == INSPECT, task.id
            elif task.id == "implement":
                assert task.allowed_tools == WRITE, task.id
            elif task.id == "verify":
                assert task.allowed_tools == VERIFY, task.id


def test_the_planner_validates_against_the_same_list() -> None:
    """The behavioural half: what the planner accepts is what the template grants."""
    from minicc.agent.planner import PLANNER_KIND_TOOLS

    assert PLANNER_KIND_TOOLS["write"] == WRITE, (
        "the planner's write tier and the fixed template's write node must "
        "be the same list, or the fallback plan is the odd one out"
    )
