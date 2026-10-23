"""M8-T428 — hook 执行记录四键两个家：预算跳过与 _run_one 初始态各写一份"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/hooks.py"

FIELDS = {"command", "decision", "event", "reason"}


def test_the_home_builds_the_entry() -> None:
    """The base shape: waved through, no reason yet."""
    from minicc.hooks import hook_entry

    assert hook_entry("PreToolUse", "echo hi") == {
        "event": "PreToolUse",
        "command": "echo hi",
        "decision": "allow",
        "reason": "",
    }


def test_the_four_keys_are_spelled_exactly_once_in_the_package() -> None:
    """One literal, in the home - a second one is a second record shape."""
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        relative = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            keys = {
                key.value
                for key in node.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
            if keys == FIELDS:
                offenders.append(f"{relative}:{node.lineno}")
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the hook execution record is spelled by hand outside its one "
        "home: " + ", ".join(offenders)
    )


def test_both_sites_ask_the_home() -> None:
    """The budget-skip output spreads it, _run_one starts from it."""
    source = (REPO / HOME).read_text(encoding="utf-8")
    assert source.count("hook_entry(") == 3, (
        "the definition plus the budget-skip spread and _run_one's "
        f"initial entry are the only spellings, found {source.count('hook_entry(')}"
    )
