"""M8-T441 — 合并预检载荷四键两个家：干净分支与冲突分支各写一份"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/tools/git.py"

FIELDS = {"branch", "clean", "conflicts", "tree"}


def test_the_home_builds_the_probe() -> None:
    """The constructor owns the four keys."""
    from minicc.tools.git import _merge_probe

    assert _merge_probe("main", True, [], "oid") == {
        "branch": "main",
        "clean": True,
        "conflicts": [],
        "tree": "oid",
    }


def test_the_four_keys_are_spelled_exactly_once_in_the_package() -> None:
    """One literal, in the home - a second one is a second probe shape."""
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
        "the merge-probe payload is spelled by hand outside its one "
        "home: " + ", ".join(offenders)
    )


def test_both_branches_ask_the_home() -> None:
    """The clean branch, the conflicted branch, and the definition itself."""
    source = (REPO / HOME).read_text(encoding="utf-8")
    assert source.count("_merge_probe(") == 3, (
        "the definition plus the clean and conflicted branches are the "
        f"only spellings, found {source.count('_merge_probe(')}"
    )
