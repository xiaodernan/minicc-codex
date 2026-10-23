"""M8-T434 — 预算快照两键三个家：wrap-up 通知与两个停止出口各写一份"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/agent/loop.py"

FIELDS = {"elapsed_seconds", "tokens"}


class _Budget:
    tokens = 42

    def elapsed_seconds(self) -> float:
        return 1.23456


def test_the_home_builds_the_snapshot() -> None:
    """The constructor owns the two keys and the rounding rule."""
    from minicc.agent.loop import _budget_snapshot

    snapshot = _budget_snapshot(_Budget())
    assert snapshot == {"tokens": 42, "elapsed_seconds": 1.235}
    assert set(snapshot) == FIELDS


def test_the_two_keys_are_spelled_exactly_once_in_the_package() -> None:
    """One literal, in the home - a second one is a second snapshot."""
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
        "the budget snapshot is spelled by hand outside its one home: "
        + ", ".join(offenders)
    )


def test_every_budget_event_asks_the_home() -> None:
    """The wrap-up spread, the two stop events, and the definition itself."""
    source = (REPO / HOME).read_text(encoding="utf-8")
    assert source.count("_budget_snapshot(") == 4, (
        "the definition plus the wrap-up spread and the two stop "
        f"events are the only spellings, found {source.count('_budget_snapshot(')}"
    )
