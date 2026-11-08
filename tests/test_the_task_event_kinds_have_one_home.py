"""M8-T603 — the task-event kinds have one home.

``TASK_EVENT_KINDS`` (minicc/agent/protocol.py) is the contract between the
task runtime (emitter) and the web face's reducer (consumer).  It was
spelled at twelve emit sites and, on the other side, as eight ``case ""``
arms in ``web/src/core/task-reducer.js`` — two hand-kept copies of one fact,
and no default arm in the switch, so a drifted or new kind vanishes
silently in the UI.

This gate pins:

* the home defines exactly the eight kinds;
* every ``_publish_locked`` call in ``minicc/`` passes a literal that is a
  member of the home (no emitter invents a kind);
* the observed emit kinds (first positional argument to ``_publish_locked``)
  are **exactly** the home's — a member that nothing mints is a member that
  can be silently dropped from both sides, and a future kind would show up
  here as well;
* the JS reducer's case arms (via the frontend smoke) equal the home,
  so the wire vocabulary cannot drift on either side.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = PACKAGE / "agent" / "protocol.py"

KINDS = {
    "timeline",
    "stream_delta",
    "state",
    "status",
    "usage",
    "context",
    "compaction",
    "result",
}


def _home_text() -> str:
    return HOME.read_text(encoding="utf-8")


def test_the_home_defines_exactly_the_eight_kinds() -> None:
    source = _home_text()
    assert "TASK_EVENT_KINDS = frozenset(" in source
    tree = ast.parse(source, filename=str(HOME))
    found = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "TASK_EVENT_KINDS" for t in node.targets
        ):
            value = node.value
            assert isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == "frozenset"
            assert len(value.args) == 1
            arg = value.args[0]
            assert isinstance(arg, ast.Set)
            found = {
                elt.value
                for elt in arg.elts
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
            }
    assert found == KINDS, f"the home drifted from {sorted(KINDS)} to {sorted(found)}"


def _publish_locked_kinds(tree: ast.Module):
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = ""
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        if name != "_publish_locked" or not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            yield first.value, node.lineno


def test_every_emit_site_kind_is_in_the_home() -> None:
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        relative = path.relative_to(REPO).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        for kind, lineno in _publish_locked_kinds(tree) or []:
            if kind not in KINDS:
                offenders.append(f"{relative}:{lineno}: {kind}")
    assert offenders == [], (
        "these _publish_locked calls pass a kind that is not in the home "
        f"(minicc/agent/protocol.py TASK_EVENT_KINDS): {offenders}"
    )


def test_the_observed_emit_kinds_equal_the_home() -> None:
    seen: set[str] = set()
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for kind, _lineno in _publish_locked_kinds(tree):
            seen.add(kind)
    assert seen == KINDS, (
        "the kinds minted at emit sites differ from the home: "
        f"home-mint missing {sorted(KINDS - seen)}, minted-but-missing {sorted(seen - KINDS)}"
    )
