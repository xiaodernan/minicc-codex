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


def test_no_shipped_task_carries_a_colliding_pair() -> None:
    """Census: the rule must not be refusing anything the corpus actually contains.

    The floors come from this same scan, so narrowing the population cannot quietly make the
    check vacuous.
    """
    suites = {
        "legacy": benchmarks.load_tasks(),
        "v2": json.loads((REPO / "benchmarks" / "tasks.v2.json").read_text(encoding="utf-8")),
        "behavior": list(behavior_bench.behavior_tasks()),
    }
    suites["v2"] = suites["v2"]["tasks"] if isinstance(suites["v2"], dict) else suites["v2"]
    offenders: list[tuple[str, str, str, str]] = []
    items = 0
    for label, tasks in suites.items():
        assert len(tasks) >= 10, f"{label}: only {len(tasks)} tasks loaded - the census read nothing"
        for task in tasks:
            fixture = task.get("fixture") if isinstance(task, dict) else None
            if not isinstance(fixture, dict):
                continue
            paths = []
            for relative in fixture:
                normalised = "/".join(
                    segment for segment in str(relative).replace(BACKSLASH, "/").split("/")
                    if segment and segment != "."
                )
                paths.append((normalised, relative))
            items += len(paths)
            for index, (path, relative) in enumerate(paths):
                for other_path, other_relative in paths[index + 1:]:
                    if path == other_path or other_path.startswith(path + "/") or path.startswith(other_path + "/"):
                        offenders.append((label, str(task.get("id")), str(relative), str(other_relative)))
    assert items >= 30, f"the census walked only {items} fixture entries"
    assert offenders == [], f"shipped tasks would now be refused: {offenders[:5]}"
