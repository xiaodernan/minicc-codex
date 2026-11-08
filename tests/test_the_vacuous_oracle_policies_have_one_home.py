"""M8-T608 — the vacuous-oracle policies have one home.

``VACUOUS_ORACLE_POLICIES`` (minicc/benchmarks.py) enumerates the legal
policies for a vacuous oracle row ("allow" | "deny" | "require_case_count").
``VACUOUS_ORACLE_POLICY`` (the active policy) is one of them; the default
is the zeroth. A test parametrize that spelled the three strings by hand
would drift from the home silently; both tests ask the home now.
This gate pins:

* the home tuple is exactly those three policies;
* the home's active policy is the zeroth of the tuple;
* no other module in ``minicc/`` assigns this tuple.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = PACKAGE / "benchmarks.py"

EXPECTED = ("allow", "deny", "require_case_count")


def test_the_home_defines_the_policies() -> None:
    from minicc.benchmarks import VACUOUS_ORACLE_POLICIES, VACUOUS_ORACLE_POLICY

    assert VACUOUS_ORACLE_POLICIES == EXPECTED
    assert VACUOUS_ORACLE_POLICY == VACUOUS_ORACLE_POLICIES[0]


def test_no_other_module_redefines_the_policies() -> None:
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        if path.resolve() == HOME.resolve():
            continue
        relative = path.relative_to(REPO).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if isinstance(node, ast.Assign):
                targets = node.targets
                value = node.value
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target] if isinstance(node.target, ast.Name) else []
                value = node.value
            else:
                continue
            if value and isinstance(value, ast.Tuple):
                members = tuple(
                    elt.value for elt in value.elts
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                )
                if members == EXPECTED:
                    for target in targets:
                        if isinstance(target, ast.Name) and target.id == "VACUOUS_ORACLE_POLICIES":
                            offenders.append(f"{relative}:{node.lineno}: VACUOUS_ORACLE_POLICIES")
    assert offenders == [], f"these files re-define VACUOUS_ORACLE_POLICIES: {offenders}"
