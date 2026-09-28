"""M8-T92: a spec key nobody reads is a check that quietly stopped existing.

Measured on ``150559f`` against the shipped producers:

    grade_file_contract({'files': [{'path': 'a.txt', 'typo_contains': 'goodbye'}]})
        -> {'passed': True, ...}          # the intended check was never run
    grade_command_contract({'command': ..., 'expct_exit': 9})
        -> {'passed': True, ...}         # the expectation was silently defaulted

The embedded graders only ever look at their own vocabulary, so a mistyped key is not an
error - it is a contract that verifies less than the task author wrote, while still
reporting success. The producers now refuse such a spec (NO-RESULT, naming the keys), and
the vocabulary they refuse against is parsed out of the grader source rather than copied.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

import minicc.bench_tasks as bench_tasks

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE = (REPO_ROOT / "minicc" / "bench_tasks.py").read_text(encoding="utf-8")
SCRIPTS = {"file_contract": "_FILE_CONTRACT_GRADER", "command_contract": "_COMMAND_CONTRACT_GRADER"}
HOST_FUNCTIONS = ("grade_v2", "grade_file_contract", "grade_command_contract")


def _module() -> ast.Module:
    return ast.parse(SOURCE)


def _script(name: str) -> ast.Module:
    for node in _module().body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str) \
                and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.parse(node.value.value)
    raise AssertionError(f"{name} is no longer a string constant in minicc/bench_tasks.py")


def _host_reads(function: str) -> set[str]:
    for node in ast.walk(_module()):
        if isinstance(node, ast.FunctionDef) and node.name == function:
            return bench_tasks._keys_read(node, "spec") | bench_tasks._keys_read(node, "grader")
    raise AssertionError(f"{function} is gone from minicc/bench_tasks.py")


#: Which grader each host function serves; grade_v2 only dispatches on "type".
HOST_SCOPE = {
    "grade_v2": None,
    "grade_file_contract": "file_contract",
    "grade_command_contract": "command_contract",
}


def test_every_key_the_host_reads_is_inside_the_vocabulary_it_enforces() -> None:
    """A host-read key missing from the declaration would be rejected as unread."""
    for function, kind in HOST_SCOPE.items():
        vocabulary = set(bench_tasks.HOST_READ_KEYS)
        for script_name in SCRIPTS.values() if kind is None else [SCRIPTS[kind]]:
            vocabulary |= bench_tasks._keys_read(_script(script_name), "spec")
        outside = sorted(_host_reads(function) - vocabulary)
        assert outside == [], (
            f"{function} reads {outside} off a spec its own vocabulary calls unread - "
            f"either the grader really ignores them or HOST_READ_KEYS is stale"
        )


def test_the_host_declaration_names_no_key_anybody_reads() -> None:
    """The converse: a declared key nobody reads any more is a silent free pass."""
    read = set(bench_tasks.HOST_READ_KEYS)
    declared_elsewhere = set()
    for script_name in SCRIPTS.values():
        declared_elsewhere |= bench_tasks._keys_read(_script(script_name), "spec")
    for function in HOST_SCOPE:
        declared_elsewhere |= _host_reads(function)
    dead = sorted(read - declared_elsewhere)
    assert dead == [], f"HOST_READ_KEYS still excuses keys nobody reads: {dead}"


def test_the_vocabulary_is_parsed_from_the_graders_not_copied() -> None:
    """The item vocabulary has to come from the script that consumes the items."""
    vocab = bench_tasks.grader_vocabulary("file_contract", _source_of("_FILE_CONTRACT_GRADER"))
    assert vocab["item"] == bench_tasks._keys_read(_script("_FILE_CONTRACT_GRADER"), "item"), vocab
    assert vocab["spec"] == bench_tasks._keys_read(_script("_FILE_CONTRACT_GRADER"), "spec") \
        | bench_tasks.HOST_READ_KEYS, vocab


def _source_of(constant: str) -> str:
    for node in _module().body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str) \
                and any(isinstance(t, ast.Name) and t.id == constant for t in node.targets):
            return node.value.value
    raise AssertionError(f"{constant} is gone")


@pytest.mark.parametrize("grader_type,unknown,dead_key", [
    ("file_contract", {"type": "file_contract",
                        "files": [{"path": "a.txt", "typo_contains": "goodbye"}]}, "typo_contains"),
    ("file_contract", {"type": "file_contract", "files": [{"path": "a.txt"}], "expiry": 3},
     "expiry"),
    ("command_contract", {"type": "command_contract", "command": "python -c ''",
                          "expct_exit": 9}, "expct_exit"),
    ("command_contract", {"type": "command_contract", "command": "python -c ''",
                          "stdout": "x"}, "stdout"),
])
def test_a_spec_key_nobody_reads_is_refused_naming_it(
    tmp_path: Path, grader_type: str, unknown: dict, dead_key: str
) -> None:
    (tmp_path / "a.txt").write_text("hello\n", encoding="utf-8")
    graded = bench_tasks.grade_v2({"grader": unknown}, tmp_path, grader_dir=tmp_path / "g")
    assert graded["passed"] is None, (
        f"a {grader_type} spec carrying an unread key was graded anyway: {graded}"
    )
    assert graded["grading_refused"] is True, graded
    assert dead_key in graded["refusal"], (
        f"the refusal did not name {dead_key!r}, so nobody can fix the task: {graded}"
    )


def test_a_real_check_still_runs_after_the_vocabulary_gate(tmp_path: Path) -> None:
    """The refusal must not eat the keys the grader does read - including the optional ones."""
    (tmp_path / "a.txt").write_text("hello\n", encoding="utf-8")
    graded = bench_tasks.grade_file_contract(
        {"grader": {"type": "file_contract",
                    "files": [{"path": "a.txt", "contains": "hello", "exists": True}],
                    "timeout": 30}},
        tmp_path, grader_dir=tmp_path / "g",
    )
    assert graded["passed"] is True, graded
    assert not graded.get("grading_refused"), graded


def test_the_refusal_reaches_the_report_as_a_refusal(tmp_path: Path) -> None:
    from minicc.benchmarks import build_report

    spec = {"type": "file_contract", "files": [{"path": "a.txt", "typo_contains": "x"}]}
    graded = bench_tasks.grade_file_contract({"grader": spec}, tmp_path,
                                              grader_dir=tmp_path / "g")
    task = {"id": "typo", "category": "write", "prompt": "p", "grader": spec}
    row = {"task_id": "typo", "category": "write", "status": "completed",
           "claimed_complete": True, **graded}
    metrics = build_report([task], [row])["metrics"]
    assert metrics["grading_refusal_count"] == 1, metrics
    assert metrics["gradable_task_count"] == 0, metrics


def test_every_shipped_task_spec_is_verifiable() -> None:
    """The corpus is the population this rule will actually hit - measure it, don't assume."""
    offenders: list[str] = []
    checked = 0
    for name in ("benchmarks/tasks.v2.json", "benchmarks/behavior-tasks.json"):
        raw = json.loads((REPO_ROOT / name).read_text(encoding="utf-8"))
        for task in raw if isinstance(raw, list) else raw.get("tasks", []):
            spec = task.get("grader") or {}
            kind = spec.get("type")
            if kind not in SCRIPTS:
                continue
            checked += 1
            script = _source_of(SCRIPTS[kind])
            dead = bench_tasks.unverifiable_spec_keys(kind, script, spec)
            if dead:
                offenders.append(f"{task.get('id')}: {dead}")
    assert checked >= 20, f"only {checked} contract tasks were read - the census saw nothing"
    assert offenders == [], f"shipped tasks carry keys no grader reads: {offenders}"


