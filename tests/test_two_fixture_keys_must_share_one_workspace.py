"""M8-T107: two fixture keys must be able to share one workspace.

Each load door checked every key on its own and never a pair. Measured on the unmodified
plane (`e88aa4e`): ``"./a.txt"`` after ``"a.txt"`` silently overwrote the first file and wrote
no error anywhere, ``"a.txt"`` with ``"a.txt/b.txt"`` raised ``FileExistsError`` after already
writing ``a.txt`` (a half-built workspace), and ``"d/x"`` with ``"d"`` raised
``PermissionError``. ``require_writable_fixture`` is the single owner of the rule, so all three
doors get it by asking it.

Batch-91's lessons are applied here: the door matrix is one case per (shape, door) pair,
because a loop over doors inside one test aborts at the first refusal and never exercises the
later doors.
"""

from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path

import pytest

from minicc import bench_tasks, behavior_bench, benchmarks

REPO = Path(__file__).resolve().parents[1]

BACKSLASH = chr(92)

# Every shape is added on top of a real shipped task's own fixture, so a refusal can only come
# from the pair, never from an unrelated required key.
COLLIDING: dict[str, dict[str, str]] = {
    "dot-prefix duplicate": {"a.txt": "one", "./a.txt": "two"},
    "double-slash duplicate": {"p//q.txt": "one", "p/q.txt": "two"},
    "separator-spelling duplicate": {f"d{BACKSLASH}f.txt": "one", "d/f.txt": "two"},
    "file-then-child": {"a.txt": "one", "a.txt/b.txt": "two"},
    "child-then-file": {"d/x": "one", "d": "two"},
    "deep-then-shallow": {"p/q/r": "1", "p/q": "2"},
}
DOORS = ("v2", "behavior", "legacy")
GOOD_LAYOUT = {"pkg/__init__.py": "", "pkg/mod.py": "x", "a.txt": "one"}


def _shipped_task(door: str) -> dict:
    """A real task from the shipped corpus, so the only new thing is the fixture pair."""
    if door == "v2":
        payload = json.loads((REPO / "benchmarks" / "tasks.v2.json").read_text(encoding="utf-8"))
        tasks = payload["tasks"] if isinstance(payload, dict) else payload
        chosen = next(task for task in tasks if task.get("fixture"))
    elif door == "behavior":
        chosen = next(task for task in behavior_bench.behavior_tasks() if task.get("fixture"))
    else:
        chosen = next(task for task in benchmarks.load_tasks() if not task.get("grader"))
    return json.loads(json.dumps(chosen))


def _run_door(door: str, fixture: dict, tmp_path: Path) -> None:
    task = _shipped_task(door)
    task["fixture"] = {**(task.get("fixture") or {}), **fixture}
    task["id"] = f"{task.get('id')}-pair"
    if door == "v2":
        bench_tasks.validate_task(task)
    elif door == "behavior":
        behavior_bench.validate_behavior_task(task)
    else:
        path = tmp_path / "legacy-pair.json"
        path.write_text(json.dumps([task], ensure_ascii=False), encoding="utf-8")
        benchmarks.load_tasks(path)


@pytest.mark.parametrize("door", DOORS)
@pytest.mark.parametrize("label", sorted(COLLIDING))
def test_every_load_door_refuses_keys_that_cannot_share_a_workspace(
    label: str, door: str, tmp_path: Path
) -> None:
    """This (shape, door) cell must refuse: one owner, asked by all three doors."""
    with pytest.raises(ValueError) as caught:
        _run_door(door, COLLIDING[label], tmp_path)
    message = str(caught.value)
    assert "fixture 键" in message, f"{label}/{door}: refusal must name the keys: {message}"


@pytest.mark.parametrize("door", DOORS)
def test_the_legitimate_nested_layout_still_loads_through_every_door(door: str, tmp_path: Path) -> None:
    """A directory and a file inside it are legal: the rule is about collisions, not nesting."""
    task = _shipped_task(door)
    task["fixture"] = {**(task.get("fixture") or {}), **GOOD_LAYOUT}
    if door == "v2":
        bench_tasks.validate_task(task)
    elif door == "behavior":
        behavior_bench.validate_behavior_task(task)
    else:
        path = tmp_path / "legacy-good.json"
        path.write_text(json.dumps([task], ensure_ascii=False), encoding="utf-8")
        assert any(item.get("fixture") for item in benchmarks.load_tasks(path))


