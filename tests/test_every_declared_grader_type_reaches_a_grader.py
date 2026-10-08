"""M8-T187: a grader type nobody dispatches is a whole type silently ungraded.

``GRADER_TYPES`` is the name four different places trust: ``validate_task`` opens
the load door on it, ``run_benchmark`` picks ``grade_v2`` or ``grade_behavior`` on
it, ``_objective_oracle`` decides whether to re-run a diagnostic on it, and
``GRADER_SCRIPTS`` reconciles its embedded-script table against it. Nothing ever
asked the one question that makes all four true: can ``grade_v2`` actually judge a
type on that list?

Measured on ``ab6fa75``, by adding a third type to the list and running the shipped
machinery against it:

    GRADER_TYPES |= {"json_contract"}
    validate_task(task)            -> accepted          # the load door opens
    grade_v2(task, workspace)      -> {'passed': None, 'grader_type': 'ungraded'}
    no_grader_count                -> 0                 # the task DID declare a grader
    grading_refusal_count          -> 0                 # nobody declined, nobody ran
    gradable_task_count            -> 0
    grading_coverage               -> 0.0               # the only trace, and it reads
                                                         # as "the model did nothing"

Every counter that exists to make a no-verdict visible reports zero. The sibling
module has had the matching door since M8-T97
(``test_the_declared_behaviour_types_match_what_the_grader_dispatches``); this file
gives ``GRADER_TYPES`` the same one, plus one owner for the ``ungraded`` verdict
that both fallbacks used to hand-write.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import minicc.bench_tasks as bench_tasks
import minicc.behavior_bench as behavior_bench
from minicc.benchmarks import build_report

REPO_ROOT = Path(__file__).resolve().parent.parent
BENCH_TASKS_SOURCE = (REPO_ROOT / "minicc" / "bench_tasks.py").read_text(encoding="utf-8")
BEHAVIOR_SOURCE = (REPO_ROOT / "minicc" / "behavior_bench.py").read_text(encoding="utf-8")
BENCHMARKS_SOURCE = (REPO_ROOT / "minicc" / "benchmarks.py").read_text(encoding="utf-8")

#: Both modules that can answer with the ungraded verdict.
UNGRADED_MODULES = {"minicc/bench_tasks.py": BENCH_TASKS_SOURCE,
                    "minicc/behavior_bench.py": BEHAVIOR_SOURCE}


def _function(source: str, name: str) -> ast.FunctionDef:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} is gone from its module")


def _type_names_read(fn: ast.FunctionDef) -> set[str]:
    """Locals bound to ``something.get("type")`` - the dispatch variable's aliases."""
    names: set[str] = set()
    for node in ast.walk(fn):
        if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Attribute)
                and node.value.func.attr == "get"):
            continue
        if not any(isinstance(arg, ast.Constant) and arg.value == "type"
                   for arg in node.value.args):
            continue
        names |= {t.id for t in node.targets if isinstance(t, ast.Name)}
    return names


def _dispatched_types(fn: ast.FunctionDef) -> set[str]:
    """The grader types ``grade_v2`` compares against, read off its own AST.

    Derived rather than typed for the same reason ``BEHAVIOR_GRADER_TYPES``' door is:
    a hand-written copy of the dispatch is a second owner of "which types exist",
    and it goes stale the moment a branch is added - which is the exact edit this
    door exists to catch.
    """
    type_names = _type_names_read(fn)
    dispatched: set[str] = set()
    for node in ast.walk(fn):
        if not (isinstance(node, ast.Compare) and len(node.ops) == 1
                and isinstance(node.ops[0], (ast.Eq, ast.NotEq))):
            continue
        if not ({n.id for n in ast.walk(node) if isinstance(n, ast.Name)} & type_names):
            continue
        for comparator in node.comparators:
            if isinstance(comparator, ast.Constant) and isinstance(comparator.value, str):
                dispatched.add(comparator.value)
    return dispatched


def test_every_declared_grader_type_reaches_a_grader() -> None:
    """The door itself: the list and the dispatch are the same set.

    Fails in the direction that matters - a type on the list with no branch in
    ``grade_v2`` - and in the reverse one, a branch for a type the list never
    admits, which would be code the runner cannot reach.
    """
    fn = _function(BENCH_TASKS_SOURCE, "grade_v2")
    dispatched = _dispatched_types(fn)
    assert dispatched, "the scan found no dispatch at all - the extraction is broken, not the code"
    assert dispatched == set(bench_tasks.GRADER_TYPES), (
        f"GRADER_TYPES declares {sorted(bench_tasks.GRADER_TYPES)} but grade_v2 dispatches "
        f"{sorted(dispatched)}; a declared type with no branch is graded ungraded, and "
        f"no_grader_count / grading_refusal_count both read zero for it"
    )


