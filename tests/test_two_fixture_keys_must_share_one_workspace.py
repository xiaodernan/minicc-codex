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


def _layout_audit_shape(node: ast.FunctionDef, graph: dict[str, set[str]]) -> tuple[bool, bool, bool]:
    """(loads a shipped corpus, reads fixture entries, decides path identity by itself).

    Only the third answer makes a function a second implementation of the rule rather than
    plumbing: walking fixtures is what every report does, comparing their paths is the owner's.
    """
    body = ast.unparse(node)
    names = graph.get(node.name, set())
    return (
        _reaches(node.name, graph, CORPUS_CALLS),
        '"fixture"' in body or "'fixture'" in body,
        "startswith" in names or ".replace(" in body,
    )


def _layout_audits(roots: list[Path]) -> tuple[list[str], list[str], int]:
    """Walk ``roots``: return (audited layout checks, ones that re-typed the comparison, files)."""
    audited: list[str] = []
    hand_copied: list[str] = []
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
                if decides_alone and not _reaches(name, graph, OWNER_CALLS):
                    hand_copied.append(f"{where}:{node.lineno}")
    return audited, hand_copied, walked


def test_no_layout_check_in_the_repo_re_types_the_owner_s_comparison() -> None:
    """The doors delegate to one owner; a test that re-types its comparison can disagree silently.

    Floors are the count this same walk got, so the gate cannot be satisfied by reading nothing.
    Measured at ``eead5ea`` after converting this file's own census: 189 python files under
    tests/, minicc/ and scripts/, and this census is one of the audited layout checks.
    """
    audited, hand_copied, walked = _layout_audits([REPO / directory for directory in CENSUS_DIRS])
    assert walked >= 180, f"the gate walked only {walked} python files - it read almost nothing"
    assert len(audited) >= 8, f"the gate looked at only {len(audited)} layout checks"
    assert any(site.endswith("::test_no_shipped_task_carries_a_colliding_pair") for site in audited), (
        f"this file's own census is not even inside the audited population: {audited}"
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

    Without this the assertion above could be green because the predicate went blind - which is
    exactly how the census in this file stayed green while its comparison drifted from the doors.
    """
    planted = tmp_path / "planted"
    planted.mkdir()
    (planted / "test_planted_census.py").write_text(PLANTED_CENSUS, encoding="utf-8")
    audited, hand_copied, walked = _layout_audits([planted])
    assert walked == 1, f"the planted file never reached the walk: {walked}"
    assert audited == ["planted/test_planted_census.py::census_of_shipped_layout"], (
        f"the plant must land inside the audited population, got {audited}"
    )
    assert len(hand_copied) == 1, f"the gate must name the planted census, got {hand_copied}"
    assert hand_copied[0].startswith("planted/test_planted_census.py::census_of_shipped_layout:"), (
        f"the named offender is not the plant: {hand_copied}"
    )
