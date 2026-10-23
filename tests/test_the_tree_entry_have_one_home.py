"""M8-T433 — 文件树条目四键两个家：目录与文件两个分支各写一份"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/web.py"

FIELDS = {"name", "path", "size", "type"}


def test_the_home_builds_the_entry() -> None:
    """The constructor owns the four keys."""
    from minicc.web import _tree_entry

    assert _tree_entry("a.py", "src/a.py", "file", 12) == {
        "name": "a.py",
        "path": "src/a.py",
        "type": "file",
        "size": 12,
    }
    assert _tree_entry("src", "src", "dir", 0)["size"] == 0


def test_the_four_keys_are_spelled_exactly_once_in_the_package() -> None:
    """One literal, in the home - a second one is a second entry shape."""
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
        "the file-tree entry is spelled by hand outside its one home: "
        + ", ".join(offenders)
    )


def test_both_branches_ask_the_home() -> None:
    """The dir branch, the file branch, and the definition itself."""
    source = (REPO / HOME).read_text(encoding="utf-8")
    assert source.count("_tree_entry(") == 3, (
        "the definition plus the dir and file branches are the only "
        f"spellings, found {source.count('_tree_entry(')}"
    )
