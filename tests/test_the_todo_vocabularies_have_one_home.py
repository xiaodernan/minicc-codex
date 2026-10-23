"""M8-T384 — todo 清单的两个词表各有三个家：todo.py / 工具 schema / 前端 normalizer"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
WEB_SRC = REPO / "web" / "src"

TODO_STATUSES = ("pending", "in_progress", "completed")
TODO_PRIORITIES = ("high", "medium", "low")
HOME = "minicc/tools/todo.py"
WEB_HOME = "web/src/core/state.js"


def test_the_homes_exist_in_todo_py() -> None:
    """todo.py owns both vocabularies with the expected members."""
    from minicc.tools.todo import TODO_PRIORITIES as Priorities
    from minicc.tools.todo import TODO_STATUSES as Statuses

    assert set(Statuses) == set(TODO_STATUSES)
    assert set(Priorities) == set(TODO_PRIORITIES)


def test_the_tool_schema_advertises_the_home() -> None:
    """The todo_write input schema's enums are the home's members, not a copy."""
    from minicc.tools import build_registry
    from minicc.tools.editor import Editor

    registry = build_registry(Editor(REPO))
    spec = registry.spec("todo_write")
    assert spec is not None and spec.input_schema is not None
    items = spec.input_schema["properties"]["todos"]["items"]["properties"]
    assert set(items["status"]["enum"]) == set(TODO_STATUSES)
    assert set(items["priority"]["enum"]) == set(TODO_PRIORITIES)


def test_no_module_inlines_the_todo_vocabularies() -> None:
    """No Python module spells either vocabulary as a literal outside todo.py."""
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
            if not isinstance(node, ast.List | ast.Tuple | ast.Set):
                continue
            elements = tuple(
                element.value
                for element in node.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            )
            if len(node.elts) < 2 or len(elements) != len(node.elts):
                continue
            if set(elements) == set(TODO_STATUSES):
                offenders.append(f"{relative}:{node.lineno} spells TODO_STATUSES")
            if set(elements) == set(TODO_PRIORITIES):
                offenders.append(f"{relative}:{node.lineno} spells TODO_PRIORITIES")
    assert not offenders, "inline todo vocabularies outside todo.py: " + ", ".join(offenders)


def test_the_frontend_home_carries_both_vocabularies() -> None:
    """web/src/core/state.js is the frontend's one home for both vocabularies."""
    source = (REPO / WEB_HOME).read_text(encoding="utf-8")
    for name, members in (
        ("TODO_STATUSES", TODO_STATUSES),
        ("TODO_PRIORITIES", TODO_PRIORITIES),
    ):
        block = re_search_set(source, name)
        assert block is not None, f"{WEB_HOME} must export {name}"
        assert set(block) == set(members), f"{name} in {WEB_HOME}: {sorted(block)}"


def re_search_set(source: str, name: str) -> list[str] | None:
    import re

    match = re.search(rf"export const {name} = new Set\(\[([\s\S]*?)\]\);", source)
    if match is None:
        return None
    return re.findall(r'"([a-z_]+)"', match.group(1))
