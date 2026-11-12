"""M8-T88: a rubric nobody can read must not be graded as an answer.

``grade_behavior`` scored ``answer_rubric`` without validating the shape it read
out of the task file. Measured on the tree this batch started from:

* ``required_any`` written as a bare string came back ``passed=True`` with
  ``case_count=5`` for an answer that merely contained those characters;
* a flat ``["hello world"]`` where a group of groups belongs graded the answer
  against a different rubric than the one written down;
* an empty term ``[[""]]`` matched everything, and a rubric with no
  ``required_any`` at all came back ``passed=False`` - end to end printed as
  ``pass_at_1 0.0`` with ``false_completion_rate 1.0``, a grader nobody
  configured charged to the agent.

The caliber settled here: **a rubric that cannot be interpreted is NO-RESULT,
not a verdict.** It takes the channel M8-T83/T86 opened for host-side failures
(``bench_tasks.grader_cannot_judge``, the single ``_no_result`` constructor). A
well-formed rubric that simply does not match stays ``passed=False``; the
controls below keep this channel from swallowing a real red.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import minicc.bench_tasks as bench_tasks
from minicc.behavior_bench import grade_behavior
from minicc.benchmarks import build_report, run_benchmark

REPO_ROOT = Path(__file__).resolve().parent.parent
BEHAVIOR_BENCH = REPO_ROOT / "minicc" / "behavior_bench.py"
NO_RESULT_KEYS = {"passed", "grader_type", "grading_refused", "refusal"}

# (label, the ``required_any`` spec, an answer that used to slip through, the
# substring the refusal must name). One entry per rejection branch, and the
# answer is chosen so a gate cannot pass by rejecting every shape identically.
MALFORMED: tuple[tuple[str, dict[str, Any], str, str], ...] = (
    ("missing", {}, "hello world", "实际是 NoneType"),
    ("empty list", {"required_any": []}, "hello", "为空"),
    ("empty group", {"required_any": [[]]}, "hello", "是空组"),
    ("empty term", {"required_any": [[" "]]}, "hello", "不是非空字符串"),
    ("flat strings", {"required_any": ["hello world"]}, "hello world", "不是「组」"),
    ("non-string term", {"required_any": [[7]]}, "7", "不是非空字符串"),
    ("bare string", {"required_any": "hello"}, "hello", "实际是 str"),
    ("nested too deep", {"required_any": [[["a"]]]}, "a", "不是非空字符串"),
)


def _task(required_any: dict[str, Any]) -> dict[str, Any]:
    return {"id": "rubric", "grader": {"type": "answer_rubric", **required_any}}


# --- the malformed shapes: no verdict, and not the agent problem ------------


@pytest.mark.parametrize("label,spec,answer,reason", MALFORMED,
                         ids=[entry[0] for entry in MALFORMED])
def test_a_rubric_nobody_can_read_is_no_result(
    tmp_path: Path, label: str, spec: dict[str, Any], answer: str, reason: str
) -> None:
    """Nobody judged the answer, so there is no verdict to report."""
    graded = grade_behavior(_task(spec), tmp_path, answer)
    assert graded["passed"] is None, f"{label} was graded as a verdict: {graded}"
    assert graded["grading_refused"] is True, graded
    assert graded["grader_type"] == "answer_rubric", graded
    assert reason in graded["refusal"], graded
    assert "error" not in graded, graded
    assert set(graded) == NO_RESULT_KEYS, graded


def test_the_refusal_row_is_the_shape_the_host_failure_channel_uses(tmp_path: Path) -> None:
    """One verdict, two entrances: the key sets must not drift apart."""
    unreadable = grade_behavior(_task({}), tmp_path, "hello")
    unable = bench_tasks.grader_unable("answer_rubric", OSError("cannot start"))
    assert unreadable["passed"] is unable["passed"] is None
    assert unreadable["grading_refused"] is unable["grading_refused"] is True
    assert set(unreadable) == set(unable), (unreadable, unable)
    assert bench_tasks.grader_cannot_judge("answer_rubric", "x")["passed"] is None


# --- the readable shapes: a verdict, including a real red -------------------


@pytest.mark.parametrize("spec,answer,expect", [
    ({"required_any": [["hello"]]}, "Hello world", True),
    ({"required_any": [["hello"]]}, "nothing useful", False),
    ({"required_any": [["a", "b"], ["c"]]}, "b and c", True),
    ({"required_any": [["a", "b"], ["c"]]}, "a only", False),
    ({"required_any": (("hello",),)}, "hello", True),
])
def test_a_readable_rubric_still_gives_a_verdict(
    tmp_path: Path, spec: dict[str, Any], answer: str, expect: bool
) -> None:
    """A well-formed rubric grades; a miss stays a red, never a refusal."""
    graded = grade_behavior(_task(spec), tmp_path, answer)
    assert graded["passed"] is expect, graded
    assert graded["case_count"] == len(spec["required_any"]), graded
    assert "grading_refused" not in graded, graded


# --- end to end: the refusal must not become a red, nor erase one -----------


def _service_config() -> SimpleNamespace:
    return SimpleNamespace(
        yolo=False, max_concurrent_tasks=2, sandbox_mode="host",
        sandbox_image="python:3.11-slim", base_url="https://example.test/v1",
        api_key="test-key", model="test-model", temperature=0.0, max_tokens=100,
        request_timeout=30, system_prompt=None, task_store_path=None,
        sampling_enabled=False,
    )


def _run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, required_any: dict[str, Any],
         answer: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    class Service:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def _chat_locked(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            return {"answer": answer}

        def shutdown(self) -> None:
            pass

    monkeypatch.setattr("minicc.web.AgentService", Service)
    monkeypatch.setattr("minicc.config.load_config", _service_config)
    task = _task(required_any)
    rows = run_benchmark([task], workspace=tmp_path)
    return rows, build_report([task], rows)


def test_a_malformed_rubric_never_becomes_a_red_in_the_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The defect: an unreadable grader printed pass_at_1 0.0 for the agent."""
    rows, report = _run(tmp_path, monkeypatch, {}, "hello world")
    assert rows[0]["passed"] is None, rows[0]
    assert rows[0]["grading_refused"] is True, rows[0]
    metrics = report["metrics"]
    assert metrics["gradable_task_count"] == 0, metrics
    assert metrics["grading_refusal_count"] == 1, metrics
    # With no gradable row the rate has an empty denominator. The old code put
    # the unreadable grader in that denominator and printed 1.0; None is the
    # honest reading of "no verdict exists", not a number about the agent.
    assert metrics["false_completion_rate"] is None, metrics
    assert metrics["pass_at_1"] is None, metrics


