"""M8-T91: a subscript read in an embedded grader is a promise made upstream.

The two contract graders ship as source strings inside ``minicc/bench_tasks.py`` and read
their spec from stdin. ``spec["command"]`` / ``item["path"]`` are *subscript* reads: if the
key is missing or the shape is wrong the grader dies with a TypeError/KeyError, exits
nonzero, and the row books ``passed=False`` - the grader's own unreadable input charged to
the agent, which is the M8-T83 class. Measured on ``e8c3db5``:

    grade_file_contract({'files': ['notes.md']}) ->
        {'passed': False, 'grader_type': 'file_contract', 'case_count': 1, 'exit_code': 1}

so a file item that is a string instead of ``{"path": ...}`` produces a verdict.

This census reads the grader sources (literal Python inside a string constant), lists the
keys they subscript, and requires each of them to have a named keeper upstream: the
load-time validator (``validate_task``) or the producer that runs before the subprocess.
Anything it cannot resolve is a blind spot and is red rather than skipped.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import minicc.bench_tasks as bench_tasks

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE = (REPO_ROOT / "minicc" / "bench_tasks.py").read_text(encoding="utf-8")

KEEPERS = {
    # key -> the upstream door that guarantees it, by name, so a reader can go look.
    # Measured on e8c3db5, these are the only two subscript reads in the shipped graders:
    # ``spec["command"]`` (kept since M8-T90 by the producer refusing a blank command) and
    # ``item["path"]`` (the hole this batch closes).
    "command": "grade_command_contract",
    "path": "grade_file_contract",
}


def _module() -> ast.Module:
    return ast.parse(SOURCE)


def _grader_sources() -> dict[str, ast.Module]:
    """Every module-level string constant named ``_*_GRADER``, parsed."""
    out: dict[str, ast.Module] = {}
    for node in _module().body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Constant):
            continue
        if not isinstance(node.value.value, str):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id.endswith("_GRADER"):
                out[target.id] = ast.parse(node.value.value)
    assert out, "no embedded grader sources found, which means the census read nothing"
    return out


def _subscript_reads(tree: ast.Module) -> tuple[set[str], list[str]]:
    """Keys read as ``x["k"]`` off a spec/item, plus shapes this census cannot resolve."""
    keys: set[str] = set()
    blind: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Subscript):
            continue
        base = node.value
        if not (isinstance(base, ast.Name) and base.id in {"spec", "item", "grader"}):
            continue
        if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
            keys.add(node.slice.value)
        else:
            blind.append(f"subscript on {base.id} with a {type(node.slice).__name__} slice")
    return keys, blind


def _guarded_keys(tree: ast.Module) -> set[str]:
    """Keys the grader itself tests for with ``if "k" in item`` before reading."""
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], ast.In):
            left = node.left
            if isinstance(left, ast.Constant) and isinstance(left.value, str):
                out.add(left.value)
    return out


def _keys_named_in(func_name: str) -> set[str]:
    """String constants appearing in a keeper function's source: its declared vocabulary."""
    for node in ast.walk(_module()):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            found: set[str] = set()
            for inner in ast.walk(node):
                if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                    found.add(inner.value)
            return found
    raise AssertionError(f"{func_name} is gone from minicc/bench_tasks.py")


def _promises() -> tuple[dict[str, set[str]], list[str]]:
    """key -> the grader sources that subscript it, plus any blind spot."""
    promises: dict[str, set[str]] = {}
    blind: list[str] = []
    for name, tree in _grader_sources().items():
        guarded = _guarded_keys(tree)
        keys, gaps = _subscript_reads(tree)
        blind += [f"{name}: {gap}" for gap in gaps]
        for key in keys - guarded:
            promises.setdefault(key, set()).add(name)
    return promises, blind


def _kept_keys() -> set[str]:
    """A key is kept only if its declared door still names it - listing it is not guarding it."""
    return {key for key, door in KEEPERS.items() if key in _keys_named_in(door)}