@pytest.mark.parametrize("grader_type", sorted(bench_tasks.GRADER_TYPES))
def test_a_declared_grader_type_reaches_a_grader_that_refuses_by_name(
    tmp_path: Path, grader_type: str
) -> None:
    """The same claim, asked of the dispatch function instead of a table.

    Two tables already reconcile ``GRADER_TYPES`` against hand-maintained entries -
    ``GRADER_SCRIPTS`` and the empty-spec table in
    ``tests/test_grader_with_nothing_to_check_is_no_result.py`` - and both go red
    when a type is declared and the table is not. This door asks what a table can
    only approximate: hand ``grade_v2`` a task of that type and see whether a
    grader answers.

    An empty spec is the probe because every shipped grader refuses one by name,
    so the answer separates "this type reached a grader that declined" from "this
    type reached nobody". Parametrized off the list itself, a new type is tested
    the day it is declared; and because it never looks at how the dispatch is
    written, it survives a refactor that a table-shaped door does not.
    """
    graded = bench_tasks.grade_v2({"grader": {"type": grader_type}}, tmp_path)
    assert graded.get("grader_type") == grader_type, (
        f"{grader_type} is on GRADER_TYPES but grade_v2 answered {graded}; every task of "
        f"that type would be reported ungraded, and no_grader_count and "
        f"grading_refusal_count both read zero for it"
    )
    assert graded.get("grading_refused") is True, (
        f"{grader_type} reached grade_v2 but no grader of that name refused it: {graded}"
    )
    assert grader_type in str(graded.get("refusal")), (
        f"the refusal does not name {grader_type}, so it is not this grader's own answer: {graded}"
    )


def test_the_dispatch_scan_reads_the_alias_not_the_call_site() -> None:
    """Otherwise a rename of the local would silently empty the set above."""
    fn = _function(BENCH_TASKS_SOURCE, "grade_v2")
    assert _type_names_read(fn), (
        "grade_v2 no longer binds a local from grader.get('type'); the door above now "
        "compares an empty set against GRADER_TYPES and passes for the wrong reason"
    )


def test_the_load_door_asks_the_declared_list_not_a_typed_copy() -> None:
    """``validate_task`` must name ``GRADER_TYPES``, not its members.

    Same shape as the gate on ``_oracle_says_pass`` (M8-T93): a membership test
    against the name, and no grader-type literal in the body.
    """
    fn = _function(BENCH_TASKS_SOURCE, "validate_task")
    references = any(
        isinstance(comparator, ast.Name) and comparator.id == "GRADER_TYPES"
        or isinstance(comparator, ast.Attribute) and comparator.attr == "GRADER_TYPES"
        for node in ast.walk(fn) if isinstance(node, ast.Compare)
        for comparator in node.comparators
    )
    assert references, f"validate_task does not reference GRADER_TYPES: {ast.unparse(fn)}"
    literals: set[str] = set()
    for node in ast.walk(fn):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"):
            continue
        literals |= {arg.value for arg in node.args
                     if isinstance(arg, ast.Constant) and isinstance(arg.value, str)}
    assert not (literals & set(bench_tasks.GRADER_TYPES)), (
        f"validate_task names grader types by hand: {sorted(literals & set(bench_tasks.GRADER_TYPES))}"
    )


def test_the_runner_asks_the_declared_list_before_choosing_a_grader() -> None:
    """The branch that decides ``grade_v2`` vs ``grade_behavior`` names the list.

    Hand-typing the two types here would restore the exact split this batch closes:
    the list would say one thing, the runner another, and a third type would be
    sent to ``grade_behavior`` - which cannot judge it and answers ``ungraded``.
    """
    fn = _function(BENCHMARKS_SOURCE, "run_benchmark")
    calls_grade_v2 = any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id == "grade_v2" for node in ast.walk(fn)
    )
    assert calls_grade_v2, "run_benchmark no longer calls grade_v2"
    references = any(
        isinstance(comparator, ast.Name) and comparator.id == "GRADER_TYPES"
        or isinstance(comparator, ast.Attribute) and comparator.attr == "GRADER_TYPES"
        for node in ast.walk(fn) if isinstance(node, ast.Compare)
        for comparator in node.comparators
    )
    assert references, "run_benchmark no longer reads GRADER_TYPES to choose a grader"


