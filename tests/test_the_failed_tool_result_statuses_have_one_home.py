"""M8-T376 — 「这次调用失败了吗」只有一个家

**一个问了两次的问题，两个手写的答案。** ✓

Agent loop 要回答两次同一个问题 ✓：

> 这一轮里，**哪些工具调用没有做成** ✓？

两个地方各自手写了一份答案 ✓（`minicc/agent/loop.py` ✓ 的
`_replan_constraints` ✓ 与 `run_agent` ✓），而它们喂给**不同的输出** ✓：

* `_replan_constraints` ✓ → **约束文本** ✓（"上一轮有失败或被阻止的工具：…" ✓）；
* `run_agent` ✓ → **`last_replan_trigger`** ✓（"上一轮工具失败或被阻止…" ✓）
  与 trace 详情 ✓。

于是**一旦两份漂移**，模型会在**同一轮**里同时收到**两句矛盾的话** ✓：
"有工具失败了" ✓ 与 "工具结果已合并" ✓。

**更糟的是那份手写的答案本身有一个死成员** ✓：`failed` ✓——
它**不是**工具结果的状态 ✓（`TOOL_RESULT_STATUSES` 里没有它 ✓），
产品**从不构造**它 ✓（实测 ✓：AST 扫过所有 `ToolResult(...)` 的显式
``status=`` ✓，只有 ok/error/denied/cancelled/timed_out ✓）✓。
所以那一项**永远匹配不上** ✓——一份**没人兑现的承诺** ✓。

而 `minicc/tools/schemas.py` 的 `TOOL_RESULT_STATUSES` ✓
**定义了却全仓无人使用** ✓——又一条"**声明了没人问**"的词表 ✓。

这一批 ✓：那个事实**收进一个家** ✓（`tools/schemas.py` ✓，
它本来就是工具结果的词表 ✓）✓，并且**从词表推导** ✓——
于是**不存在的状态进不来** ✓，**以后加的状态自动被带上** ✓✓。
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"


def test_the_failed_statuses_have_one_home() -> None:
    """The home exists, and it holds exactly the three real failures."""
    from minicc.tools.schemas import FAILED_TOOL_RESULT_STATUSES

    assert FAILED_TOOL_RESULT_STATUSES == frozenset({"error", "denied", "timed_out"}), (
        "the failed statuses are "
        f"{sorted(FAILED_TOOL_RESULT_STATUSES)}; a status the product never "
        "produces must not be in the list, and a status it does produce "
        "(other than the deliberately excluded cancelled) must be"
    )


def test_the_home_is_derived_from_the_declared_vocabulary() -> None:
    """Derived, not written out - so a status that cannot exist cannot creep in."""
    from minicc.tools.schemas import FAILED_TOOL_RESULT_STATUSES, TOOL_RESULT_STATUSES

    assert FAILED_TOOL_RESULT_STATUSES <= frozenset(TOOL_RESULT_STATUSES), (
        "the failed statuses must be a subset of the declared tool-result "
        "vocabulary; a member outside it is a promise nobody can keep"
    )
    assert "ok" not in FAILED_TOOL_RESULT_STATUSES
    assert "cancelled" not in FAILED_TOOL_RESULT_STATUSES, (
        "a cancelled call means the task is being torn down, not that the "
        "model should try something else"
    )


def test_the_declared_vocabulary_is_now_actually_used() -> None:
    """The control: the vocabulary is not a dead declaration any more."""
    from minicc.tools.schemas import FAILED_TOOL_RESULT_STATUSES, TOOL_RESULT_STATUSES

    assert FAILED_TOOL_RESULT_STATUSES, "the derivation must produce a set"
    assert set(TOOL_RESULT_STATUSES) - {"ok", "cancelled"} == set(
        FAILED_TOOL_RESULT_STATUSES
    ), "the derivation must be exactly 'every status but ok and cancelled'"


def test_no_module_writes_the_failed_statuses_out_by_hand() -> None:
    """A second copy is a second answer to the same question."""
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Set):
                continue
            members = frozenset(
                element.value
                for element in node.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            )
            # The old hand-written answer, with or without its dead member.
            if members in (
                frozenset({"error", "failed", "denied", "timed_out"}),
                frozenset({"error", "denied", "timed_out"}),
            ):
                relative = path.relative_to(REPO).as_posix()
                if relative != "minicc/tools/schemas.py":
                    offenders.append(f"{relative}:{node.lineno}")
    assert not offenders, (
        "the failed tool-result statuses are written out by hand outside "
        "their one home (minicc/tools/schemas.py): " + ", ".join(offenders)
    )


def test_the_loop_asks_the_one_home_twice() -> None:
    """Both questioners read the home, so they cannot disagree."""
    source = (PACKAGE / "agent" / "loop.py").read_text(encoding="utf-8")
    assert source.count("FAILED_TOOL_RESULT_STATUSES") >= 2, (
        "both places that ask 'did this call fail?' must read the one home"
    )


def test_the_dead_status_is_not_spelled_out_as_a_set_anywhere() -> None:
    """The dead member is gone from the source, not just from the answer.

    The check is scoped to the **tool-result** question.  Other vocabularies
    legitimately carry a ``failed`` status - a verification result
    (``failed``/``blocked``/``passed``/``skipped``) and a DAG node
    (``failed``/``error``/``completed``) - and those are different questions.
    A set belongs to the tool-result questions when it names ``denied`` and
    ``timed_out`` (which only tool results have) and borrows nothing from
    the other two.
    """
    home = "minicc/tools/schemas.py"
    borrowed = {"blocked", "passed", "skipped", "completed", "ok"}
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Set):
                continue
            members = frozenset(
                element.value
                for element in node.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            )
            is_tool_result_question = (
                {"denied", "timed_out"} <= members and not (members & borrowed)
            )
            if is_tool_result_question:
                relative = path.relative_to(REPO).as_posix()
                if relative != home:
                    offenders.append(f"{relative}:{node.lineno}")
    assert not offenders, (
        "the statuses that mean 'this tool call failed' (or 'did not succeed') "
        "are written out by hand outside their one home "
        "(minicc/tools/schemas.py): " + ", ".join(offenders)
    )


def test_the_unsuccessful_statuses_have_their_own_home() -> None:
    """The second question - "did not succeed" - is a different question.

    A cancelled call did not succeed, even though it is not a failure the
    model should retry.  The stagnation guard asks *that* question, so it
    needs its own answer - and its own name.
    """
    from minicc.tools.schemas import (
        FAILED_TOOL_RESULT_STATUSES,
        TOOL_RESULT_STATUSES,
        UNSUCCESSFUL_TOOL_RESULT_STATUSES,
    )

    assert UNSUCCESSFUL_TOOL_RESULT_STATUSES == frozenset(
        status for status in TOOL_RESULT_STATUSES if status != "ok"
    )
    assert "cancelled" in UNSUCCESSFUL_TOOL_RESULT_STATUSES
    assert "cancelled" not in FAILED_TOOL_RESULT_STATUSES
    assert FAILED_TOOL_RESULT_STATUSES < UNSUCCESSFUL_TOOL_RESULT_STATUSES
