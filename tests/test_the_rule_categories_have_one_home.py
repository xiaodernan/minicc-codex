"""M8-T387 — 规则三类别 {commands, paths, tools} 四个家：两个元组（顺序还不同）+ 两个 dict"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/allowlist.py"

CATEGORIES = frozenset({"commands", "paths", "tools"})


def test_the_home_exists_in_allowlist() -> None:
    """allowlist.py owns the three rule categories, in one canonical order."""
    from minicc.allowlist import RULE_CATEGORIES

    assert RULE_CATEGORIES == ("commands", "paths", "tools")


def test_the_empty_side_is_built_from_the_home() -> None:
    """empty_rule_side() has exactly the home's categories, no more, no fewer."""
    from minicc.allowlist import empty_rule_side

    assert set(empty_rule_side()) == CATEGORIES
    assert all(value == [] for value in empty_rule_side().values())


def test_no_module_spells_the_categories() -> None:
    """No module spells the three categories as a tuple/set/dict literal outside the home."""
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
            if isinstance(node, ast.Set | ast.Tuple | ast.List):
                elements = frozenset(
                    element.value
                    for element in node.elts
                    if isinstance(element, ast.Constant) and isinstance(element.value, str)
                )
                if len(node.elts) >= 3 and elements == CATEGORIES:
                    offenders.append(f"{relative}:{node.lineno} spells the categories")
            elif isinstance(node, ast.Dict):
                keys = frozenset(
                    key.value
                    for key in node.keys
                    if isinstance(key, ast.Constant) and isinstance(key.value, str)
                )
                if len(node.keys) >= 3 and keys == CATEGORIES:
                    offenders.append(f"{relative}:{node.lineno} builds a side by hand")
    assert not offenders, "rule categories spelled outside allowlist.py: " + ", ".join(offenders)


def test_both_normalizers_still_work() -> None:
    """Both readers still normalize their payloads from the shared categories."""
    from minicc.allowlist import _normalize_rules
    from minicc.permissions import _normalize_side

    rules = _normalize_rules({"commands": ["ls"], "tools": ["read_file"], "paths": ["src"]})
    assert set(rules) == CATEGORIES
    assert rules["commands"] == ["ls"]
    side = _normalize_side({"tools": ["bash"], "unknown_category": ["x"]})
    assert set(side) == CATEGORIES
    assert side["tools"] == ["bash"]
    assert side["commands"] == []