@pytest.mark.parametrize("planted,expected", [
    ('spec["fresh_key"]\nitem.get("other")\nif "third" in item: pass\n',
     {"fresh_key", "other", "third"}),
    ('spec.get("only")\n', {"only"}),
])
def test_the_reader_walk_counts_all_three_shapes(planted: str, expected: set[str]) -> None:
    tree = ast.parse(f'import sys\nspec = sys.stdin\nitem = spec\n{planted}')
    assert bench_tasks._keys_read(tree, "spec") | bench_tasks._keys_read(tree, "item") \
        == expected


def test_a_key_read_only_by_a_shape_we_cannot_see_is_not_silently_accepted() -> None:
    """``spec[var]`` cannot be enumerated: the vocabulary must not grow to swallow it."""
    tree = ast.parse('import sys\nspec = sys.stdin\nkey = "x"\nspec[key]\n')
    assert bench_tasks._keys_read(tree, "spec") == set(), (
        "a dynamic subscript was counted as a named key"
    )
    unresolved = [n for n in ast.walk(tree) if isinstance(n, ast.Subscript)
                  and isinstance(n.value, ast.Name) and n.value.id == "spec"
                  and not isinstance(n.slice, ast.Constant)]
    assert unresolved, "the planted dynamic subscript disappeared from the walk"
