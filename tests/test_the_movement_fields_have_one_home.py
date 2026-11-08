"""M8-T605 — the movement-fields vocabulary has one home.

``MOVEMENT_FIELDS`` (minicc/bench_compare.py) names the six keys of the
compare report that answer "did the variant move relative to the baseline".
The home is consumed by compare_reports' publish gate; a test that
imported its own copy would drift silently, so the home itself has the
definition. This gate pins that no module under ``minicc/`` re-defines the
same tuple of names.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = PACKAGE / "bench_compare.py"

EXPECTED = {
    "pass_at_1_delta",
    "pass_at_1_delta_ci",
    "cost_per_success_delta",
    "cost_per_success_delta_ci",
    "latency_p50_delta_ms",
    "latency_p95_delta_ms",
}


def _assigns_tuple_to_name(tree: ast.Module, name: str):
    for node in tree.body:
        target_names = []
        value = None
        if isinstance(node, ast.Assign):
            target_names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target_names = [node.target.id]
            value = node.value
        if name not in target_names or value is None:
            continue
        if isinstance(value, ast.Tuple):
            yield name, {
                elt.value
                for elt in value.elts
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
            }, node


def test_the_home_defines_movement_fields() -> None:
    from minicc.bench_compare import MOVEMENT_FIELDS

    assert MOVEMENT_FIELDS == (
        "pass_at_1_delta",
        "pass_at_1_delta_ci",
        "cost_per_success_delta",
        "cost_per_success_delta_ci",
        "latency_p50_delta_ms",
        "latency_p95_delta_ms",
    )
    assert set(MOVEMENT_FIELDS) == EXPECTED


def test_no_other_module_redefines_the_movement_fields() -> None:
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        if path.resolve() == HOME.resolve():
            continue
        relative = path.relative_to(REPO).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for name, members, node in _assigns_tuple_to_name(tree, "MOVEMENT_FIELDS"):
            offenders.append(f"{relative}:{node.lineno}: {sorted(members)}")
    assert offenders == [], (
        "these modules re-define MOVEMENT_FIELDS (the home is minicc/bench_compare.py): "
        + ", ".join(offenders)
    )
