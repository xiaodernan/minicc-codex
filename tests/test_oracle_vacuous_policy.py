"""Gate: the vacuous-oracle policy is a live knob, and its default is on record.

M8-T176 measured one full-suite run: 217 ``_objective_oracle`` calls, 32 of them
vacuous (17.4%, no ``case_count``), every one from a shipped grader type. A
vacuous oracle is a pass that names no case it judged, so what such a pass is
worth is a policy decision, not an accident of payload shape. The decision has
to be read from the constant on the path that decides - a comment paraphrasing
it is exactly the kind of second copy that drifts (M8-T82).

What this file does not do is measure the suite-wide ratio again: that number
is a property of the test suite's composition, not of the product, so a gate
asserting it would fail whenever someone adds an oracle test for a reason that
has nothing to do with the product. The one-time measurement lives in the
roadmap record for M8-T176.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

from minicc.benchmarks import VACUOUS_ORACLE_POLICY, _oracle_says_pass

REPO_ROOT = Path(__file__).resolve().parent.parent


def _row(oracle: dict[str, Any], grader_type: object = "file_contract") -> dict[str, Any]:
    row: dict[str, Any] = {"objective_oracle": oracle}
    if grader_type is not None:
        row["grader_type"] = grader_type
    return row


@pytest.fixture
def policy(monkeypatch: pytest.MonkeyPatch):
    """Set ``VACUOUS_ORACLE_POLICY`` for one test; monkeypatch restores it after."""
    def apply(value: str) -> None:
        monkeypatch.setattr("minicc.benchmarks.VACUOUS_ORACLE_POLICY", value)
    return apply


def test_the_default_policy_is_the_one_the_measurement_was_taken_under() -> None:
    """The recorded 32/32 vacuous passes were counted under ``allow``.

    If this constant moves, every historical ``reviewer_false_negative_count``
    was produced under a different口径 than the one now in force, and the
    roadmap record that measured the ratio stops describing this code.
    """
    assert VACUOUS_ORACLE_POLICY == "allow"
    assert _oracle_says_pass(_row({"passed": True})) is True


def test_allow_trusts_only_a_grader_the_shipped_vocabulary_names() -> None:
    """Trust is a claim about a producer, so it needs the producer's name."""
    for grader_type in ("file_contract", "command_contract"):
        assert _oracle_says_pass(_row({"passed": True}, grader_type)) is True, grader_type
    assert _oracle_says_pass(_row({"passed": True}, "mystery_oracle")) is False
    assert _oracle_says_pass(_row({"passed": True}, None)) is False


def test_a_refusal_never_reaches_the_vacuous_branch() -> None:
    """``passed: None`` is NO-RESULT, and NO-RESULT is not a yes about anything.

    ``_no_result`` can carry a ``case_count`` (a refused file_contract reports
    how many files it declined to judge), so the vacuous branch is not the only
    place a countless payload can arrive.
    """
    refused = _row({"passed": None, "grading_refused": True, "case_count": 0})
    assert _oracle_says_pass(refused) is False


def test_deny_refuses_every_vacuous_pass(policy) -> None:
    policy("deny")
    for grader_type in ("file_contract", "command_contract"):
        assert _oracle_says_pass(_row({"passed": True}, grader_type)) is False, grader_type


def test_require_case_count_refuses_a_pass_that_names_no_case(policy) -> None:
    policy("require_case_count")
    assert _oracle_says_pass(_row({"passed": True})) is False


def test_an_unknown_policy_value_fails_closed(policy) -> None:
    """A typo in the constant must not silently become ``allow``."""
    policy("deny_vacuous_but_only_sometimes")
    assert _oracle_says_pass(_row({"passed": True})) is False


@pytest.mark.parametrize("count,expected", [
    (5, True),
    (1, True),
    (0, False),
    (-1, False),
    (True, False),          # a bool is not a measurement, whatever it equals
    ("3", False),           # a string is not a measurement
    (float("inf"), False),  # nor is an infinity
    (float("nan"), False),  # nor is a NaN, which compares >= 1 as False anyway
])
@pytest.mark.parametrize("mode", ["allow", "deny", "require_case_count"])
def test_a_counted_oracle_is_judged_on_its_count_under_every_policy(
    policy, mode: str, count: object, expected: bool
) -> None:
    """A real count outranks the policy in both directions.

    ``deny`` refuses *vacuous* passes; it does not get to overrule a grader
    that actually judged cases, and ``require_case_count`` accepts exactly the
    rows it names.
    """
    policy(mode)
    assert _oracle_says_pass(_row({"passed": True, "case_count": count})) is expected, (mode, count)


def test_the_policy_constant_is_read_on_the_deciding_path() -> None:
    """Otherwise the knob is decorative: the branch would hard-code its answer.

    The gate looks for the structural pattern - the constant must be loaded by
    name inside ``_oracle_says_pass`` - so renaming the constant, or inlining
    its value at the decision point, is red even though every behavioural test
    above still passes.
    """
    tree = ast.parse((REPO_ROOT / "minicc" / "benchmarks.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_oracle_says_pass":
            loads = {
                inner.id
                for inner in ast.walk(node)
                if isinstance(inner, ast.Name) and inner.id == "VACUOUS_ORACLE_POLICY"
            }
            assert loads, (
                "_oracle_says_pass no longer reads VACUOUS_ORACLE_POLICY: "
                f"{ast.unparse(node)}"
            )
            return
    pytest.fail("_oracle_says_pass is gone from benchmarks.py")
