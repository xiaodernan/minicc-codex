"""M8-T597/M8-T602 — the five task retention limits have one home.

Five module-level constants live only in ``minicc/config.py`` (the config
home, where the ``MINICC_TASK_*_LIMIT`` env vars are read and validated
against their documented clamps).  They were duplicated in
``minicc/task_manager.py`` — and ``web.py`` re-exported the manager copies.
A change to one home would silently not reach the other.

``minicc/config.py`` is the one home now; task_manager and web.py ask it.
This gate pins:

* all five names are assigned exactly once each, in minicc/config.py, with
  the documented default (768 / 16_000 / 32 / 64 / 64);
* no other file under minicc/ defines any of them (a copy is drift);
* the documented env clamps are validated there by source inspection
  (each env pick exists), so the home stays honest about its contract.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = PACKAGE / "config.py"
NAMES = (
    "DEFAULT_TASK_EVENT_LIMIT",
    "DEFAULT_TASK_STREAM_LIMIT",
    "DEFAULT_TASK_QUEUE_LIMIT",
    "DEFAULT_TASK_USAGE_LIMIT",
    "DEFAULT_TASK_COMPACTION_LIMIT",
)
VALUES = {
    "DEFAULT_TASK_EVENT_LIMIT": 768,
    "DEFAULT_TASK_STREAM_LIMIT": 16_000,
    "DEFAULT_TASK_QUEUE_LIMIT": 32,
    "DEFAULT_TASK_USAGE_LIMIT": 64,
    "DEFAULT_TASK_COMPACTION_LIMIT": 64,
}


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


def test_the_home_defines_all_five_limits() -> None:
    tree = ast.parse(HOME.read_text(encoding="utf-8"), filename=str(HOME))
    found: dict[str, int] = {}
    for name, value, node in _definitions(tree):
        if name in VALUES and isinstance(value, ast.Constant):
            found[name] = value.value  # type: ignore[assignment]
    missing = [name for name in NAMES if name not in found]
    assert not missing, f"the home config.py is missing definitions for {missing}"
    for name, expected in VALUES.items():
        assert found[name] == expected, f"{name} drifted from {expected} to {found[name]}"


def test_no_other_module_defines_any_limit() -> None:
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


def test_the_home_clamps_the_env_spellings() -> None:
    source = HOME.read_text(encoding="utf-8")
    for name in (
        "MINICC_TASK_EVENT_LIMIT",
        "MINICC_TASK_STREAM_LIMIT",
        "MINICC_TASK_QUEUE_LIMIT",
        "MINICC_TASK_USAGE_LIMIT",
        "MINICC_TASK_COMPACTION_LIMIT",
    ):
        assert name in source, f"{name} is not validated in minicc/config.py's env layer"
    for expected in ("32-10000", "512-100000", "1-256", "8-512"):
        assert expected in source, f"the documented clamp {expected!r} is missing from config.py"
