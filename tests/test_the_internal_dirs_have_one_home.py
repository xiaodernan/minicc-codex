"""M8-T385 — 工作区内部目录 {.git, .minicc} 一个事实两个家：changes / snapshots"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/changes.py"

INTERNAL_DIRS = frozenset({".git", ".minicc"})


def test_the_home_exists_in_changes() -> None:
    """changes.py owns the internal-directory set with both members."""
    from minicc.changes import INTERNAL_DIRS as Home

    assert Home == INTERNAL_DIRS


def test_snapshots_asks_the_home() -> None:
    """snapshots.py uses the same object, not its own spelling."""
    import minicc.changes as changes
    import minicc.snapshots as snapshots

    assert snapshots.INTERNAL_DIRS is changes.INTERNAL_DIRS


def test_no_module_inlines_the_internal_dirs() -> None:
    """No other module spells {".git", ".minicc"} as a literal."""
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        relative = path.relative_to(REPO).as_posix()
        if relative == HOME:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Set | ast.Tuple | ast.List):
                continue
            elements = frozenset(
                element.value
                for element in node.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            )
            if len(node.elts) >= 2 and elements == INTERNAL_DIRS:
                offenders.append(f"{relative}:{node.lineno}")
    assert not offenders, "inline internal-dir sets outside changes.py: " + ", ".join(offenders)


def test_both_readers_still_behave() -> None:
    """The two readers still answer their own questions from the shared home."""
    from minicc.changes import _ignored_path
    from minicc.snapshots import _relative

    assert _ignored_path(".minicc/todos.json") is True
    assert _ignored_path(".git/config") is True
    assert _ignored_path("src/main.py") is False
    with pytest.raises(Exception):
        _relative(".minicc/audit.jsonl")
    assert _relative("src/main.py") == "src/main.py"
