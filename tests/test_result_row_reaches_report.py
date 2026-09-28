"""M8-T89: the report row must not be a hand-copied subset of the runner's row.

``build_report`` rebuilds every per-task row key by key (that is how M8-T81's
dropped ``refusal`` and M8-T85's dropped ``error`` were found). The rebuild is a
second master of the knowledge "which fields exist", so a field the runner writes
and the rebuild forgets is invisible in the product output while sitting on disk -
measured on ``d784d2c``: the runner can write 23 keys onto a row, the report carried
19 of them, and six were forgotten (``turns``, ``review_rounds``, ``case_count``,
``exit_code``, ``retained_workspace``, ``cleanup_error``).

The census below answers both directions mechanically:

* every key the runner can put on a row has to be carried by the report row;
* every key the report reads off a recorded row has to be written by someone, or be
  a named exception that still describes a real hole.

The exception list exists for ``repeated_tool_calls`` only: it is read by the report
and feeds ``tool_repeat_rate``, while no production code writes it, so the metric is
permanently null. Deleting it or writing it is the user's call (tracked as task #83),
and until then the exception must keep matching the measured hole - a stale exemption
is itself a red.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from minicc.benchmarks import build_report

REPO_ROOT = Path(__file__).resolve().parent.parent
EXCEPTIONS_FOR_UNWRITTEN_READS = {"repeated_tool_calls"}


def _trees() -> dict[str, ast.Module]:
    out: dict[str, ast.Module] = {}
    for path in sorted((REPO_ROOT / "minicc").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        out[path.relative_to(REPO_ROOT).as_posix()] = ast.parse(path.read_text(encoding="utf-8"))
    return out


def _functions(trees: dict[str, ast.Module]) -> dict[str, tuple[str, ast.FunctionDef]]:
    """Name -> (module, definition). Collisions are kept visible, not folded."""
    out: dict[str, list[tuple[str, ast.FunctionDef]]] = {}
    for module, tree in trees.items():
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                out.setdefault(node.name, []).append((module, node))
    return {name: hits[0] for name, hits in out.items() if len(hits) == 1}


def _literal_keys(dct: ast.Dict) -> set[str]:
    return {k.value for k in dct.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}


def _targets(node: ast.AST) -> list[ast.expr]:
    if isinstance(node, ast.Assign):
        return list(node.targets)
    if isinstance(node, ast.AnnAssign) and node.target is not None:
        return [node.target]
    return []


def _returned_keys(fn: ast.FunctionDef, index: dict, seen: set[str], blind: list[str]) -> set[str]:
    """Keys a producer function can hand to ``entry.update(...)``.

    A producer may build its dict in a local (``_no_result`` does) and add optional
    keys to it after the literal, so locals are tracked as well; anything that cannot
    be resolved is recorded as a blind spot instead of being skipped.
    """
    keys: set[str] = set()
    locals_: dict[str, set[str]] = {}
    for node in ast.walk(fn):
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(node.value, ast.Dict):
            for target in _targets(node):
                if isinstance(target, ast.Name):
                    locals_.setdefault(target.id, set()).update(_literal_keys(node.value))
        for target in _targets(node):
            if isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name) \
                    and target.value.id in locals_ and isinstance(target.slice, ast.Constant) \
                    and isinstance(target.slice.value, str):
                locals_[target.value.id].add(target.slice.value)
    for node in ast.walk(fn):
        if not isinstance(node, ast.Return) or node.value is None:
            continue
        value = node.value
        if isinstance(value, ast.Dict):
            keys |= _literal_keys(value)
        elif isinstance(value, ast.Name) and value.id in locals_:
            keys |= locals_[value.id]
        elif isinstance(value, ast.Call):
            callee = value.func
            name = callee.id if isinstance(callee, ast.Name) else (
                callee.attr if isinstance(callee, ast.Attribute) else None)
            if name is None:
                blind.append(f"{fn.name}: cannot read the shape of a returned call")
                continue
            if name in seen:
                continue
            if name not in index:
                blind.append(f"{fn.name}: returns {name}, which this census cannot resolve")
                continue
            keys |= _returned_keys(index[name][1], index, seen | {name}, blind)
        else:
            blind.append(f"{fn.name}: returns a {type(value).__name__}, not a literal dict")
    return keys


def _keys_written_on_rows(trees: dict[str, ast.Module]) -> tuple[set[str], list[str]]:
    """Every key ``run_benchmark`` can put on a result row, plus the census' blind spots."""
    index = _functions(trees)
    runner = index["run_benchmark"][1]
    keys: set[str] = set()
    blind: list[str] = []
    for node in ast.walk(runner):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            for target in _targets(node):
                if isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name) \
                        and target.value.id == "entry" and isinstance(target.slice, ast.Constant) \
                        and isinstance(target.slice.value, str):
                    keys.add(target.slice.value)
                elif isinstance(target, ast.Name) and target.id == "entry" \
                        and isinstance(node.value, ast.Dict):
                    keys |= _literal_keys(node.value)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "update" and isinstance(node.func.value, ast.Name) \
                and node.func.value.id == "entry":
            for kw in node.keywords:
                if kw.arg:
                    keys.add(kw.arg)
            for arg in node.args:
                if isinstance(arg, ast.Dict):
                    keys |= _literal_keys(arg)
                    continue
                callee = arg.func if isinstance(arg, ast.Call) else None
                name = None
                if isinstance(callee, ast.Name):
                    name = callee.id
                elif isinstance(callee, ast.Attribute):
                    name = callee.attr
                if name is None:
                    blind.append("entry.update(<something this census cannot read>)")
                elif name not in index:
                    blind.append(f"entry.update({name}(...)): carrier not in the function index")
                else:
                    keys |= _returned_keys(index[name][1], index, {name}, blind)
    return keys, blind


