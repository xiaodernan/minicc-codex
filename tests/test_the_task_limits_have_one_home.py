"""M8-T597 — the two 64 task retention limits have one home.

``DEFAULT_TASK_USAGE_LIMIT`` and ``DEFAULT_TASK_COMPACTION_LIMIT`` were
defined in both ``minicc/config.py`` (the config home, where
``MINICC_TASK_USAGE_LIMIT`` / ``MINICC_TASK_COMPACTION_LIMIT`` are read and
validated against the documented 8-512 clamp) and ``minicc/task_manager.py``
(where the task service consumes them) — two homes for the same defaults,
and ``web.py`` re-exported the task_manager copies. A change to one home
would silently not reach the other.

``minicc/config.py`` is the one home now; task_manager and web.py ask it.
This gate pins:

* both names are assigned exactly once each, in minicc/config.py, with the
  documented default (64);
* no other file under minicc/ defines either name (a copy is drift);
* the documented env clamp is validated there by source inspection (the
  8-512 pick exists), so the home stays honest about its contract.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = PACKAGE / "config.py"
NAMES = ("DEFAULT_TASK_USAGE_LIMIT", "DEFAULT_TASK_COMPACTION_LIMIT")


def _definitions(tree: ast.Module):
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = node.targets
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value = node.value
        else:
            continue
        names = [t.id for t in targets if isinstance(t, ast.Name)]
        for name in names:
            yield name, value, node


def test_the_home_defines_the_two_limits() -> None:
    tree = ast.parse(HOME.read_text(encoding="utf-8"), filename=str(HOME))
    found: dict[str, int] = {}
    for name, value, node in _definitions(tree):
        if name in NAMES and isinstance(value, ast.Constant):
            found[name] = value.value  # type: ignore[assignment]
    assert found.get("DEFAULT_TASK_USAGE_LIMIT") == 64
    assert found.get("DEFAULT_TASK_COMPACTION_LIMIT") == 64


def test_no_other_module_defines_the_limits() -> None:
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        if path.resolve() == HOME.resolve():
            continue
        relative = path.relative_to(REPO).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for name, value, node in _definitions(tree):
            if name in NAMES:
                offenders.append(f"{relative}:{node.lineno}: {name}")
    assert offenders == [], (
        "these files define a copy of the task limits (ask minicc/config.py "
        f"instead): {offenders}"
    )


def test_the_home_clamps_the_env_spelling() -> None:
    source = HOME.read_text(encoding="utf-8")
    assert "MINICC_TASK_USAGE_LIMIT" in source
    assert "MINICC_TASK_COMPACTION_LIMIT" in source
    assert "8-512" in source
