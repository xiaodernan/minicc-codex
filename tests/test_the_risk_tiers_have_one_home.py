"""M8-T590 — the readonly/write/exec risk tiers have one home.

``RISK_LEVELS`` (minicc/tools/registry.py) is the gated home for the three
declared tool risk levels.  The same trio kept re-appearing as hand-spelled
containers next to it: ``RISK_ORDER`` (registry), ``RISK_ORDER``'s values,
``SUBAGENT_TOOL_TIERS`` (subagent), the timeout budget/mode-note blocks, and
the planner's deliberately *larger* kind set (which extends the trio and is
a different vocabulary, not a copy).

This gate pins:

* the home itself is the trio, in the documented order;
* ``RISK_ORDER`` and ``AUTHORIZATION_RISKS`` are derived from the home
  (correct shape, correct members);
* ``SUBAGENT_TOOL_TIERS`` is keyed by exactly the home;
* ``PLANNER_KINDS`` extends the home by exactly {review, merge} — the one
  place a superset is legal, so a future drift there is visible too;
* no container in ``minicc/`` keyed by exactly the trio exists outside the
  enumerated sites (new hand copies are drift).
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
TRIO = {"readonly", "write", "exec"}
# The sites allowed to spell a container keyed by exactly the trio:
# (relative path, assigned name or "<inline>").  Anything else is drift.
ALLOWED_EXACT = {
    ("minicc/tools/registry.py", "RISK_LEVELS"),
    ("minicc/tools/registry.py", "RISK_ORDER"),
    ("minicc/agent/subagent.py", "SUBAGENT_TOOL_TIERS"),
    ("minicc/agent/subagent.py", "mode_note"),
}


def test_the_home_is_the_trio_in_the_documented_order() -> None:
    from minicc.tools.registry import RISK_LEVELS, RISK_ORDER, AUTHORIZATION_RISKS

    assert RISK_LEVELS == ("readonly", "write", "exec")
    assert set(RISK_ORDER) == TRIO
    assert list(RISK_ORDER.values()) == sorted(RISK_ORDER.values())
    assert AUTHORIZATION_RISKS == frozenset(TRIO) - {"readonly"}


def test_the_subagent_tiers_are_the_home_trio() -> None:
    from minicc.tools.registry import RISK_LEVELS
    from minicc.agent.subagent import SUBAGENT_TOOL_TIERS

    assert set(SUBAGENT_TOOL_TIERS) == set(RISK_LEVELS)


def test_the_planner_kind_set_extends_the_trio_by_review_and_merge() -> None:
    from minicc.agent.planner import PLANNER_KINDS, PLANNER_KIND_TOOLS

    assert PLANNER_KINDS == frozenset({"readonly", "write", "exec", "review", "merge"})
    assert TRIO <= PLANNER_KINDS
    assert set(PLANNER_KIND_TOOLS) == PLANNER_KINDS


def _container_of(value):
    if isinstance(value, (ast.Dict, ast.Set, ast.Tuple, ast.List)):
        yield value
    elif isinstance(value, ast.Subscript):
        yield from _container_of(value.value)
    elif isinstance(value, ast.Call):
        for arg in value.args:
            yield from _container_of(arg)


def _members_of(container):
    if isinstance(container, ast.Dict):
        elts = container.keys
    else:
        elts = container.elts
    return {
        elt.value
        for elt in elts
        if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
    }


def _exact_trio_containers(tree: ast.Module):
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            target = names[0] if names else "<inline>"
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target = node.target.id
            value = node.value
        else:
            continue
        if value is None:
            continue
        for container in _container_of(value):
            yield node, target, _members_of(container)


def test_no_new_container_is_keyed_by_exactly_the_trio() -> None:
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        relative = path.relative_to(REPO).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node, name, members in _exact_trio_containers(tree):
            if members == TRIO and (relative, name) not in ALLOWED_EXACT:
                offenders.append(f"{relative}:{node.lineno}: {name}")
    assert offenders == [], (
        "these containers are keyed by exactly the risk trio - new copies of "
        f"it drift; derive them from minicc/tools/registry.py's RISK_LEVELS: {offenders}"
    )