def _keys_carried_by_report(trees: dict[str, ast.Module]) -> set[str]:
    _, report = _functions(trees)["build_report"]
    for node in ast.walk(report):
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "row" for t in node.targets) \
                and isinstance(node.value, ast.Dict):
            return _literal_keys(node.value)
    raise AssertionError("build_report no longer builds its row as a dict literal")


def _recorded_reads(trees: dict[str, ast.Module]) -> set[str]:
    """Keys the report reads off a recorded result row (``recorded``)."""
    _, report = _functions(trees)["build_report"]
    out: set[str] = set()
    for node in ast.walk(report):
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) \
                and node.value.id == "recorded" and isinstance(node.slice, ast.Constant) \
                and isinstance(node.slice.value, str):
            out.add(node.slice.value)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "get" and isinstance(node.func.value, ast.Name) \
                and node.func.value.id == "recorded":
            # Only the first positional argument is a key; "not_run" in
            # recorded.get("status", "not_run") is a default, and counting it as a
            # read invented a field nobody ever asked for.
            for arg in node.args[:1]:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    out.add(arg.value)
    return out


def _uncarried(written: set[str], carried: set[str]) -> set[str]:
    return written - carried


def _reads_nobody_writes(reads: set[str], written: set[str], exceptions: set[str]) -> set[str]:
    return reads - written - exceptions


# --- the live census over the shipped source ---------------------------------


def test_the_row_census_sees_every_way_a_key_can_reach_a_row() -> None:
    """A carrier the census cannot resolve is a hole, not a pass."""
    written, blind = _keys_written_on_rows(_trees())
    assert blind == [], f"the row census went blind on: {blind}"
    assert written, "the census found no keys at all, which means it read nothing"


def test_every_key_the_runner_writes_on_a_row_is_carried_into_the_report() -> None:
    trees = _trees()
    written, blind = _keys_written_on_rows(trees)
    assert blind == [], f"cannot answer while blind on: {blind}"
    missing = _uncarried(written, _keys_carried_by_report(trees))
    assert missing == set(), (
        f"these fields exist on the results row but the report forgets them: {sorted(missing)}"
    )


def test_the_report_does_not_read_a_recorded_key_nobody_writes() -> None:
    trees = _trees()
    written, blind = _keys_written_on_rows(trees)
    assert blind == [], f"cannot answer while blind on: {blind}"
    dead = _reads_nobody_writes(_recorded_reads(trees), written, EXCEPTIONS_FOR_UNWRITTEN_READS)
    assert dead == set(), (
        f"the report reads {sorted(dead)} off a row that nothing writes (a permanently null field):"
        " either write it, stop reading it, or name it in the exception set with a reason"
    )


def test_the_exception_for_unwritten_reads_still_describes_a_real_hole() -> None:
    """A stale exemption is a red: the named key must still be read and still unwritten."""
    trees = _trees()
    written, _ = _keys_written_on_rows(trees)
    reads = _recorded_reads(trees)
    for key in EXCEPTIONS_FOR_UNWRITTEN_READS:
        assert key in reads, f"the exception names {key!r}, but the report no longer reads it"
        assert key not in written, (
            f"the exception names {key!r}, but something writes it now - drop the exemption"
        )


# --- behaviour: the six forgotten fields must reach the product output --------

# Each witness value is of the field's own type: two of these six are text, and a
# single number for all six would only prove the copy stringifies.
_SAMPLES = {
    "turns": 3,
    "review_rounds": 3,
    "case_count": 3,
    "exit_code": -9,
    "retained_workspace": "C:/Temp/minicc-behavior-abc123",
    "cleanup_error": "PermissionError",
}