def test_dict_order_does_not_change_the_answer() -> None:
    """Pass 1 of this rule checked only prefixes of the key being inserted, so ``{d: ..., d/x:
    ...}`` was refused while ``{d/x: ..., d: ...}`` loaded. Both orders must refuse now."""
    first = {"d": "one", "d/x": "two"}
    second = {"d/x": "two", "d": "one"}
    with pytest.raises(ValueError):
        bench_tasks.require_writable_fixture({"id": "order-a", "fixture": first})
    with pytest.raises(ValueError):
        bench_tasks.require_writable_fixture({"id": "order-b", "fixture": second})


def test_the_refusal_names_the_task_and_both_keys() -> None:
    """A refusal that only says "collision" cannot be acted on in a 39-file corpus."""
    for fixture in COLLIDING.values():
        keys = list(fixture)
        with pytest.raises(ValueError) as caught:
            bench_tasks.require_writable_fixture({"id": "naming", "fixture": fixture})
        message = str(caught.value)
        for key in keys:
            assert repr(key) in message, f"refusal must name {key!r}: {message}"
        assert "'naming'" in message, f"refusal must name the task id: {message}"


def test_the_pair_rule_has_one_owner_across_the_module_tree() -> None:
    """The comparison must live in the owner the doors already ask, not be re-typed per door."""
    owners = []
    for path in sorted((REPO / "minicc").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "require_writable_fixture":
                body = ast.unparse(node)
                if "父目录" in body and "同一个位置" in body:
                    owners.append(path.name)
    assert owners == ["bench_tasks.py"], (
        f"the pair rule must live in exactly one owner; found it in {owners}"
    )


def test_the_host_still_leaves_a_half_built_workspace(tmp_path: Path) -> None:
    """The door is the only thing between the agent and a partial workspace: the write point
    itself is unchanged, so its measured behaviour is pinned here as the reason."""
    root = tmp_path / "workspace"
    root.mkdir()
    with pytest.raises(OSError) as caught:
        behavior_bench.prepare_fixture({"fixture": COLLIDING["file-then-child"]}, root)
    left = sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))
    assert left == ["a.txt"], f"expected the host to stop after a.txt, tree was {left}"
    assert isinstance(caught.value, FileExistsError), type(caught.value).__name__


def _shipped_populations() -> dict[str, list[dict]]:
    """The three corpora exactly as their own doors load them."""
    payload = json.loads((REPO / "benchmarks" / "tasks.v2.json").read_text(encoding="utf-8"))
    v2 = payload["tasks"] if isinstance(payload, dict) else payload
    return {
        "legacy": list(benchmarks.load_tasks()),
        "v2": list(v2),
        "behavior": list(behavior_bench.behavior_tasks()),
    }


def _fixture_refusals(tasks: list[dict]) -> list[tuple[str, str]]:
    """Audit a population by asking the owner the doors ask - never a copy of its comparison."""
    refusals: list[tuple[str, str]] = []
    for task in tasks:
        fixture = task.get("fixture") if isinstance(task, dict) else None
        if not isinstance(fixture, dict):
            continue
        try:
            bench_tasks.require_writable_fixture(task)
        except ValueError as exc:
            refusals.append((str(task.get("id")), str(exc)))
    return refusals


