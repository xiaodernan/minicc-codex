"""M8-T95: a vocabulary that spans two graders is strict-looking and permissive.

While the rubric and the behaviour spec were read in one function, the only key list
derivable from that function was the union of both branches - so a rubric spec carrying
``cases`` (a behaviour key) was accepted and ignored, and a behaviour spec carrying
``required_any`` likewise. The union is exactly the shape of list that reads as strict in
review and catches nothing.

``grade_answer_rubric`` is now its own function, so the declaration below has a
branch-sized subject, and these gates reconcile it against that subject's AST.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import minicc.behavior_bench as behavior_bench
from minicc.benchmarks import build_report

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE = (REPO_ROOT / "minicc" / "behavior_bench.py").read_text(encoding="utf-8")


def _function(name: str) -> ast.FunctionDef:
    tree = ast.parse(SOURCE)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} is gone from minicc/behavior_bench.py")


def _grader_keys(function: ast.FunctionDef) -> set[str]:
    import minicc.bench_tasks as bench_tasks
    return bench_tasks._keys_read(function, "grader")


def test_the_declared_rubric_vocabulary_is_what_the_rubric_actually_reads() -> None:
    read = _grader_keys(_function("grade_answer_rubric"))
    assert read == set(behavior_bench.RUBRIC_SPEC_KEYS), (
        f"the rubric reads {sorted(read)} but declares {sorted(behavior_bench.RUBRIC_SPEC_KEYS)}"
    )


def test_the_branch_scoped_list_is_narrower_than_the_merged_one() -> None:
    """The point of the split: the old subject could only yield a union."""
    merged = _grader_keys(_function("grade_behavior"))
    declared = set(behavior_bench.RUBRIC_SPEC_KEYS)
    assert merged - declared, (
        "grade_behavior no longer reads more keys than the rubric does, so this witness "
        "is no longer distinguishing the two - update it instead of letting it idle"
    )
    assert "cases" in merged and "cases" not in declared, (merged, declared)


@pytest.mark.parametrize("spec,dead_key", [
    ({"type": "answer_rubric", "required_any": [["好"]], "cases": []}, "cases"),
    ({"type": "answer_rubric", "required_any": [["好"]], "preserve_inputs": True}, "preserve_inputs"),
])
def test_a_rubric_spec_carrying_another_graders_key_is_refused(
    tmp_path: Path, spec: dict, dead_key: str
) -> None:
    graded = behavior_bench.grade_answer_rubric({"grader": spec}, answer="很好")
    assert graded["passed"] is None, f"a rubric accepted a key it never reads: {graded}"
    assert graded["grading_refused"] is True, graded
    assert dead_key in graded["refusal"], graded


def test_a_rubric_that_does_read_its_subject_still_grades(tmp_path: Path) -> None:
    graded = behavior_bench.grade_answer_rubric(
        {"grader": {"type": "answer_rubric", "required_any": [["很好", "good"], ["完成"]]}},
        answer="很好，任务完成。")
    assert graded["passed"] is True, graded
    assert graded["case_count"] == 2, graded
    assert not graded.get("grading_refused"), graded


def test_the_reverse_direction_is_closed_too(tmp_path: Path) -> None:
    """A python_behavior spec must not borrow the rubric key either."""
    (tmp_path / "solution.py").write_text("def f(a):\n    return a\n", encoding="utf-8")
    graded = behavior_bench.grade_behavior(
        {"grader": {"type": "python_behavior", "function": "f",
                    "cases": [[[1], 1]], "required_any": [["x"]]}}, tmp_path)
    assert graded["passed"] is None, graded
    assert "required_any" in graded["refusal"], graded


def test_a_rubric_refusal_reaches_the_report_as_a_refusal() -> None:
    spec = {"type": "answer_rubric", "required_any": [["好"]], "cases": []}
    graded = behavior_bench.grade_answer_rubric({"grader": spec}, answer="很好")
    task = {"id": "rubric-typo", "category": "qa", "prompt": "p", "grader": spec}
    row = {"task_id": "rubric-typo", "category": "qa", "status": "completed",
           "claimed_complete": True, **graded}
    metrics = build_report([task], [row])["metrics"]
    assert metrics["grading_refusal_count"] == 1, metrics
    assert metrics["gradable_task_count"] == 0, metrics


def test_grade_behavior_delegates_rubric_work_to_the_branch() -> None:
    """Otherwise the strict list protects a path nobody takes."""
    fn = _function("grade_behavior")
    called = {n.func.id for n in ast.walk(fn)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    called |= {n.func.attr for n in ast.walk(fn)
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert "grade_answer_rubric" in called, (
        f"grade_behavior does not CALL grade_answer_rubric (calls: {sorted(called)}); "
        "a mere mention in ast.dump is not delegation"
    )