def test_the_grader_source_census_reports_no_blind_spots() -> None:
    _found, blind = _promises()
    assert blind == [], f"the grader-source census went blind on: {blind}"


def test_every_key_an_embedded_grader_subscripts_has_a_named_keeper() -> None:
    promises, blind = _promises()
    assert blind == [], f"cannot answer while blind on: {blind}"
    unkept = sorted(set(promises) - _kept_keys())
    assert unkept == [], (
        "these keys are read as x[\"k\"] inside an embedded grader with nothing upstream "
        f"guaranteeing them, so a bad spec becomes passed=False: {unkept}"
    )


def test_the_keeper_named_in_the_ledger_actually_names_the_key() -> None:
    """A keeper that stops mentioning the key is a dead ledger row, not a guard."""
    unkept = sorted(key for key, door in KEEPERS.items() if key not in _keys_named_in(door))
    assert unkept == [], (
        f"the ledger excuses {unkept} but the door it names no longer mentions them"
    )


def test_the_ledger_does_not_excuse_a_key_the_graders_never_subscript() -> None:
    promises, _blind = _promises()
    stale = sorted(set(KEEPERS) - set(promises))
    assert stale == [], f"these exemptions name no subscript read any more: {stale}"


def test_a_file_item_without_a_string_path_is_no_result(tmp_path: Path) -> None:
    """The measured shape: a string item used to produce a verdict."""
    (tmp_path / "notes.md").write_text("hello\n", encoding="utf-8")
    for bad in (["notes.md"], [{"nope": "notes.md"}], [{"path": "   "}], [None]):
        graded = bench_tasks.grade_file_contract(
            {"grader": {"type": "file_contract", "files": bad + [{"path": "notes.md"}]}},
            tmp_path, grader_dir=tmp_path / "graders",
        )
        assert graded["passed"] is None, f"{bad!r} produced a verdict: {graded}"
        assert graded["grading_refused"] is True, graded
        assert "path" in graded["refusal"], graded


def test_a_well_formed_file_contract_still_reaches_a_verdict(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_text("hello\n", encoding="utf-8")
    graded = bench_tasks.grade_file_contract(
        {"grader": {"type": "file_contract",
                    "files": [{"path": "notes.md", "contains": "hello"}]}},
        tmp_path, grader_dir=tmp_path / "graders",
    )
    assert graded["passed"] is True, graded
    assert not graded.get("grading_refused"), graded


def test_a_refusal_for_a_malformed_item_reaches_the_report_as_a_refusal(tmp_path: Path) -> None:
    graded = bench_tasks.grade_file_contract(
        {"grader": {"type": "file_contract", "files": ["notes.md"]}},
        tmp_path, grader_dir=tmp_path / "graders",
    )
    task = {"id": "bad-item", "category": "write", "prompt": "p",
            "grader": {"type": "file_contract", "files": ["notes.md"]}}
    row = {"task_id": "bad-item", "category": "write", "status": "completed",
           "claimed_complete": True, **graded}
    from minicc.benchmarks import build_report

    metrics = build_report([task], [row])["metrics"]
    assert metrics["grading_refusal_count"] == 1, metrics
    assert metrics["gradable_task_count"] == 0, metrics


@pytest.mark.parametrize("planted,expected", [
    ('spec["brand_new_key"]', {"brand_new_key"}),
    ('item["another_key"]', {"another_key"}),
])
def test_a_new_subscript_read_is_named_without_editing_this_file_first(
    planted: str, expected: set[str]
) -> None:
    tree = ast.parse(f"import sys\nspec = sys.stdin\nitem = spec\n{planted}\n")
    keys, blind = _subscript_reads(tree)
    assert blind == [], blind
    assert keys == expected, keys


def test_a_dynamic_subscript_is_reported_as_a_hole_not_skipped() -> None:
    tree = ast.parse('import sys\nspec = sys.stdin\nkey = "x"\nspec[key]\n')
    keys, blind = _subscript_reads(tree)
    assert keys == set(), keys
    assert blind, "an unresolvable subscript must be reported, not silently ignored"
