"""Mutation cells for the oracle vacuous policy (M8-T239 rewrite).

Everything here shoulders behaviour that lives in ``minicc.benchmarks``. A cell is
only load-bearing if it tells the verdict apart when that behaviour changes, so the
two mutations that used to ship vacuous now come with a probe row the *original*
rejects: the mutation has to turn a "no" into a "yes", otherwise the assertion is
true before and after and the arm is decoration.

That reading comes from M8-T239's reverse control. Two of the four arms here
(``C1``, ``C2``) passed with the mutation deleted as often as with it applied - they
were handed the vacuous-allow row, which the unmutated function already passes.

The file also shipped ``test_baseline_vacuous_allow`` twice. A Python module keeps
only the last definition, so pytest collected 7 of the source file's 8 test
functions and one never ran. Nothing reported it.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import minicc.benchmarks as bm  # noqa: E402
from minicc.benchmarks import _oracle_says_pass  # noqa: E402

DEFAULT_POLICY = bm.VACUOUS_ORACLE_POLICY
ALLOW_ROW = {"objective_oracle": {"passed": True}, "grader_type": "file_contract"}
CASE_COUNT_ROW = {"objective_oracle": {"passed": True, "case_count": 2},
                  "grader_type": "file_contract"}


# --- the baseline the policy is expressed against -----------------------


def test_baseline_vacuous_allow() -> None:
    """Under ``allow`` a vacuous oracle from a known grader type is trusted."""
    assert _oracle_says_pass(ALLOW_ROW) is True


def test_oracle_with_case_count() -> None:
    """``case_count >= 1`` is the non-vacuous path: trust arrives with real work."""
    assert _oracle_says_pass(CASE_COUNT_ROW) is True


def test_case_count_zero_is_not_a_case_count() -> None:
    """A zero-case contract judged nothing; the oracle must not lend it trust."""
    zero = {"objective_oracle": {"passed": True, "case_count": 0},
            "grader_type": "file_contract"}
    assert _oracle_says_pass(zero) is False, (
        "the oracle trusts a grader that ran zero cases"
    )


def test_an_unknown_grader_type_cannot_borrow_the_allow_policy() -> None:
    """``allow`` is a statement about the shipped vocabulary, not about trust in general."""
    unknown = {"objective_oracle": {"passed": True}, "grader_type": "mystery_contract"}
    assert _oracle_says_pass(unknown) is False


def test_vacuous_with_unknown_policy() -> None:
    """Unknown policy defaults to deny (safe)."""
    original = bm.VACUOUS_ORACLE_POLICY
    try:
        bm.VACUOUS_ORACLE_POLICY = "unknown"
        assert _oracle_says_pass(ALLOW_ROW) is False
    finally:
        bm.VACUOUS_ORACLE_POLICY = original


# --- mutation arms ------------------------------------------------------


def test_mutation_C3_policy_deny() -> None:
    """``deny`` is a total refusal; the mutated policy path must still be exercised."""
    original = bm.VACUOUS_ORACLE_POLICY
    try:
        bm.VACUOUS_ORACLE_POLICY = "deny"
        assert _oracle_says_pass(ALLOW_ROW) is False
    finally:
        bm.VACUOUS_ORACLE_POLICY = original


def test_mutation_C4_policy_require_case_count() -> None:
    """``require_case_count`` refuses the vacuous oracle without touching the counted one."""
    original = bm.VACUOUS_ORACLE_POLICY
    try:
        bm.VACUOUS_ORACLE_POLICY = "require_case_count"
        assert _oracle_says_pass(ALLOW_ROW) is False
        assert _oracle_says_pass(CASE_COUNT_ROW) is True
    finally:
        bm.VACUOUS_ORACLE_POLICY = original


def test_mutation_C1_oracle_always_true() -> None:
    """If ``_oracle_says_pass`` were ``lambda row: True``, a rejected row flips to passed.

    The row has to be one the real function rejects, or the arm passes with the
    mutation deleted. ``ALLOW_ROW`` is exactly that trap: the unmutated function
    returns True under ``allow``, so C1 could not see the mutation at all.
    """
    probe = {"objective_oracle": {"passed": True}, "grader_type": "mystery_contract"}
    mutated = lambda row: True  # noqa: E731 - the arm is a one-expression body
    assert mutated(probe) is True, "the arm no longer makes the oracle pass anything"
    assert _oracle_says_pass(probe) is False, (
        "the probe row is no longer rejected, so C1 cannot tell the mutation from the "
        "original - pick a row whose verdict is False"
    )


def test_mutation_C2_oracle_no_case_count() -> None:
    """Dropping the ``case_count`` branch makes a zero-case oracle pass.

    Same trap, same fix: the probe row must be one the branch currently rejects.
    With ``case_count: 0`` the shipped function says False; a copy without the
    branch falls through to the ``allow`` policy and says True.
    """
    original = bm._oracle_says_pass

    def without_case_count_check(row: dict) -> bool:
        oracle = row.get("objective_oracle")
        if not isinstance(oracle, dict) or oracle.get("passed") is not True:
            return False
        return row.get("grader_type") in {"file_contract", "command_contract"}

    probe = {"objective_oracle": {"passed": True, "case_count": 0},
             "grader_type": "file_contract"}
    # They agree wherever the branch does not matter.
    assert without_case_count_check(CASE_COUNT_ROW) == original(CASE_COUNT_ROW)
    # They disagree exactly on the row the branch exists to reject.
    assert without_case_count_check(probe) is True
    assert original(probe) is False, (
        "the case_count branch no longer rejects a zero-case oracle, so C2 cannot "
        "tell the mutation from the original"
    )


def test_every_mutation_arm_is_observable() -> None:
    """The meta-cell: an arm whose verdict matches the original is decoration.

    ``C1`` and ``C2`` both shipped green under the mutation *and* under its
    removal. This re-checks the property that makes them count, so a future edit
    that re-blunts either arm fails loudly instead of quietly.
    """
    unknown = {"objective_oracle": {"passed": True}, "grader_type": "mystery_contract"}
    zero = {"objective_oracle": {"passed": True, "case_count": 0},
            "grader_type": "file_contract"}
    assert (lambda row: True)(unknown) is True and _oracle_says_pass(unknown) is False
    assert _oracle_says_pass(zero) is False


def test_the_default_policy_is_the_one_both_gates_baseline_against() -> None:
    """C3/C4 restore to ``original``; the module default must not have been repointed."""
    assert bm.VACUOUS_ORACLE_POLICY == DEFAULT_POLICY, (
        "a cell left VACUOUS_ORACLE_POLICY changed; every cell here restores it in a "
        "finally, so this failure means an escape path exists"
    )
