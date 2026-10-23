"""M8-T442 — 编排结果三键两个家：取消出口与合并出口各写一份"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/task_manager.py"

FIELDS = {"answer", "cancelled", "children"}


def test_the_home_builds_the_result() -> None:
    """The constructor owns the three keys."""
    from minicc.task_manager import _orchestration_result

    assert _orchestration_result("done", False, [{"id": 1}]) == {
        "answer": "done",
        "cancelled": False,
        "children": [{"id": 1}],
    }


def test_the_three_keys_are_spelled_exactly_once_in_the_package() -> None:
    """One literal, in the home - a second one is a second result shape."""
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
        "the orchestration result is spelled by hand outside its one "
        "home: " + ", ".join(offenders)
    )


def test_both_exits_ask_the_home() -> None:
    """The cancelled exit, the merged exit, and the definition itself."""
    source = (REPO / HOME).read_text(encoding="utf-8")
    assert source.count("_orchestration_result(") == 3, (
        "the definition plus the two exits are the only spellings, "
        f"found {source.count('_orchestration_result(')}"
    )
