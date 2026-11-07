"""M8-T587 — the six stage names have one home, tests included.

``STAGE_NAMES`` (minicc/config.py) is the gated home for the six pipeline
stage names.  Four places in the test suite hand-spelled the full six (three
tuples used for routing-equivalence loops and one leftover ordered tuple),
so a seventh stage added to the home would silently not be exercised by
those loops — and nothing would fail.

This gate pins: no container literal anywhere under ``tests/`` carries five
or more of the six stage names.  Tests that care about the ordering ask the
home (``tuple(sorted(STAGE_NAMES))``).
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TESTS = REPO / "tests"
# Built from a string on purpose: writing the names as a container literal
# here would make this gate flag itself.
STAGE_NAMES = set("inspect planning implement verify repair review".split())


def test_no_test_file_spells_five_or_more_stage_names() -> None:
    offenders: list[str] = []
    for path in sorted(TESTS.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Set, ast.Tuple, ast.List)):
                continue
            values = {
                elt.value
                for elt in node.elts
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
            }
            if len(values & STAGE_NAMES) >= 5:
                offenders.append(f"{path.relative_to(REPO).as_posix()}:{node.lineno}: {sorted(values & STAGE_NAMES)}")
    assert offenders == [], (
        "these containers re-spell the stage names (ask STAGE_NAMES from "
        f"minicc/config.py instead): {offenders}"
    )


def test_the_home_carries_the_six_stages() -> None:
    from minicc.config import STAGE_NAMES as HOME

    assert HOME == STAGE_NAMES