def test_the_ungraded_verdict_has_exactly_one_owner() -> None:
    """One constructor, and no dict literal anywhere else spells the verdict.

    The census is structural on purpose. A behavioural door cannot see this: with
    both copies byte-identical, every call to either fallback returns the right
    thing, so the only way the split is observable is by reading the source - and
    the day one copy gains a field, the report still prints both identically,
    because ``markdown_report`` reads ``passed`` and ``grading_refused`` and
    nothing else.
    """
    owners = {}
    for path, source in UNGRADED_MODULES.items():
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for inner in ast.walk(node):
                if not (isinstance(inner, ast.Return) and isinstance(inner.value, ast.Dict)):
                    continue
                values = [v.value for v in inner.value.values
                          if isinstance(v, ast.Constant) and isinstance(v.value, str)]
                if "ungraded" in values:
                    owners.setdefault(node.name, set()).add(path)
    assert owners == {"ungraded_verdict": {"minicc/bench_tasks.py"}}, (
        f"the ungraded verdict is spelled by {sorted(owners)}; one constructor is the "
        f"only shape that keeps the two fallbacks from drifting apart"
    )


def test_the_one_constructor_says_what_the_verdict_is_not() -> None:
    """A refusal means a grader looked and declined; this means nobody could.

    The distinction is what ``build_report`` counts on: folding this into the
    refusal family would inflate ``grading_refusal_count`` with a claim about a
    grader that never ran, and folding it into ``passed=False`` would charge the
    agent for the host's own missing grader (M8-T80).
    """
    verdict = bench_tasks.ungraded_verdict()
    assert verdict == {"passed": None, "grader_type": "ungraded"}, verdict
    assert "grading_refused" not in verdict, verdict
    assert "refusal" not in verdict, verdict


def test_both_fallbacks_answer_with_the_one_verdict(tmp_path: Path) -> None:
    """The two call sites are the only producers; they must not disagree."""
    v2 = bench_tasks.grade_v2({"grader": {"type": "mystery"}}, tmp_path)
    behaviour = behavior_bench.grade_behavior({"grader": {"type": "mystery"}}, tmp_path)
    assert v2 == behaviour == bench_tasks.ungraded_verdict(), (v2, behaviour)
    # A spec with no type at all is the same verdict, not a different one.
    assert bench_tasks.grade_v2({"grader": {}}, tmp_path) == bench_tasks.ungraded_verdict()
    assert behavior_bench.grade_behavior({"grader": {}}, tmp_path) == bench_tasks.ungraded_verdict()


def test_an_ungraded_row_is_neither_a_pass_nor_a_refusal_nor_a_no_grader_task() -> None:
    """Where the verdict lands in the report, pinned so it cannot be re-filed.

    ``no_grader_count`` asks the *task* (M8-T184), so a task that declares a grader
    this host cannot run is not a no-grader task - and it is not a refusal either.
    That leaves the row counted by nothing, which is the debt this batch names
    rather than fixes: the door above is what stops the set of such tasks from
    growing silently.
    """
    task = {"id": "mystery", "category": "edit", "grader": {"type": "mystery"}}
    row = {"task_id": "mystery", "category": "edit", "status": "completed",
           "claimed_complete": True, **bench_tasks.ungraded_verdict()}
    metrics = build_report([task], [row])["metrics"]  # type: ignore[arg-type]
    assert metrics["grading_refusal_count"] == 0, metrics
    assert metrics["no_grader_count"] == 0, metrics
    assert metrics["gradable_task_count"] == 0, metrics
    assert metrics["pass_at_1"] is None, metrics


def test_a_type_the_grader_cannot_run_is_refused_at_the_load_door() -> None:
    """Today the loader is what keeps the fallback unreachable for v2 tasks.

    So the safety net has two layers, and this test pins the one that fires first:
    an unknown type never reaches ``grade_v2`` from a shipped suite. If this ever
    goes green the other way, the fallback has become a production path.
    """
    task = {"id": "x", "category": "edit", "prompt": "p", "max_minutes": 5,
            "fixture": {"a.txt": "x"}, "grader": {"type": "mystery"}}
    with pytest.raises(ValueError, match="grader 类型非法"):
        bench_tasks.validate_task(task)
