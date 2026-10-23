"""The bench loader's "this task cannot be scored" sentences must have one home.

Two doors refuse an unscoreable bench task: ``bench_tasks.validate_task`` (the
v2 / legacy suites) and ``behavior_bench.validate_behavior_task`` (the behaviour
suite).  Both raised the same two sentences - an unknown grader type, and a
grader spec nobody can execute - and both spelled them out by hand.  So the
wording of "this task file is broken" had two homes: a task author who grepped
for one phrase found the refusals of one loader only, and nothing failed.

The census here works on the **template** of an f-string, not on its rendered
text: the literal parts are re-joined with ``{}`` standing in for each
interpolation, so ``f"任务 {a} grader 类型非法: {b}"`` and
``f"任务 {x} grader 类型非法: {y}"`` are recognised as the same sentence.  That
is the property being defended - two spellings of one sentence are one fact -
and comparing rendered text would miss it entirely.

This door pins:

* each template has exactly one carrier, in ``bench_tasks``;
* nothing else starts with either template;
* each builder is defined once and called from both loaders;
* the two doors render the same bytes for the same task;
* a scoreable task still passes both.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from minicc import bench_tasks
from minicc.behavior_bench import validate_behavior_task

REPO = pathlib.Path(__file__).resolve().parents[1]
HOME = "minicc/bench_tasks.py"
OTHER = "minicc/behavior_bench.py"
TYPE_TEMPLATE = "任务 {} grader 类型非法: {}"
SPEC_TEMPLATE = "任务 {} grader 规格无法判分: {}"
BUILDERS = ("grader_type_illegal", "grader_spec_unscoreable")


def _trees():
    for path in sorted((REPO / "minicc").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path, ast.parse(path.read_bytes().decode("utf-8"))


def _template(node: ast.JoinedStr) -> str:
    """The f-string's literal skeleton, with ``{}`` per interpolation."""
    parts = []
    for value in node.values:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            parts.append(value.value)
        else:
            parts.append("{}")
    return "".join(parts)


def _templates() -> list[tuple[str, int, str]]:
    found = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                found.append((path.relative_to(REPO).as_posix(), node.lineno, _template(node)))
    return found


def _call_name(func: ast.AST) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _call_sites(name: str) -> list[str]:
    sites = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _call_name(node.func) == name:
                sites.append(f"{path.relative_to(REPO).as_posix()}:{node.lineno}")
    return sites


def _definitions(name: str) -> list[str]:
    found = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                found.append(f"{path.relative_to(REPO).as_posix()}:{node.lineno}")
    return found


def _v2_bad_type() -> dict[str, object]:
    return {"id": "x", "category": "edit", "prompt": "p", "max_minutes": 5,
            "fixture": {"a.txt": "x"}, "grader": {"type": "mystery"}}


def _v2_bad_spec() -> dict[str, object]:
    return {"id": "z", "category": "edit", "prompt": "p", "max_minutes": 5,
            "fixture": {"a.txt": "x"},
            "grader": {"type": "file_contract", "files": [{"path": "../escape"}]}}


def _behaviour_bad_type(task_id: str = "b1") -> dict[str, object]:
    return {"id": task_id, "category": "edit", "prompt": "p", "grader": {"type": "mystery"}}


def _behaviour_bad_spec(task_id: str = "b2") -> dict[str, object]:
    return {"id": task_id, "category": "edit", "prompt": "p",
            "grader": {"type": "answer_rubric", "required_any": [["a"], []]}}


def _refusal(fn, task: dict[str, object]) -> str:
    with pytest.raises(ValueError) as caught:
        fn(task)
    return str(caught.value)


# --- one home for the words ---------------------------------------------------


@pytest.mark.parametrize("template", [TYPE_TEMPLATE, SPEC_TEMPLATE],
                         ids=["type", "spec"])
def test_the_template_has_exactly_one_home(template):
    hits = [hit for hit in _templates() if hit[2] == template]
    assert len(hits) == 1, hits
    assert hits[0][0] == HOME, hits


@pytest.mark.parametrize("template", [TYPE_TEMPLATE, SPEC_TEMPLATE],
                         ids=["type", "spec"])
def test_nothing_else_starts_with_the_template(template):
    """A hand-written copy is exactly this shape: the template, then more."""
    strays = [hit for hit in _templates()
              if hit[2].startswith(template) and hit[2] != template]
    assert strays == [], strays


@pytest.mark.parametrize("name", BUILDERS)
def test_the_builder_is_defined_exactly_once(name):
    assert _definitions(name) == [f"{HOME}:{_line_of(name)}"], _definitions(name)


def _line_of(name: str) -> int:
    for path, tree in _trees():
        if path.relative_to(REPO).as_posix() != HOME:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                return node.lineno
    raise AssertionError(name)


@pytest.mark.parametrize("name", BUILDERS)
def test_the_builder_is_called_from_both_loaders(name):
    sites = _call_sites(name)
    assert len(sites) == 2, sites
    assert sum(site.startswith(f"{HOME}:") for site in sites) == 1, sites
    assert sum(site.startswith(f"{OTHER}:") for site in sites) == 1, sites


# --- the home still refuses ---------------------------------------------------


def test_the_type_builder_renders_the_pinned_bytes():
    assert bench_tasks.grader_type_illegal("x", "mystery") == "任务 x grader 类型非法: mystery"


def test_the_spec_builder_renders_the_pinned_bytes():
    assert bench_tasks.grader_spec_unscoreable("z", ["a", "b"]) == (
        "任务 z grader 规格无法判分: a; b"
    )


def test_the_two_doors_refuse_an_unknown_type_the_same_way():
    """Same task, same id, same bytes - the wording is not two facts."""
    assert _refusal(bench_tasks.validate_task, _v2_bad_type()) == (
        _refusal(validate_behavior_task, _behaviour_bad_type("x"))
    )


def test_the_two_doors_refuse_an_unscoreable_spec_the_same_way():
    v2 = _refusal(bench_tasks.validate_task, _v2_bad_spec())
    behaviour = _refusal(validate_behavior_task, _behaviour_bad_spec())
    assert v2.startswith("任务 z grader 规格无法判分: "), v2
    assert behaviour.startswith("任务 b2 grader 规格无法判分: "), behaviour
    assert v2 == _refusal(bench_tasks.validate_task, _v2_bad_spec()), v2


def test_a_non_dict_grader_still_names_what_it_got():
    """The v2 door has not proved the grader is a dict; the sentence must say so."""
    task = {"id": "y", "category": "edit", "prompt": "p", "max_minutes": 5,
            "fixture": {"a.txt": "x"}, "grader": "nope"}
    assert _refusal(bench_tasks.validate_task, task) == "任务 y grader 类型非法: nope"


def test_a_scoreable_task_passes_both_doors():
    v2 = {"id": "ok", "category": "edit", "prompt": "p", "max_minutes": 5,
          "fixture": {"a.txt": "x"},
          "grader": {"type": "file_contract", "files": [{"path": "a.txt", "contains": "x"}]}}
    assert bench_tasks.validate_task(v2) is None
    behaviour = {"id": "ok", "category": "edit", "prompt": "p",
                 "grader": {"type": "answer_rubric", "required_any": [["done"]]}}
    assert validate_behavior_task(behaviour) is None