@pytest.mark.parametrize("answer,expect_passed,expect_false_completion", [
    ("hello world", True, 0.0),
    ("nothing useful", False, 1.0),
])
def test_a_readable_rubric_grades_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, answer: str,
    expect_passed: bool, expect_false_completion: float,
) -> None:
    """Reverse control: the channel must not erase a red or fake a pass."""
    rows, report = _run(tmp_path, monkeypatch, {"required_any": [["hello"]]}, answer)
    assert rows[0]["passed"] is expect_passed, rows[0]
    assert "grading_refused" not in rows[0], rows[0]
    metrics = report["metrics"]
    assert metrics["gradable_task_count"] == 1, metrics
    assert metrics["grading_refusal_count"] == 0, metrics
    assert metrics["pass_at_1"] == (1.0 if expect_passed else 0.0), metrics
    assert metrics["false_completion_rate"] == expect_false_completion, metrics


# --- census: one reader of the field, and it runs before the verdict --------


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """Ids of the string constants that are docstrings rather than code."""
    out: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                out.add(id(body[0].value))
    return out


def _key_readers(source: str, key: str) -> list[str]:
    """Functions whose code names ``key`` as a plain string (docstrings excluded)."""
    tree = ast.parse(source)
    docstrings = _docstring_nodes(tree)
    readers: list[str] = []

    def visit(node: ast.AST, function: str | None) -> None:
        for child in ast.iter_child_nodes(node):
            name = (child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                    else function)
            if (isinstance(child, ast.Constant) and child.value == key
                    and id(child) not in docstrings):
                readers.append(name or "<module>")
            visit(child, name)

    visit(tree, None)
    return readers


def test_the_rubric_field_is_read_in_exactly_one_place() -> None:
    """A second reader is where an unvalidated shape sneaks back in."""
    readers = _key_readers(BEHAVIOR_BENCH.read_text(encoding="utf-8"), "required_any")
    assert readers == ["_rubric_groups"], readers


def test_the_reader_census_notices_a_second_reader() -> None:
    """Reverse control: the census must be able to see the defect shape."""
    planted = (
        "def grade_behavior(task, workspace, answer):\n"
        "    groups = task[\"grader\"].get(\"required_any\", [])\n"
        "    return {\"passed\": bool(groups)}\n"
    )
    assert _key_readers(planted, "required_any") == ["grade_behavior"]
    documented = (
        "def grade_behavior(task, workspace, answer):\n"
        "    \"\"\"Reads required_any after validating it.\"\"\"\n"
        "    return {}\n"
    )
    assert _key_readers(documented, "required_any") == []


def _grade_behavior_node(source: str) -> ast.FunctionDef:
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef) and node.name == "grade_behavior":
            return node
    raise AssertionError("grade_behavior is gone")


def _rubric_verdict_order(source: str) -> tuple[int | None, int | None]:
    """Lines of the shape check and of the first answer comparison."""
    node = _grade_behavior_node(source)
    validate = next((call.lineno for call in ast.walk(node)
                     if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                     and call.func.id == "_rubric_groups"), None)
    compare = next((attr.lineno for attr in ast.walk(node)
                    if isinstance(attr, ast.Attribute) and attr.attr == "casefold"), None)
    return validate, compare


def test_the_rubric_branch_validates_the_shape_before_it_compares() -> None:
    """Reading the answer before reading the shape is the defect itself."""
    validate, compare = _rubric_verdict_order(BEHAVIOR_BENCH.read_text(encoding="utf-8"))
    assert validate is not None, "grade_behavior no longer validates the rubric shape"
    assert compare is not None, "grade_behavior no longer compares the answer"
    assert validate < compare, (validate, compare)


def test_the_order_census_notices_a_verdict_computed_first() -> None:
    """Reverse control: a verdict computed first must be flagged out of order."""
    planted = (
        "def grade_behavior(task, workspace, answer):\n"
        "    folded = answer.casefold()\n"
        "    return _rubric_groups(task)\n"
    )
    validate, compare = _rubric_verdict_order(planted)
    assert validate is not None and compare is not None, (validate, compare)
    assert compare < validate, (validate, compare)
