"""M8-T410 — 评分判决记录四个家：两个契约评分器与两个行为评分器各手抄一份"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/bench_tasks.py"

#: The core every verdict record carries - "did it pass" and "who judged".
CORE = {"passed", "grader_type"}
#: A verdict record is small; the report row that also carries both keys has
#: two dozen of them and is a different fact (``benchmarks.py`` row schema).
MAX_VERDICT_KEYS = 6

#: The four graders that produce a graded verdict, by defining function.
PRODUCERS = {
    "minicc/bench_tasks.py": ("grade_file_contract", "grade_command_contract"),
    "minicc/behavior_bench.py": ("grade_answer_rubric", "grade_behavior"),
}


def _small_verdict_literals(path: Path) -> list[ast.Dict]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[ast.Dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        keys = {
            key.value
            for key in node.keys
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        }
        if CORE <= keys and len(keys) <= MAX_VERDICT_KEYS:
            found.append(node)
    return found


def test_the_home_builds_the_verdict() -> None:
    """The constructor keeps both shapes: with and without the optional keys."""
    from minicc.bench_tasks import graded_verdict

    assert graded_verdict("python_behavior", True, case_count=2, exit_code=0) == {
        "passed": True, "grader_type": "python_behavior",
        "case_count": 2, "exit_code": 0,
    }
    assert graded_verdict("answer_rubric", False) == {
        "passed": False, "grader_type": "answer_rubric",
    }


def test_every_grader_asks_the_home() -> None:
    """All four producers call the constructor, not their own dict literal."""
    for module, functions in PRODUCERS.items():
        tree = ast.parse((PACKAGE / module.removeprefix("minicc/")).read_text(encoding="utf-8"))
        bodies: dict[str, ast.AST] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in functions:
                bodies[node.name] = node
        assert set(bodies) == set(functions), (
            f"{module} no longer defines {sorted(set(functions) - set(bodies))}"
        )
        for name, body in bodies.items():
            calls = [
                node.func for node in ast.walk(body)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "graded_verdict"
            ] + [
                node.func for node in ast.walk(body)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "graded_verdict"
            ]
            assert calls, f"{module}:{name} must ask the one home for the verdict"


def test_no_module_spells_a_verdict_outside_the_home() -> None:
    """A verdict spelled outside the home is a shape the metrics cannot see."""
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        relative = path.relative_to(REPO).as_posix()
        if relative == HOME:
            continue
        for node in _small_verdict_literals(path):
            offenders.append(f"{relative}:{node.lineno}")
    assert not offenders, (
        "a graded verdict is spelled by hand outside its one home "
        f"({HOME}): " + ", ".join(offenders)
    )


def test_the_verdict_family_stays_three_constructors() -> None:
    """Inside the home the family is exactly three constructors.

    ``_no_result`` (a grader declined), ``graded_verdict`` (a grader judged)
    and ``ungraded_verdict`` (nobody was going to look).  A fourth small
    verdict literal in the home module is drift too - the T398 lesson: the
    home is one constructor per fact, not one module per fact.
    """
    offenders = [
        str(node.lineno) for node in _small_verdict_literals(REPO / HOME)
    ]
    assert len(offenders) == 3, (
        "the verdict family must stay three constructors in "
        f"{HOME}, found literals at lines {offenders}"
    )
