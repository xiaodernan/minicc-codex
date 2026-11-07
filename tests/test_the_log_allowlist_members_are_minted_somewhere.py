"""M8-T601 — every logging-allowlist member is a key something mints.

``describe_event`` (minicc/logging_setup.py) prints a curated subset of the
event's ``detail`` keys for log grepping.  The allowlist previously carried
two members no emitter ever minted inside a detail dict - ``risk`` and
``authorization`` live only as top-level keys on the authorization frame
(``event["risk"] = risk``) - so they could never print and misled readers
into thinking authorization risk was logged there.

This gate pins the invariant that failed here: every member of the
``describe_event`` detail-allowlist must appear as a key in at least one
dict literal somewhere in ``minicc/``.  A key that is never a key anywhere
can never match inside a detail dict either, and silently does nothing
while looking load-bearing.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
LOGGING = PACKAGE / "logging_setup.py"


def _allowlist() -> list[str]:
    tree = ast.parse(LOGGING.read_text(encoding="utf-8"), filename=str(LOGGING))
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.For)
            and isinstance(node.target, ast.Name)
            and node.target.id == "key"
        ):
            continue
        if (
            isinstance(node.iter, ast.Tuple)
            and all(isinstance(elt, ast.Constant) for elt in node.iter.elts)
        ):
            return [
                elt.value
                for elt in node.iter.elts
                if isinstance(elt.value, str)
            ]
    raise AssertionError("the detail-allowlist loop was not found in minicc/logging_setup.py")


def _all_dict_keys() -> set[str]:
    keys: set[str] = set()
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            for key in node.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    keys.add(key.value)
    return keys


def test_every_allowlist_member_is_minted_somewhere() -> None:
    members = _allowlist()
    assert members, "the allowlist must not be empty"
    minted = _all_dict_keys()
    dead = [member for member in members if member not in minted]
    assert dead == [], (
        "these describe_event allowlist members are never a dict key anywhere "
        "in minicc/, so they can never match a detail dict and can never "
        f"print: {dead}"
    )


def test_the_allowlist_is_the_documented_four() -> None:
    # The two proven-dead members were removed; this pins the current
    # allowlist so it cannot silently grow members nobody mints again.
    assert _allowlist() == ["turn", "attempt", "retry", "tool_count"]
