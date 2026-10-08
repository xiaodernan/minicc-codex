"""M8-T177: a module-qualified call through a module the file never bound.

Measured at HEAD (2026-10-08): ``minicc/benchmarks.py`` promised behaviour tasks
their own load-time door - "Behavior tasks must also pass their own load-time
door ... so the agent never starts on a task the grader will refuse" - and then
called ``behavior_bench.validate_behavior_task(task)``. The file imports that
function *by name* (``from .behavior_bench import ...``) and never binds the
module, so the door was a ``NameError``:

    >>> benchmarks.load_tasks(Path("benchmarks/behavior-tasks.json"))
    NameError: name 'behavior_bench' is not defined

The shipped corpus has 12 ``python_behavior`` tasks. Nothing walked them through
this loader: the suite's own tests read the file with ``json.loads`` or through
``behavior_tasks()``, and the CLI's ``--suite behavior`` branch validates through
its own call inside ``main()``. Two call sites in the source, zero executions on
this path - the door existed twice and ran nowhere.

The gate below has three halves, because three different mutations each break a
different half: the package-wide scan (a name that is never bound), the shipped
corpus actually loading (the door runs on real data), and a bad task actually
being refused (the door is live rather than decorative).
"""
from __future__ import annotations

import ast
import builtins
import json
from pathlib import Path

import pytest

from minicc.benchmarks import load_tasks

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_ROOT = REPO_ROOT / "minicc"
BEHAVIOUR_CORPUS = REPO_ROOT / "benchmarks" / "behavior-tasks.json"
LEGACY_CORPUS = REPO_ROOT / "benchmarks" / "tasks.json"

#: Names a module can use without any local binding: the interpreter's own, plus
#: the dunders a module body legitimately reads. Everything else has to be bound
#: by an import, an assignment, a def, or a parameter somewhere in the file.
_UNBOUND_BY_DESIGN = set(dir(builtins)) | {
    "__file__", "__name__", "__doc__", "__spec__", "__package__",
    "__builtins__", "__all__", "__dict__", "__path__", "__loader__",
}


def _bound_names(tree: ast.Module) -> set[str]:
    """Every name the module binds anywhere, at any scope.

    Deliberately over-inclusive: a name bound in one function and used as an
    attribute base in another is a different bug (and pyflakes' job), not this
    one. This gate asks only the question it can answer soundly - "is this base
    name bound *somewhere* in this file" - so that it never fires on a local.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            names.update(node.names)
    return names


def _unbound_attribute_bases(path: Path) -> list[str]:
    """``module.attr`` call sites whose base name this file never binds."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bound = _bound_names(tree)
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            base = node.value.id
            if base not in bound and base not in _UNBOUND_BY_DESIGN:
                offenders.append(f"{path.relative_to(REPO_ROOT).as_posix()}:{node.lineno}: {base}.{node.attr}")
    return offenders


def test_every_module_qualified_call_in_the_package_resolves() -> None:
    """The scan that found M8-T177, kept.

    One finding on the whole package at the time this gate was written, and zero
    false positives - which is what makes it worth keeping: a check that fires on
    correct code teaches readers to ignore it (M8-T22).
    """
    scanned = sorted(PACKAGE_ROOT.rglob("*.py"))
    assert len(scanned) >= 20, f"only {len(scanned)} modules scanned - the scan saw nothing"
    offenders: list[str] = []
    for path in scanned:
        offenders.extend(_unbound_attribute_bases(path))
    assert offenders == [], offenders


def test_the_shipped_behaviour_corpus_loads_through_the_legacy_loader() -> None:
    """The door runs on the real file, not on a fixture that flatters it.

    ``--suite legacy --fixtures benchmarks/behavior-tasks.json`` is the path this
    fixes; before the fix it died with a NameError before the first task ran.
    """
    tasks = load_tasks(BEHAVIOUR_CORPUS)
    raw = json.loads(BEHAVIOUR_CORPUS.read_text(encoding="utf-8"))
    assert len(tasks) == len(raw) >= 10, (len(tasks), len(raw))
    assert [task["id"] for task in tasks] == [task["id"] for task in raw]
    assert {(task.get("grader") or {}).get("type") for task in tasks} == {"python_behavior"}


def test_the_legacy_loader_refuses_a_behaviour_task_the_grader_would_refuse(tmp_path: Path) -> None:
    """A door that opens for everything is not a door.

    An unscoreable spec (no cases and no raises) must be refused by the loader
    itself, by task id, as a ``ValueError`` - the same verdict the CLI's
    behaviour branch and the grader give, not a crash and not a silent load.
    """
    bad = {
        "id": "behaviour-that-checks-nothing",
        "category": "edit",
        "prompt": "fix it",
        "grader": {"type": "python_behavior", "function": "f", "cases": []},
        "fixture": {"solution.py": "def f(a, b):\n    return a + b\n"},
    }
    path = tmp_path / "behaviour.json"
    path.write_text(json.dumps([bad]), encoding="utf-8")
    with pytest.raises(ValueError) as refusal:
        load_tasks(path)
    assert "behaviour-that-checks-nothing" in str(refusal.value), refusal.value

    good = dict(bad, id="behaviour-that-checks-something",
                grader={"type": "python_behavior", "function": "f",
                        "cases": [[[1, 2], 3]], "raises": [], "preserve_inputs": True})
    good["fixture"] = dict(good["fixture"], **{"README.md": "把两数加起来。\n"})
    path.write_text(json.dumps([good]), encoding="utf-8")
    assert [task["id"] for task in load_tasks(path)] == ["behaviour-that-checks-something"]


def test_the_legacy_corpus_still_loads_untouched() -> None:
    """The fix is a one-line name repair, not a widening of the door.

    ``validate_behavior_task`` refuses any grader type outside the behaviour
    vocabulary, so calling it on every task would break the legacy suite this
    loader exists for. This is the arm that keeps the repair narrow.
    """
    tasks = load_tasks(LEGACY_CORPUS)
    assert len(tasks) >= 20, f"legacy suite reads {len(tasks)} tasks"
    assert all(not task.get("grader") or (task["grader"] or {}).get("type") not in ("python_behavior", "answer_rubric") for task in tasks)


def test_the_loader_door_is_one_function_shared_with_the_cli_branch() -> None:
    """Two call sites, one door: the loader must call the validator by name.

    The bug was a name-resolution failure, so the structural half of the gate is
    about the name: ``load_tasks`` has to reach ``validate_behavior_task`` as a
    bare imported name, the same call ``main()`` makes for ``--suite behavior``.
    A second qualified spelling (``behavior_bench.validate_behavior_task``) is
    how the first one broke.
    """
    tree = ast.parse((PACKAGE_ROOT / "benchmarks.py").read_text(encoding="utf-8"))
    loader = next(node for node in ast.walk(tree)
                  if isinstance(node, ast.FunctionDef) and node.name == "load_tasks")
    calls = {ast.unparse(node) for node in ast.walk(loader)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
             and node.func.id == "validate_behavior_task"}
    assert calls == {"validate_behavior_task(task)"}, sorted(calls)
