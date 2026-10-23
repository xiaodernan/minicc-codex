"""M8-T429 — todo 工具结果载荷三键两个家：read 与 write 各写一份"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/tools/todo.py"

FIELDS = {"source", "todos", "updated_at"}


def test_the_home_builds_the_payload() -> None:
    """The constructor owns the three keys and names the verb."""
    from minicc.tools.todo import _tool_data

    payload = _tool_data([{"content": "x"}], "2026-01-01T00:00:00Z", "read")
    assert payload == {
        "todos": [{"content": "x"}],
        "updated_at": "2026-01-01T00:00:00Z",
        "source": "read",
    }


def test_the_three_keys_are_spelled_exactly_once_in_the_package() -> None:
    """One literal, in the home - a second one is a second payload shape.

    The on-disk payload (``todos`` + ``updated_at``, no ``source``) is
    a different fact with two of these keys and is not an offender.
    """
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
        "the todo tool payload is spelled by hand outside its one "
        "home: " + ", ".join(offenders)
    )


def test_both_verbs_ask_the_home() -> None:
    """Read and write plus the definition itself."""
    source = (REPO / HOME).read_text(encoding="utf-8")
    assert source.count("_tool_data(") == 3, (
        "the definition plus the read and write results are the only "
        f"spellings, found {source.count('_tool_data(')}"
    )
