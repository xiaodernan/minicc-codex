"""M8-T440 — 遍历统计三键两个家：初始零形状与记录值各写一份"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/agent/retrieval.py"

FIELDS = {"directories_walked", "files_seen", "stopped_early"}


def test_the_home_builds_the_stats() -> None:
    """The constructor owns the three keys."""
    from minicc.agent.retrieval import _walk_stats

    assert _walk_stats(0, 0, False) == {
        "files_seen": 0,
        "directories_walked": 0,
        "stopped_early": False,
    }
    assert _walk_stats(12, 3, True) == {
        "files_seen": 12,
        "directories_walked": 3,
        "stopped_early": True,
    }


def test_the_three_keys_are_spelled_exactly_once_in_the_package() -> None:
    """One literal, in the home - a second one is a second denominator."""
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
        "the walk denominator is spelled by hand outside its one "
        "home: " + ", ".join(offenders)
    )


def test_both_writes_ask_the_home() -> None:
    """The initial zero shape, the recorded one, and the definition itself."""
    source = (REPO / HOME).read_text(encoding="utf-8")
    assert source.count("_walk_stats(") == 3, (
        "the definition plus the initial and recorded shapes are the "
        f"only spellings, found {source.count('_walk_stats(')}"
    )