def test_no_shipped_task_carries_a_colliding_pair() -> None:
    """Census: the rule must not be refusing anything the corpus actually contains.

    This walk used to re-type the owner's comparison by hand. Measured at ``eead5ea``, that copy
    accepted three layouts the owner refuses - ``{"A.txt", "a.txt"}``, ``{"p/q.txt", "P/Q.txt"}``
    and ``{"P", "p/q.txt"}`` - and was never stricter than it, so "the corpus is clean" could
    drift away from what the doors enforce while staying green. The audit now asks the owner;
    ``test_the_layout_census_names_a_planted_pair`` is what gives "no offenders" its reach.

    The floors come from this same walk, so narrowing the population cannot make it vacuous.
    Measured on the plane this ships from: legacy 30 tasks carrying 0 fixtures, v2 24 tasks /
    39 keys, behavior 12 tasks / 24 keys.
    """
    offenders: list[tuple[str, str]] = []
    items = 0
    for label, tasks in _shipped_populations().items():
        assert len(tasks) >= 10, f"{label}: only {len(tasks)} tasks loaded - the census read nothing"
        items += sum(len(task["fixture"]) for task in tasks if isinstance(task.get("fixture"), dict))
        offenders.extend((f"{label}/{task_id}", detail) for task_id, detail in _fixture_refusals(tasks))
    assert items >= 50, f"the census walked only {items} fixture entries"
    assert offenders == [], f"shipped tasks would now be refused: {offenders[:5]}"


PLANTED_POPULATION: list[dict] = [
    {"id": "planted-file-over-its-own-child",
     "fixture": {"a.txt": "1", "a.txt/b.txt": "2", "keep/one.txt": "3", "keep/two.txt": "4"}},
    {"id": "planted-case-duplicate",
     "fixture": {"Dir/Report.txt": "5", "dir/report.txt": "6", "keep/three.txt": "7",
                 "keep/four.txt": "8"}},
    {"id": "planted-clean", "fixture": {"pkg/__init__.py": "9", "pkg/mod.py": "10"}},
]


@pytest.mark.parametrize("policy", ("fold", "identity"))
def test_the_layout_census_names_a_planted_pair(policy: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """"Zero offenders" must be able to name an offender, and must know which half is the host.

    The census walks a population this file supplies: one pair that collides by layout (a file
    sitting on its own child) and one that collides only where the volume folds case. A folding
    policy has to name both, a case-sensitive one only the layout pair - so the census inherits
    the owner's dependence on the host instead of silently assuming either answer.
    """
    monkeypatch.setattr(os.path, "normcase", (lambda value: value.lower()) if policy == "fold"
                        else (lambda value: value))
    named = sorted(task_id for task_id, _ in _fixture_refusals(PLANTED_POPULATION))
    assert len(PLANTED_POPULATION) == 3, "the planted population lost a task - the audit read nothing"
    if policy == "fold":
        assert named == ["planted-case-duplicate", "planted-file-over-its-own-child"], (
            f"a folding volume must show both collisions, named {named}"
        )
    else:
        assert named == ["planted-file-over-its-own-child"], (
            f"on a case-sensitive volume 'Dir/Report.txt' and 'dir/report.txt' are two files, "
            f"named {named}"
        )


CENSUS_DIRS = ("tests", "minicc", "scripts")
CORPUS_CALLS = {"load_tasks", "behavior_tasks"}
OWNER_CALLS = {"require_writable_fixture", "validate_task", "validate_behavior_task"}

#: The spellings a census can use to decide path identity without the owner.
#: Measured at 第一百一十批 (M8-T129): the probe named only two of them, so a census
#: written with ``os.path.commonprefix``, ``PurePosixPath.parts``, a slice,
#: ``removeprefix``, case folding or path normalisation was invisible to it. The wide
#: alternative - "does this body compare anything at all?" - was measured on this same
#: walk and named three sites that are plumbing rather than hand copies, so this stays a
#: list of names instead of a question about comparisons. Every entry has one planted
#: sample in ``test_a_hand_copied_census_is_named_whatever_spelling_it_uses``; that test
#: is what turns an entry here into a red cell when the walk stops recognising it.
IDENTITY_CALLS = frozenset({"startswith", "removeprefix", "casefold", "lower",
                            "commonprefix", "normpath", "abspath", "realpath"})
IDENTITY_ATTRS = (".replace(", ".parts")


def _call_names(node: ast.AST) -> set[str]:
    """Every function or method name this body calls, bare or attribute-reached."""
    return {
        call.func.attr if isinstance(call.func, ast.Attribute) else call.func.id
        for call in ast.walk(node)
        if isinstance(call, ast.Call) and isinstance(call.func, (ast.Attribute, ast.Name))
    }


def _reaches(name: str, graph: dict[str, set[str]], targets: set[str],
             seen: frozenset[str] = frozenset()) -> bool:
    """Does this function reach one of ``targets``, directly or through a same-module helper?"""
    if name in seen:
        return False
    calls = graph.get(name, set())
    if calls & targets:
        return True
    return any(_reaches(other, graph, targets, seen | {name}) for other in calls)


def _decides_identity_alone(node: ast.FunctionDef, graph: dict[str, set[str]],
                            body: str) -> bool:
    """Does this body decide path identity itself instead of asking the owner?

    Three routes, in the order a reader meets them: a call name from ``IDENTITY_CALLS``,
    a marker from ``IDENTITY_ATTRS``, and a slice - a prefix compare that has no method
    name to catch (``key[:len(other)] == other``). Only the third is structural; the
    first two are the names this walk has actually been shown.
    """
    if graph.get(node.name, set()) & IDENTITY_CALLS:
        return True
    if any(mark in body for mark in IDENTITY_ATTRS):
        return True
    return any(isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Slice)
               for n in ast.walk(node))


