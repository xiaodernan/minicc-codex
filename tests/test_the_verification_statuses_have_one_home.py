"""M8-T378 — 验证结果的词表有名字，它的子集是推导出来的

**一个词表没有名字，它的子集就到处被手写。** ✓

`VerificationResult.status` ✓（`minicc/agent/verifier.py` ✓）能取六个值 ✓：
`passed` ✓ / `failed` ✓ / `skipped` ✓ / `blocked` ✓ / `cancelled` ✓ /
`timed_out` ✓——而这六个值**没有任何地方声明过** ✓。

于是它的子集被**手写了五处** ✓（三个模块 ✓）✓：

| 位置 | 集合 | 问的是什么 |
| --- | --- | --- |
| `verifier.py:61` ✓ | `{passed, skipped}` ✓ | "这次验证**没发现问题**" ✓ |
| `verifier.py:62-69` ✓ | 六个 ✓ | 事件 code 的表 ✓ |
| `completion.py:342` ✓ | `{failed, blocked, cancelled, timed_out}` ✓ | "这次验证**没给出可用结论**" ✓ |
| `web.py:2850` ✓ | `{passed, skipped}` ✓ | 同第一行 ✓ |
| `completion.py:394` ✓ | `{error, failed, blocked, cancelled, timed_out, denied}` ✓ | **单项检查**的状态 ✓（**另一套词表** ✓，`error`/`denied` ✓ 不是验证状态 ✓） |

于是"**这个验证状态算不算问题**"这个问题 ✓，在**三个模块**里各有答案 ✓。
一旦词表**多一个状态** ✓，一个面会当它"没问题" ✓、另一个面会当它"没结论" ✓。

这一批 ✓：词表**有了名字** ✓（`VERIFICATION_STATUSES` ✓）✓，
两个真正被问到的子集**由它推导** ✓——
于是**新加的状态**会被**同一套规则**分类 ✓✓。
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"

#: The six statuses a verification result can carry.
VOCABULARY = frozenset({
    "passed", "failed", "skipped", "blocked", "cancelled", "timed_out",
})
#: "The verification found no problem."
NO_PROBLEM = frozenset({"passed", "skipped"})


def test_the_verification_vocabulary_has_a_name() -> None:
    """The home exists, and it holds the six statuses."""
    from minicc.agent.verifier import VERIFICATION_STATUSES

    assert VERIFICATION_STATUSES == VOCABULARY, (
        f"the vocabulary is {sorted(VERIFICATION_STATUSES)}, expected "
        f"{sorted(VOCABULARY)}"
    )


def test_the_two_subsets_are_derived() -> None:
    """Derived, not written out - so a new status is classified alike."""
    from minicc.agent.verifier import (
        NON_FAILURE_VERIFICATION_STATUSES,
        UNUSABLE_VERIFICATION_STATUSES,
        VERIFICATION_STATUSES,
    )

    assert NON_FAILURE_VERIFICATION_STATUSES == NO_PROBLEM
    assert UNUSABLE_VERIFICATION_STATUSES == (
        VERIFICATION_STATUSES - NON_FAILURE_VERIFICATION_STATUSES
    )
    assert UNUSABLE_VERIFICATION_STATUSES == frozenset(
        {"failed", "blocked", "cancelled", "timed_out"}
    )


def test_the_derivation_is_what_the_code_uses() -> None:
    """The two faces must read the derived sets, not their own copies."""
    for name, expected in (
        ("agent/verifier.py", "NON_FAILURE_VERIFICATION_STATUSES"),
        ("agent/completion.py", "UNUSABLE_VERIFICATION_STATUSES"),
        ("web.py", "NON_FAILURE_VERIFICATION_STATUSES"),
    ):
        source = (PACKAGE / name).read_text(encoding="utf-8")
        assert expected in source, (
            f"minicc/{name} must ask the one home for {expected}"
        )


def test_no_module_writes_the_no_problem_subset_out_by_hand() -> None:
    """A second copy is a second answer to the same question."""
    home = "minicc/agent/verifier.py"
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
            if members == NO_PROBLEM:
                relative = path.relative_to(REPO).as_posix()
                if relative != home:
                    offenders.append(f"{relative}:{node.lineno}")
    assert not offenders, (
        "the 'the verification found no problem' statuses are written out by "
        f"hand outside their one home ({home}): " + ", ".join(offenders)
    )


def test_no_module_writes_the_no_verdict_subset_out_by_hand() -> None:
    """The other subset, and the one the mutation exposed.

    The first version of this gate only watched the "no problem" subset, so
    a hand-written copy of the *other* one slipped through - the mutation
    caught it, not the gate.
    """
    home = "minicc/agent/verifier.py"
    no_verdict = frozenset({"failed", "blocked", "cancelled", "timed_out"})
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
            if members == no_verdict:
                relative = path.relative_to(REPO).as_posix()
                if relative != home:
                    offenders.append(f"{relative}:{node.lineno}")
    assert not offenders, (
        "the 'the verification produced no usable verdict' statuses are "
        f"written out by hand outside their one home ({home}): "
        + ", ".join(offenders)
    )


def test_the_check_statuses_are_a_different_vocabulary() -> None:
    """The control: one list really is about something else.

    ``completion.py`` also asks about ``error`` and ``denied`` - those are
    the statuses of an individual *check*, not of the verification as a
    whole.  This gate says so explicitly, so a later round does not "fix" it
    by pulling it into the verification vocabulary.
    """
    source = (PACKAGE / "agent" / "completion.py").read_text(encoding="utf-8")
    assert '"denied"' in source and '"error"' in source, (
        "the per-check status list is a different vocabulary and stays where "
        "it is; this control fails if it is ever removed"
    )
    assert '"denied"' not in VOCABULARY
    assert '"error"' not in VOCABULARY
