"""Reverse-control cells for the layout gate's plane cell (M8-T239).

The file this replaces shipped with M8-T200 and passed a reverse control that should
have failed it: **none** of its three cells went red when the plane cell's own
assertion was blinded. The reason is visible on one reading - each cell built the
list it asserted on inside the cell, then checked a property of that list:

    audited_with_scripts = list(audited) + ["scripts/fake_module.py::fake_census"]
    assert set(by_plane.keys()) == {"tests", "scripts"}

That is a statement about ``PurePath("scripts/...").parts[0]``, which is true however
``_layout_audits`` behaves. ``_layout_audits`` - the code the cells name - is never
called with anything but the real repo, and its result is never fed to the gate's own
predicate.

So the cells here grow a fixture tree and put the **real** ``_layout_audits`` in front
of it. The gate's predicate (``set(by_plane) == {"tests"}``) is then evaluated on the
result, which is the only thing that makes a red meaningful. Nothing writes inside the
repository: the census modules are planted in pytest's ``tmp_path``.
"""
from __future__ import annotations

import sys
from pathlib import Path, PurePath

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tests.test_two_fixture_keys_must_share_one_workspace import (  # noqa: E402
    CENSUS_DIRS,
    REPO,
    _layout_audits,
)

# A census is in scope for the plane cell only when it both loads a shipped corpus
# and reads the fixture key. ``CORPUS_CALLS`` is ``{"load_tasks", "behavior_tasks"}``,
# so the planted module calls ``load_tasks`` itself and indexes ``task["fixture"]``.
PLANTED_CENSUS = '''"""A layout census for the plane cell's fixture tree."""


def census_of_shipped_layout():
    for task in load_tasks():
        keys = [key for key in task["fixture"]]
        return keys
'''


def _plane_predicate(roots: list[Path]) -> tuple[bool, dict[str, int]]:
    """The gate's own condition, over any set of roots."""
    audited, _, _, _ = _layout_audits(roots)
    by_plane: dict[str, int] = {}
    for site in audited:
        plane = PurePath(site).parts[0]
        by_plane[plane] = by_plane.get(plane, 0) + 1
    return set(by_plane) == {"tests"}, by_plane


def test_the_real_tree_still_reports_tests_only() -> None:
    """The shipped answer, and the reason a red on this file means something."""
    ok, by_plane = _plane_predicate([REPO / directory for directory in CENSUS_DIRS])
    assert ok is True, (
        f"the real population is not tests-only: {by_plane} - re-baseline the gate "
        "before trusting anything below"
    )
    assert sum(by_plane.values()) >= 10, (
        f"the walk audited only {sum(by_plane.values())} sites; the measured floor was "
        "12 at M8-T120, so the walk went blind"
    )


# --- fixture trees ------------------------------------------------------


def _write_census(root: Path, name: str, source: str = PLANTED_CENSUS) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{name}.py").write_text(
        "from minicc.benchmarks import load_tasks\n\n\n" + source,
        encoding="utf-8",
    )


def test_a_census_outside_tests_makes_the_gate_predicate_fail(tmp_path: Path) -> None:
    """The cell the shipped file could not write: a real census in a second plane.

    ``_layout_audits`` walks the roots it is given and reports the plane each site
    came from. Plant the same census under ``scripts/`` as well as ``tests/`` and the
    gate's condition ``set(by_plane) == {"tests"}`` is False - which is precisely the
    red the gate exists to raise on a corpus loader appearing outside tests/.
    """
    tree = tmp_path / "plane_tree"
    _write_census(tree / "tests", "census_in_tests")
    _write_census(tree / "scripts", "census_in_scripts")

    ok, by_plane = _plane_predicate([tree / "tests", tree / "scripts"])
    assert ok is False, (
        "the predicate still passes with a corpus loader outside tests/ - the gate "
        "cannot see the population move planes, and neither can this file"
    )
    assert set(by_plane) == {"tests", "scripts"}, (
        f"expected both planes populated, got {by_plane}; the fixture tree is not "
        "reaching _layout_audits"
    )


def test_a_tests_only_fixture_tree_passes_the_gate_predicate(tmp_path: Path) -> None:
    """Control for the cell above: one tree, one plane, no red."""
    tree = tmp_path / "plane_tree"
    _write_census(tree / "tests", "census_in_tests")

    ok, by_plane = _plane_predicate([tree / "tests"])
    assert ok is True, f"a tests-only population must satisfy the predicate: {by_plane}"
    assert by_plane == {"tests": 1}, f"expected exactly the planted census, got {by_plane}"


def test_a_nested_path_still_reports_its_own_plane(tmp_path: Path) -> None:
    """``where`` is ``<root.name>/<relative>/::<name>``: the plane is the root, not the path."""
    tree = tmp_path / "nested_tree"
    inner = tree / "scripts" / "audit" / "deep"
    _write_census(inner, "buried_census")

    ok, by_plane = _plane_predicate([tree / "scripts"])
    assert ok is False, (
        "a corpus loader buried under scripts/audit/deep must still fail the "
        f"predicate, got {by_plane}"
    )


def test_a_pycache_sibling_is_not_audited(tmp_path: Path) -> None:
    """The walk skips ``__pycache__``; a copy there must not add a site."""
    tree = tmp_path / "plane_tree"
    _write_census(tree / "tests", "census_in_tests")
    _write_census(tree / "tests" / "__pycache__", "census_in_pycache")

    _, by_plane = _plane_predicate([tree / "tests"])
    assert by_plane == {"tests": 1}, (
        f"a cached copy was audited: {by_plane}"
    )


def test_a_module_that_only_reads_the_key_is_not_a_census(tmp_path: Path) -> None:
    """Loading the corpus and reading the key are separate; only the conjunction counts."""
    tree = tmp_path / "plane_tree"
    reader = tree / "tests"
    reader.mkdir(parents=True, exist_ok=True)
    (reader / "reader_only.py").write_text(
        "def reads_the_key(task):\n    return [k for k in task['fixture']]\n",
        encoding="utf-8",
    )
    (tree / "scripts").mkdir(parents=True, exist_ok=True)
    (tree / "scripts" / "loader_only.py").write_text(
        "from minicc.benchmarks import load_tasks\n\n\n"
        "def loads_only():\n    return list(load_tasks())\n",
        encoding="utf-8",
    )

    audited, _, _, _ = _layout_audits([tree / "tests", tree / "scripts"])
    assert audited == [], f"a one-sided function was audited: {audited}"


def test_this_file_calls_the_real_auditor() -> None:
    """The drift guard: no cell may rebuild the audited list by hand.

    The shipped cells all assigned from ``list(audited) + [...]`` and then asserted
    on the result, which is why blinding the gate changed nothing they could see.

    Read by AST over *executable* code only. Matching the file text found the
    quoted example in this docstring instead, on the first run after writing it -
    and a guard that cannot survive its own explanation is not a guard.
    """
    import ast

    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    calls = [node.func.attr
             for node in ast.walk(tree)
             if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute)]
    assert "_layout_audits" in " ".join(calls) or "_layout_audits" in {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    }, (
        "this file stopped calling _layout_audits - its cells can only describe "
        "lists they build themselves"
    )
    # A literal site string in executable code is how the shipped cells faked it.
    planted = [node.value
               for node in ast.walk(tree)
               if isinstance(node, ast.Constant)
               and isinstance(node.value, str)
               and node.value.startswith(("scripts/", "tests/", "minicc/"))
               and "::" in node.value]
    assert planted == [], (
        f"a cell hands the predicate a site it wrote itself: {planted} - that is the "
        "shape that passed under a blinded gate"
    )