def _layout_audit_shape(node: ast.FunctionDef, graph: dict[str, set[str]]) -> tuple[bool, bool, bool]:
    """(loads a shipped corpus, reads fixture entries, decides path identity by itself).

    Only the third answer makes a function a second implementation of the rule rather than
    plumbing: walking fixtures is what every report does, comparing their paths is the owner's.
    """
    body = ast.unparse(node)
    return (
        _reaches(node.name, graph, CORPUS_CALLS),
        '"fixture"' in body or "'fixture'" in body,
        _decides_identity_alone(node, graph, body),
    )


def _layout_audits(roots: list[Path]) -> tuple[list[str], list[str], int, int]:
    """Walk ``roots``: return (audited layout checks, ones that re-typed, ones that delegated, files).

    The third answer is why the fourth cell of the gate can go red at all: a population in which
    nothing is classified ``decides_alone`` cannot name a hand copy, so "no offenders" proves
    nothing until a positive count of the owner's own calls is asserted beside it.
    """
    audited: list[str] = []
    hand_copied: list[str] = []
    delegating = 0
    walked = 0
    for root in roots:
        paths = sorted(root.rglob("*.py")) if root.is_dir() else []
        for path in paths:
            if "__pycache__" in path.parts:
                continue
            walked += 1
            tree = ast.parse(path.read_text(encoding="utf-8"))
            defs = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
            graph = {name: _call_names(node) for name, node in defs.items()}
            for name, node in defs.items():
                loads, reads_fixtures, decides_alone = _layout_audit_shape(node, graph)
                if not (loads and reads_fixtures):
                    continue
                where = f"{root.name}/{path.relative_to(root).as_posix()}::{name}"
                audited.append(where)
                if _reaches(name, graph, OWNER_CALLS):
                    delegating += 1
                if decides_alone and not _reaches(name, graph, OWNER_CALLS):
                    hand_copied.append(f"{where}:{node.lineno}")
    return audited, hand_copied, delegating, walked


def test_the_layout_gate_walks_a_real_number_of_files() -> None:
    """Cell 1 of the layout gate: the walk covers the repo, not a corner of it.

    Four cells instead of one test with four assertions, because assertions stacked in one body
    short-circuit: an arm that broke only the third could never be seen while the first was red.
    Floors are what this same walk measured, so the gate cannot be satisfied by reading nothing.
    Measured at ``eead5ea`` after converting this file's own census: 189 python files under
    tests/, minicc/ and scripts/; 203 at the split (batch 109).
    """
    _, _, _, walked = _layout_audits([REPO / directory for directory in CENSUS_DIRS])
    assert walked >= 180, f"the gate walked only {walked} python files - it read almost nothing"


def test_the_layout_gate_finds_a_real_population_of_layout_checks() -> None:
    """Cell 2: the shape matcher still recognises a layout check when it sees one.

    Twelve sites at the split. This floor is what keeps cells 3 and 4 from being answered by an
    empty population - and it is the cell that goes red when the matcher's own reading of
    ``fixture`` is switched off, which leaves the walk (cell 1) untouched.
    """
    audited, _, _, _ = _layout_audits([REPO / directory for directory in CENSUS_DIRS])
    assert len(audited) >= 8, f"the gate looked at only {len(audited)} layout checks"