def _row_for(recorded: dict[str, object]) -> dict[str, object]:
    task = {"id": "t1", "category": "verify", "prompt": "回答任意内容。"}
    report = build_report([task], [{"task_id": "t1", **recorded}])
    return report["results"][0]


@pytest.mark.parametrize("key", sorted(_SAMPLES))
def test_a_recorded_field_reaches_the_report_row(key: str) -> None:
    expected = _SAMPLES[key]
    row = _row_for({"status": "completed", key: expected})
    assert row[key] == expected, (
        f"{key} is written by the runner but the report row cannot show it: {row}"
    )


@pytest.mark.parametrize("key", sorted(_SAMPLES))
def test_a_field_that_was_never_recorded_is_not_invented(key: str) -> None:
    """Absence stays absence: no row may turn "nothing recorded" into 0 or "".

    ``exit_code`` keeps a negative value on purpose - a signal-killed grader has a
    real, negative code, and a nonnegative-only guard would erase the exact case a
    human needs to see.
    """
    row = _row_for({"status": "completed"})
    assert row[key] is None, f"{key} invented a value for a task that recorded none: {row}"


def test_a_non_measurement_does_not_masquerade_as_a_count() -> None:
    row = _row_for({"status": "completed", "turns": "12", "case_count": True})
    assert row["turns"] is None, row
    assert row["case_count"] is None, row


# --- plant controls: the census must name a hole it has never seen ------------

_RUNNER_SEED = (
    "def grade_v2(task):\n"
    "    out = {'passed': True, 'grader_type': 'contract'}\n"
    "    return out\n"
    "def run_benchmark(tasks):\n"
    "    entry = {'task_id': 'x', 'status': 'failed'}\n"
    "    entry['turns'] = 1\n"
    "    entry.update(grade_v2(task))\n"
    "    return entry\n"
)
_REPORT_SEED = (
    "def build_report(tasks, results):\n"
    "    for task in tasks:\n"
    "        recorded = {}\n"
    "        row = {'task_id': 'x', 'status': recorded.get('status'),"
    " 'turns': recorded.get('turns'), 'passed': recorded.get('passed'),"
    " 'grader_type': recorded.get('grader_type')}\n"
    "        return row\n"
)


def _trees_from(sources: dict[str, str]) -> dict[str, ast.Module]:
    return {name: ast.parse(text) for name, text in sources.items()}


def test_a_written_key_the_report_forgot_is_named() -> None:
    planted = _RUNNER_SEED.replace("entry['turns'] = 1", "entry['turns'] = 1\n    entry['zzz_only_on_disk'] = 2")
    trees = _trees_from({"m": planted, "r": _REPORT_SEED})
    written, blind = _keys_written_on_rows(trees)
    assert blind == [], blind
    missing = _uncarried(written, _keys_carried_by_report(trees))
    assert missing == {"zzz_only_on_disk"}, f"the census did not name the forgotten write: {missing}"


def test_a_carrier_that_is_invisible_to_the_census_is_a_hole_not_a_pass() -> None:
    planted = _RUNNER_SEED.replace("entry.update(grade_v2(task))", "entry.update(nobody_exports_this(task))")
    trees = _trees_from({"m": planted, "r": _REPORT_SEED})
    _, blind = _keys_written_on_rows(trees)
    assert blind and "nobody_exports_this" in blind[0], (
        f"an unresolvable carrier must be reported as a blind spot: {blind}"
    )


def test_a_read_nobody_writes_is_named_unless_it_is_excused() -> None:
    planted_report = _REPORT_SEED.replace(
        "'turns': recorded.get('turns')",
        "'turns': recorded.get('turns'), 'ghost': recorded.get('ghost')")
    trees = _trees_from({"m": _RUNNER_SEED, "r": planted_report})
    written, _ = _keys_written_on_rows(trees)
    dead = _reads_nobody_writes(_recorded_reads(trees), written, EXCEPTIONS_FOR_UNWRITTEN_READS)
    assert dead == {"ghost"}, f"the permanently null read was not named: {dead}"


def test_an_exception_that_no_longer_describes_a_hole_is_refused() -> None:
    """The exception set cannot be left standing after the hole it excuses is fixed."""
    trees = _trees_from({"m": _RUNNER_SEED, "r": _REPORT_SEED})
    written, _ = _keys_written_on_rows(trees)
    reads = _recorded_reads(trees)
    for key in {"turns"}:
        stale = key in written or key not in reads
        assert stale, f"{key} should be refused as an exception"
    assert _reads_nobody_writes(reads, written, {"turns"}) == set()
