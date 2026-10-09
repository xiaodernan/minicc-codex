"""M8-T106: a fixture must be text the workspace can actually hold.

``prepare_fixture`` used to write ``str(content)``, so a task that spelled its fixture as a
nested object handed the agent a file containing Python repr - ``{'items': [1, 2]}`` is not
valid JSON, and the agent was charged for a workspace the host could not author. The write
path also opens whatever key the task spelled, so a key naming a directory (empty, a bare
dot, a trailing separator) raised in the host, and a Windows drive-absolute key slipped past
the leading-slash escape test. Text-mode writing was the third corruption, found by measuring
this file: an authored CRLF came back as two newlines.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from minicc import behavior_bench, bench_tasks, benchmarks  # noqa: E402

SOLUTION = "def clamp(value):\n    return 1 if value > 0 else 0\n"

BAD_FIXTURES = {
    "nested object": {"data.json": {"items": [1, 2], "note": "hello"}},
    "nested list": {"list.yaml": ["a", "b"]},
    "number": {"n.txt": 123},
    "boolean": {"flag.txt": True},
    "null": {"none.txt": None},
    "non-string key": {7: "content"},
    "empty key": {"": "content"},
    "dot key": {".": "content"},
    "directory key": {"nested/": "content"},
    "drive absolute key": {"C:/Windows/probe.txt": "content"},
    "escaping key": {"sub/../escape.txt": "content"},
}

DOORS = ("v2", "behavior", "legacy")


def _v2_task(fixture: dict) -> dict:
    return {
        "id": "fixture-honesty-v2",
        "category": "editing",
        "prompt": "edit the file",
        "max_minutes": 5,
        "fixture": fixture,
        "grader": {"type": "file_contract", "files": [{"path": "data.json", "contains": "items"}]},
    }


def _behavior_task(fixture: dict) -> dict:
    base = {"solution.py": SOLUTION}
    base.update(fixture)
    return {
        "id": "fixture-honesty-behavior",
        "category": "python",
        "prompt": "keep clamp working",
        "max_minutes": 5,
        "fixture": base,
        "grader": {"type": "python_behavior", "function": "clamp",
                   "cases": [[[1], 1]], "raises": [], "preserve_inputs": False},
    }


@pytest.mark.parametrize("door", DOORS)
@pytest.mark.parametrize("label", sorted(BAD_FIXTURES))
def test_every_load_door_refuses_a_fixture_the_workspace_cannot_hold(label, door, tmp_path: Path) -> None:
    """Each door gets its own case: an earlier raise must not hide the later doors.

    The matrix began as a loop over the three doors, which aborts at the first ``ValueError``
    and so never reached the legacy door for any shape v2 already refused - an arm that
    disconnected the legacy door measured zero reds. One (case, door) pair per case is what
    makes a removed door observable.
    """
    offending = dict(BAD_FIXTURES[label])
    expected_key = next(iter(offending))
    if door == "legacy" and not isinstance(expected_key, str):
        # A JSON task file cannot carry a non-string key (the writer stringifies it), so the
        # legacy door is never handed this shape.
        return
    if door == "v2":
        task_id, invoke = "fixture-honesty-v2", lambda: bench_tasks.validate_task(_v2_task(offending))
    elif door == "behavior":
        task_id, invoke = ("fixture-honesty-behavior",
                           lambda: behavior_bench.validate_behavior_task(_behavior_task(offending)))
    else:
        task_id = "fixture-honesty-legacy"
        path = tmp_path / "legacy.json"
        path.write_text(
            json.dumps([{"id": task_id, "category": "editing", "prompt": "edit",
                         "fixture": offending}], ensure_ascii=False),
            encoding="utf-8",
        )
        invoke = lambda: benchmarks.load_tasks(path)  # noqa: E731 - the door under test
    with pytest.raises(ValueError) as exc:
        invoke()
    message = str(exc.value)
    assert task_id in message, f"{door} door did not name the task: {message}"
    # str() of an empty key is "" and always "in" a message, so repr is the honest check.
    named = repr(expected_key) in message or (str(expected_key) != "" and str(expected_key) in message)
    assert named, f"{door} door did not name the offending key {expected_key!r}: {message}"


def test_an_honest_fixture_still_loads_through_all_three_doors(tmp_path: Path) -> None:
    v2_fixture = {"README.md": "# hello\n", "src/data.json": '{"items": [1, 2]}'}
    bench_tasks.validate_task(_v2_task(v2_fixture))
    behavior_bench.validate_behavior_task(_behavior_task({"data.json": '{"items": [1, 2]}'}))
    legacy_path = tmp_path / "legacy.json"
    legacy_path.write_text(
        json.dumps([{"id": "honest-legacy", "category": "editing", "prompt": "edit",
                     "fixture": v2_fixture}], ensure_ascii=False),
        encoding="utf-8",
    )
    assert [task["id"] for task in benchmarks.load_tasks(legacy_path)] == ["honest-legacy"]


def test_prepare_fixture_writes_the_text_it_was_given(tmp_path: Path) -> None:
    content = "第一行\nsecond\r\nthird\n"
    behavior_bench.prepare_fixture({"id": "t", "fixture": {"notes.md": content}}, tmp_path)
    raw = (tmp_path / "notes.md").read_bytes()
    assert raw == content.encode("utf-8"), (
        f"the workspace did not get the authored bytes back: {raw!r} != {content.encode('utf-8')!r}"
    )
    # Text-mode writing translated every LF, so an authored CRLF came back as two newlines.
    assert raw.count(b"\r\n") == 1, f"newline translation is back: {raw!r}"


def test_prepare_fixture_cannot_turn_a_value_into_repr(tmp_path: Path) -> None:
    """The coercion is gone, so a structured value can no longer reach disk silently."""
    with pytest.raises(TypeError):
        behavior_bench.prepare_fixture({"id": "t", "fixture": {"data.json": {"items": [1, 2]}}}, tmp_path)
    written = list(tmp_path.rglob("*"))
    assert not [p for p in written if p.is_file()], f"the bad value still produced {written}"


def test_the_shape_rule_has_one_owner_and_all_three_doors_ask_it() -> None:
    sources = {
        "minicc/bench_tasks.py": "validate_task",
        "minicc/benchmarks.py": "load_tasks",
        "minicc/behavior_bench.py": "validate_behavior_task",
    }
    owners = []
    for relative in ["minicc/bench_tasks.py", "minicc/benchmarks.py", "minicc/behavior_bench.py",
                     "minicc/cli_io.py", "minicc/main.py"]:
        tree = ast.parse((REPO / relative).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "require_writable_fixture":
                owners.append(relative)
    assert owners == ["minicc/bench_tasks.py"], f"the fixture rule has more than one home: {owners}"
    for relative, door in sources.items():
        tree = ast.parse((REPO / relative).read_text(encoding="utf-8"))
        function = next(
            (node for node in ast.walk(tree)
             if isinstance(node, ast.FunctionDef) and node.name == door),
            None,
        )
        assert function is not None, f"{relative} no longer defines {door}"
        asked = any(
            isinstance(call, ast.Call)
            and ast.unparse(call.func).endswith("require_writable_fixture")
            for call in ast.walk(function)
        )
        assert asked, f"{relative}:{door} no longer asks the single owner of the fixture rule"


def test_the_write_path_no_longer_coerces_content() -> None:
    """``str(content)`` was how repr got into the workspace; the door owns the rule now."""
    tree = ast.parse((REPO / "minicc/behavior_bench.py").read_text(encoding="utf-8"))
    function = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "prepare_fixture"
    )
    coercions = [
        node for node in ast.walk(function)
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "str"
        and [ast.unparse(arg) for arg in node.args] == ["content"]
    ]
    assert not coercions, "prepare_fixture coerces content again - that writes Python repr"
    writes = [
        ast.unparse(node) for node in ast.walk(function)
        if isinstance(node, ast.Call) and ast.unparse(node.func).endswith("write_text")
    ]
    assert writes and all("content" in call for call in writes), f"unexpected writes: {writes}"
    # ast.unparse prints string literals with single quotes.
    assert all("newline=''" in call for call in writes), (
        f"a write that translates newlines is back: {writes}"
    )


def test_no_shipped_task_needs_the_fixture_writable_rule() -> None:
    """The corpus is the floor: a scan that read nothing must not report a pass.

    Division of labor with test_every_shipped_behaviour_task_passes_the_behavior_door:
    - This test checks the FIXTURE WRITABLE RULE (require_writable_fixture) - does the host encoding path accept the fixture?
    - The companion test checks the BEHAVIOR DOOR (validate_behavior_task).
    """
    v2 = json.loads((REPO / "benchmarks" / "tasks.v2.json").read_text(encoding="utf-8"))
    all_tasks = {
        "legacy": benchmarks.load_tasks(REPO / "benchmarks" / "tasks.json"),
        "v2": v2["tasks"] if isinstance(v2, dict) and "tasks" in v2 else v2,
        "behavior": behavior_bench.behavior_tasks(),
    }
    offenders = {}
    fixture_entries = 0
    for suite, tasks in all_tasks.items():
        assert len(tasks) >= 10, f"{suite}: only {len(tasks)} tasks loaded - the census read nothing"
        for task in tasks:
            fixture = task.get("fixture")
            if fixture:
                fixture_entries += len(fixture)
                for key in task["fixture"]:
                    try:
                        bench_tasks.require_writable_fixture(task)
                    except ValueError as exc:
                        offenders[task["id"]] = str(exc)
    assert fixture_entries >= 30, f"only {fixture_entries} fixture files were inspected"
    assert offenders == {}, f"shipped tasks would break the agent's workspace: {offenders}"