def test_the_layout_gate_audits_its_own_census() -> None:
    """Cell 3: this file's own census sits inside the population the gate audits.

    The census at ``test_no_shipped_task_carries_a_colliding_pair`` reaches the shipped corpus
    through the helper ``_shipped_populations``, so this cell is also the witness that the shape
    matcher follows a call chain rather than only direct calls.
    """
    audited, _, _, _ = _layout_audits([REPO / directory for directory in CENSUS_DIRS])
    assert any(site.endswith("::test_no_shipped_task_carries_a_colliding_pair") for site in audited), (
        f"this file's own census is not even inside the audited population: {audited}"
    )


def test_the_layout_gate_sees_the_population_delegate_to_one_owner() -> None:
    """Cell 4: the doors delegate to one owner; a test that re-types its comparison can disagree.

    The negative half (nothing decides alone) is worth keeping but cannot carry the cell: at the
    split, 0 of the 12 audited sites are classified ``decides_alone``, so no amount of editing
    ``OWNER_CALLS`` can make ``hand_copied`` non-empty - the assertion was reachable only through
    the plant in ``test_the_layout_gate_names_a_hand_copied_census``. The positive half is what
    gives this cell an arm: 8 of 12 audited sites reach an owner call today, and a gate whose
    owner list has quietly lost ``require_writable_fixture`` still sees all twelve sites while
    recognising only five of them as delegation.
    """
    audited, hand_copied, delegating, _ = _layout_audits(
        [REPO / directory for directory in CENSUS_DIRS]
    )
    assert delegating >= 6, (
        f"only {delegating} of {len(audited)} layout checks reach an owner call {sorted(OWNER_CALLS)}"
        f" - the gate can no longer tell delegation from a hand copy"
    )
    assert hand_copied == [], f"these decide fixture layout by hand: {hand_copied}"


PLANTED_CENSUS = r'''
"""A layout census written the way the one in this file used to be."""
from minicc.benchmarks import load_tasks


def census_of_shipped_layout():
    bad = []
    for task in load_tasks():
        keys = [key.replace("\\", "/") for key in task["fixture"]]
        for index, key in enumerate(keys):
            for other in keys[index + 1:]:
                if key == other or other.startswith(key + "/"):
                    bad.append(task["id"])
    return bad
'''


def test_the_layout_gate_names_a_hand_copied_census(tmp_path: Path) -> None:
    """The refusing half of the gate: one planted file through the same walk, not a new matcher.

    Without this the negative half of cell 4 could be green because the predicate went blind -
    which is exactly how the census in this file stayed green while its comparison drifted from
    the doors. The plant is also the only thing that has ever made ``hand_copied`` non-empty:
    measured at the split, 0 of the 12 real audited sites are classified ``decides_alone``.
    """
    planted = tmp_path / "planted"
    planted.mkdir()
    (planted / "test_planted_census.py").write_text(PLANTED_CENSUS, encoding="utf-8")
    audited, hand_copied, delegating, walked = _layout_audits([planted])
    assert walked == 1, f"the planted file never reached the walk: {walked}"
    assert audited == ["planted/test_planted_census.py::census_of_shipped_layout"], (
        f"the plant must land inside the audited population, got {audited}"
    )
    assert delegating == 0, (
        f"a planted hand copy must not read as delegation to the owner, got {delegating}"
    )
    assert len(hand_copied) == 1, f"the gate must name the planted census, got {hand_copied}"
    assert hand_copied[0].startswith("planted/test_planted_census.py::census_of_shipped_layout:"), (
        f"the named offender is not the plant: {hand_copied}"
    )


