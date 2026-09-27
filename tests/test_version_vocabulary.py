"""M8-T79: every version constant must either be branched on or be announced.

A format version that is written but never read is the defect class this repo
has now hit three times (session checkpoint, agent checkpoint, suite identity in
bench results): the value exists, the file carries it, and nothing ever asks
whether the thing in front of it was produced under those semantics.

The gate enumerates module-level ``*VERSION`` constants in ``minicc/`` from the
AST - never from a hand-written list of line numbers - and requires each one to
match a declared role:

* ``branched`` - the constant is compared somewhere in its own module, so a
  reader can actually refuse a foreign value;
* ``announced`` - the constant is never compared but is written into a payload
  (dict value, subscript store, or a table it belongs to), i.e. it is an
  identity we publish on purpose.

A constant that is neither - or one that is merely exported - is red, because
that is precisely the shape that lets a hand-copied literal in a data file
become the only real source of truth.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
import minicc.bench_tasks as bench_tasks

# Role declared per (module, constant). Keys are module-relative paths plus the
# constant's own identity - a line number would rot the moment the file moves.
DECLARED_ROLES: dict[tuple[str, str], str] = {
    ("minicc/agent/context.py", "CHECKPOINT_VERSION"): "branched",
    ("minicc/agent/rpc.py", "JSONRPC_VERSION"): "branched",
    ("minicc/behavior_bench.py", "SUITE_VERSION"): "announced",
    ("minicc/bench_tasks.py", "SUITE_VERSION"): "announced",
    ("minicc/bench_tasks.py", "LEGACY_SUITE_VERSION"): "announced",
    ("minicc/llm/anthropic_provider.py", "ANTHROPIC_VERSION"): "announced",
    ("minicc/session.py", "SESSION_FORMAT_VERSION"): "branched",
    ("minicc/task_contract.py", "TASK_SCHEMA_VERSION"): "branched",
    ("minicc/task_worker.py", "WORKER_VERSION"): "announced",
    ("minicc/tools/registry.py", "TOOL_API_VERSION"): "branched",
    ("minicc/tools/registry.py", "_MIN_TOOL_API_VERSION"): "branched",
}

# Modules that write a version into a durable format on disk. Those get the
# strict rule: publishing the number is not enough, something must read it.
DURABLE_FORMAT_MODULES = {"minicc/agent/context.py", "minicc/session.py"}


def _module_constants(tree: ast.Module) -> dict[str, object]:
    found: dict[str, object] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id.upper().endswith("VERSION"):
                found[target.id] = node.value
    return found


def _compared(tree: ast.Module, name: str) -> int:
    hits = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and any(
            isinstance(sub, ast.Name) and sub.id == name and isinstance(sub.ctx, ast.Load)
            for sub in ast.walk(node)
        ):
            hits += 1
    return hits


def _announced(tree: ast.Module, name: str) -> int:
    hits = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for value in node.values:
                for sub in ast.walk(value):
                    if isinstance(sub, ast.Name) and sub.id == name and isinstance(sub.ctx, ast.Load):
                        hits += 1
        elif isinstance(node, (ast.List, ast.Set, ast.Tuple)):
            for element in node.elts:
                for sub in ast.walk(element):
                    if isinstance(sub, ast.Name) and sub.id == name and isinstance(sub.ctx, ast.Load):
                        hits += 1
        elif isinstance(node, ast.Assign):
            if any(
                    isinstance(sub, ast.Name) and sub.id == name and isinstance(sub.ctx, ast.Load)
                    for sub in ast.walk(node.value)
                ):
                    hits += 1
    return hits


def _roles_for(source: str, filename: str) -> dict[str, str]:
    tree = ast.parse(source, filename=filename)
    roles: dict[str, str] = {}
    for name in _module_constants(tree):
        if _compared(tree, name):
            roles[name] = "branched"
        elif _announced(tree, name):
            roles[name] = "announced"
        else:
            roles[name] = "dead"
    return roles


def _census() -> dict[tuple[str, str], str]:
    census: dict[tuple[str, str], str] = {}
    for path in sorted((REPO_ROOT / "minicc").rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        roles = _roles_for(path.read_text(encoding="utf-8"), str(path))
        for name, role in roles.items():
            census[(rel, name)] = role
    return census


def test_census_and_declared_table_are_the_same_set() -> None:
    census = _census()
    extra = sorted(set(census) - set(DECLARED_ROLES))
    missing = sorted(set(DECLARED_ROLES) - set(census))
    assert not extra and not missing, f"unlisted version constants={extra} stale table rows={missing}"


def test_each_version_constant_matches_its_declared_role() -> None:
    census = _census()
    drift = []
    for key, declared in sorted(DECLARED_ROLES.items()):
        actual = census.get(key, "<absent>")
        if actual != declared:
            drift.append(f"{key[0]}::{key[1]} declared={declared} actual={actual}")
    assert drift == [], "role drift:\n  " + "\n  ".join(drift)


def test_durable_format_versions_are_read_not_only_written() -> None:
    census = _census()
    silent = sorted(
        f"{module}::{name}"
        for (module, name), role in census.items()
        if module in DURABLE_FORMAT_MODULES and role != "branched"
    )
    assert silent == [], f"a durable format version with no reader: {silent}"


def test_gate_refuses_a_version_constant_with_no_reader_and_no_announcement() -> None:
    """Reverse control: the classifier must be able to say 'dead'."""
    planted = "SUITE_VERSION = 'v9-9'\n__all__ = ['SUITE_VERSION']\n"
    assert _roles_for(planted, "planted.py") == {"SUITE_VERSION": "dead"}
    announced = "SUITE_VERSION = 'v9-9'\n\n\ndef build():\n    return {'suite_version': SUITE_VERSION}\n"
    assert _roles_for(announced, "planted.py") == {"SUITE_VERSION": "announced"}
    branched = "SUITE_VERSION = 'v9-9'\n\n\ndef check(value):\n    return value == SUITE_VERSION\n"
    assert _roles_for(branched, "planted.py") == {"SUITE_VERSION": "branched"}


# --- the two defects the census points at, fixed behaviourally --------------


def _checkpoint_message(payload: dict[str, object]) -> dict[str, str]:
    from minicc.agent.context import COMPACTION_MARKER

    return {"role": "user", "content": COMPACTION_MARKER + "\n" + json.dumps(payload)}


def _merge(previous: list[dict[str, str]], middle: list[dict[str, str]]) -> dict[str, object]:
    from minicc.agent import context

    return context._merge_checkpoint(previous, {"objectives": ["现在的要求"], "files": []}, middle)


def test_agent_checkpoint_version_now_has_a_reader() -> None:
    from minicc.agent import context

    assert context._checkpoint_is_mergeable({"version": context.CHECKPOINT_VERSION}) is True
    assert context._checkpoint_is_mergeable({}) is True
    assert context._checkpoint_is_mergeable({"version": context.CHECKPOINT_VERSION + 1}) is False
    assert context._checkpoint_is_mergeable({"version": "not-a-number"}) is False


def test_foreign_checkpoint_facts_are_not_merged_but_still_counted() -> None:
    from minicc.agent import context

    foreign = _checkpoint_message({
        "version": context.CHECKPOINT_VERSION + 5,
        "objectives": ["另一个格式版本的目标"],
        "archive": {"messages": 7, "characters": 40},
    })
    current = _checkpoint_message({
        "version": context.CHECKPOINT_VERSION,
        "objectives": ["同版本的目标"],
        "archive": {"messages": 3, "characters": 20},
    })
    middle = [{"role": "user", "content": "本轮消息"}]
    merged = _merge([foreign, current], middle)

    objectives = merged["objectives"]
    assert isinstance(objectives, list)
    assert "另一个格式版本的目标" not in objectives, "a foreign version's facts were merged"
    assert "同版本的目标" in objectives
    # the archive counters are version-agnostic totals: dropping them would be a
    # second, quieter lie, so both checkpoints must still be counted.
    archive = merged["archive"]
    assert isinstance(archive, dict)
    assert archive["messages"] == 7 + 3 + len(middle)
    assert any("version" in line for line in merged["loss_risk"]), (
        "a skipped checkpoint merged silently - the loss must be visible where loss is documented"
    )


def test_suite_version_is_derived_not_hand_copied(tmp_path: Path) -> None:
    tasks_file = tmp_path / "tasks.json"
    tasks_file.write_text(
        json.dumps([{"id": "t1", "prompt": "p", "fixture": {"a.txt": "x"},
                     "grader": {"type": "file_contract", "files": []}}]),
        encoding="utf-8",
    )
    stamped = bench_tasks.v2_tasks(tasks_file)
    assert stamped[0].get("suite_version") == bench_tasks.SUITE_VERSION

    # Derivation witness: move the constant, the stamp must move with it.
    original = bench_tasks.SUITE_VERSION
    bench_tasks.SUITE_VERSION = "v9-derived"
    try:
        assert bench_tasks.v2_tasks(tasks_file)[0].get("suite_version") == "v9-derived"
    finally:
        bench_tasks.SUITE_VERSION = original


def test_unknown_suite_version_is_refused_and_the_vocabulary_is_public() -> None:
    task = {"id": "t1", "category": "edit", "prompt": "p", "fixture": {"a.txt": "x"},
            "grader": {"type": "file_contract", "files": []}, "suite_version": "v3-99"}
    with pytest.raises(ValueError, match="suite_version"):
        bench_tasks.validate_task(task)
    assert bench_tasks.SUITE_VERSIONS >= {bench_tasks.SUITE_VERSION, bench_tasks.LEGACY_SUITE_VERSION}


def test_shipped_suite_still_validates_against_the_vocabulary() -> None:
    tasks = bench_tasks.v2_tasks()
    for task in tasks:
        bench_tasks.validate_task(task)
    versions = {task.get("suite_version") for task in tasks}
    assert versions and versions <= set(bench_tasks.SUITE_VERSIONS), versions