IDENTITY_PLANTS: dict[str, str] = {
    "startswith": r'''
"""A census whose prefix test is spelled with str.startswith."""
from minicc.benchmarks import load_tasks


def census():
    bad = []
    for task in load_tasks():
        keys = list(task["fixture"])
        for key in keys:
            for other in keys:
                if key.startswith(other + "/"):
                    bad.append(task["id"])
    return bad
''',
    "replace": r'''
"""A census that normalises separators with str.replace."""
from minicc.benchmarks import load_tasks


def census():
    bad = []
    for task in load_tasks():
        keys = [key.replace("\\", "/") for key in task["fixture"]]
        for key in keys:
            for other in keys:
                if key == other:
                    bad.append(task["id"])
    return bad
''',
    "commonprefix": r'''
"""A census that decides a shared prefix with os.path.commonprefix."""
import os

from minicc.benchmarks import load_tasks


def census():
    bad = []
    for task in load_tasks():
        keys = list(task["fixture"])
        for key in keys:
            for other in keys:
                if os.path.commonprefix([key, other]) == key and key != other:
                    bad.append(task["id"])
    return bad
''',
    "parts": r'''
"""A census that compares PurePosixPath.parts."""
from pathlib import PurePosixPath

from minicc.benchmarks import load_tasks


def census():
    bad = []
    for task in load_tasks():
        keys = list(task["fixture"])
        for key in keys:
            for other in keys:
                if PurePosixPath(key).parts == PurePosixPath(other).parts:
                    bad.append(task["id"])
    return bad
''',
    "slice": r'''
"""A census that reads a prefix off the front with a slice."""
from minicc.benchmarks import load_tasks


def census():
    bad = []
    for task in load_tasks():
        keys = list(task["fixture"])
        for key in keys:
            for other in keys:
                if key[: len(other)] == other and key != other:
                    bad.append(task["id"])
    return bad
''',
    "removeprefix": r'''
"""A census that strips a prefix with str.removeprefix."""
from minicc.benchmarks import load_tasks


def census():
    bad = []
    for task in load_tasks():
        keys = list(task["fixture"])
        for key in keys:
            for other in keys:
                if key.removeprefix(other) != key:
                    bad.append(task["id"])
    return bad
''',
    "lower": r'''
"""A census that folds case with str.lower before comparing."""
from minicc.benchmarks import load_tasks


def census():
    bad = []
    for task in load_tasks():
        keys = list(task["fixture"])
        for key in keys:
            for other in keys:
                if key.lower() == other.lower() and key != other:
                    bad.append(task["id"])
    return bad
''',
    "normpath": r'''
"""A census that normalises the path with os.path.normpath."""
import os

from minicc.benchmarks import load_tasks


def census():
    bad = []
    for task in load_tasks():
        keys = list(task["fixture"])
        for key in keys:
            for other in keys:
                if os.path.normpath(key) == os.path.normpath(other) and key != other:
                    bad.append(task["id"])
    return bad
''',
}


@pytest.mark.parametrize("spelling", sorted(IDENTITY_PLANTS))
def test_a_hand_copied_census_is_named_whatever_spelling_it_uses(
    spelling: str, tmp_path: Path
) -> None:
    """Every spelling in ``IDENTITY_CALLS`` / ``IDENTITY_ATTRS`` has a sample that must be named.

    One plant per spelling, and each plant fires exactly one rule - measured before this test
    existed, because a plant that trips two rules could not lose one of them. That property is
    what makes a removal arm land on this cell alone: take ``commonprefix`` out of the list and
    the ``commonprefix`` plant goes red while the other seven stay green.

    The plant is also the reach for the wide alternative. A predicate of "does it compare
    anything" names this plant too, but it also names three sites of the real population that
    are plumbing rather than hand copies - which is the cost this list of names is avoiding,
    and which cell 4 of the layout gate still refuses.
    """
    root = tmp_path / "planted"
    root.mkdir()
    (root / f"test_planted_{spelling}.py").write_text(IDENTITY_PLANTS[spelling], encoding="utf-8")
    audited, hand_copied, delegating, walked = _layout_audits([root])
    site = f"planted/test_planted_{spelling}.py::census"
    assert walked == 1, f"the {spelling} plant never reached the walk: {walked}"
    assert audited == [site], f"the {spelling} plant must land in the audited population: {audited}"
    assert delegating == 0, f"a hand copy must not read as delegation: {delegating}"
    assert len(hand_copied) == 1, (
        f"the {spelling} spelling is in IDENTITY_* but this walk did not name it: {hand_copied}"
    )
    assert hand_copied[0].startswith(site + ":"), f"the named offender is not the plant: {hand_copied}"
