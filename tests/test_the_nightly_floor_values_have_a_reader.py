"""M8-T539: the nightly floors' values have a reader, not just a roster.

Batch 210 gave every gateable metric a roster row saying who pins its floor
(``tests/test_ci_hygiene.py``). The *values* stayed hand-copied: ``GATE_FLOORS``
recorded "nightly >=0.3" and the workflow said ``--gate pass_at_1>=0.3``, and
nothing compared them, so either side could drift alone. Both comments also
claimed real-model v2 accuracy "is not yet characterised" while the roadmap
holds three clean full-suite portraits (13/24, 22/24, 24/24), and the nightly
step claimed that lowering a threshold below the achieved value "turns this
red" - a sentence no gate implemented, and one this door replaces with what it
actually checks: a pass@1 floor inside (0, 13/24].

This door reads the five nightly floors off both sides and requires them to be
the same numbers; keeps pass@1 above zero (a floor of zero gates nothing) and
at or below the worst clean portrait, 13/24 (a floor above what was measured
would red the nightly for a reason nobody decided); and requires the two
comments to name the portrait instead of claiming there is none.
"""

from __future__ import annotations

import re
from pathlib import Path

import minicc.bench_compare as bench_compare

REPO_ROOT = Path(__file__).resolve().parents[1]
CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"
ROADMAP = REPO_ROOT / "docs" / "ROADMAP_TO_PRODUCT.md"

_FLOOR_LINE = re.compile(r"^nightly\s*(>=|<=|>|<)\s*(-?\d+(?:\.\d+)?)")
_GATE = re.compile(r"--gate\s+([a-z0-9_]+)\s*(>=|<=|>|<)\s*(-?\d+(?:\.\d+)?)")
_PORTRAIT = re.compile(r"pass@1 \*\*(\d+)/(\d+) = (0\.\d+)\*\*")
_STALE_CLAIMS = ("not yet characterised", "not yet characterized")


def _registry_floors() -> dict[str, tuple[str, float]]:
    floors: dict[str, tuple[str, float]] = {}
    for metric, note in bench_compare.GATE_FLOORS.items():
        match = _FLOOR_LINE.match(note)
        if match:
            floors[metric] = (match.group(1), float(match.group(2)))
    return floors


def _workflow_block() -> str:
    text = CI.read_text(encoding="utf-8")
    start = text.index("- name: Apply absolute gates and emit JUnit")
    end = text.index("- name: Upload nightly eval artifacts", start)
    return text[start:end]


def _workflow_floors(block: str) -> dict[str, tuple[str, float]]:
    floors: dict[str, tuple[str, float]] = {}
    for metric, op, value in _GATE.findall(block):
        floors[metric] = (op, float(value))
    return floors


def _worst_portrait() -> tuple[int, int]:
    """The smallest pass@1 portrait the roadmap states in prose.

    The reader matches ``pass@1 **P/T = 0.xxxx**``; the same portraits written
    into table rows (13/24 -> 22/24 -> 24/24) do not carry that prefix, and the
    pinned ``(13, 24)`` below catches a prose spelling change rather than
    pretending to have parsed every table.
    """
    text = ROADMAP.read_text(encoding="utf-8")
    ratios = [(int(passed), int(total)) for passed, total, _ in _PORTRAIT.findall(text)]
    assert ratios, "the roadmap no longer states any clean full-suite pass@1 portrait in prose"
    return min(ratios, key=lambda pair: pair[0] / pair[1])


def _floor_problems(
    registry: dict[str, tuple[str, float]],
    workflow: dict[str, tuple[str, float]],
    portrait: tuple[int, int],
    comments: str,
) -> list[str]:
    problems: list[str] = []
    for metric in sorted(set(registry) | set(workflow)):
        left = registry.get(metric)
        right = workflow.get(metric)
        if left is None:
            problems.append(f"{metric}: pinned by the workflow ({right}) but absent from GATE_FLOORS")
        elif right is None:
            problems.append(f"{metric}: GATE_FLOORS says {left} but the workflow does not gate it")
        elif left != right:
            problems.append(f"{metric}: GATE_FLOORS says {left[0]}{left[1]:g}, the workflow says {right[0]}{right[1]:g}")
    pass_floor = registry.get("pass_at_1")
    if pass_floor is not None:
        op, value = pass_floor
        passed, total = portrait
        achieved = passed / total
        if op != ">=":
            problems.append(f"pass_at_1 floor {op}{value:g} is not a lower bound")
        if value <= 0:
            problems.append(f"pass_at_1 floor {value:g} gates nothing")
        if value > achieved:
            problems.append(
                f"pass_at_1 floor {value:g} is above the worst clean portrait {passed}/{total} = {achieved:.4f}; "
                "the nightly would red on a run nobody called a regression"
            )
    for claim in _STALE_CLAIMS:
        if claim in comments:
            problems.append(f"a comment still claims {claim!r} while the roadmap holds clean portraits")
    return problems


def test_the_registry_and_the_workflow_name_the_same_floors() -> None:
    registry = _registry_floors()
    workflow = _workflow_floors(_workflow_block())
    assert len(registry) >= 5, registry
    assert registry == workflow, _floor_problems(registry, workflow, _worst_portrait(), "")
    assert "pass_at_1" in registry


def test_the_pass_at_1_floor_sits_inside_the_measured_portrait() -> None:
    portrait = _worst_portrait()
    passed, total = portrait
    op, value = _registry_floors()["pass_at_1"]
    assert op == ">=" and 0 < value <= passed / total, (op, value, portrait)
    assert (passed, total) == (13, 24), (
        f"the worst prose portrait moved to {passed}/{total}; re-read the roadmap before trusting this door"
    )


def test_the_comments_name_the_portrait_instead_of_claiming_there_is_none() -> None:
    registry_note = bench_compare.GATE_FLOORS["pass_at_1"]
    ci_note = _workflow_block()
    for text, where in ((registry_note, "GATE_FLOORS"), (ci_note, "ci.yml")):
        for claim in _STALE_CLAIMS:
            assert claim not in text, (
                f"{where} still says real-model accuracy is {claim!r}; three clean full-suite "
                "portraits exist (13/24, 22/24, 24/24)"
            )
    assert "13/24" in registry_note and "13/24" in ci_note, (
        "each comment must name the worst clean portrait it is being compared against"
    )


def test_a_drifted_registry_is_red() -> None:
    registry = _registry_floors()
    workflow = _workflow_floors(_workflow_block())
    registry["pass_at_1"] = (">=", 0.9)
    problems = _floor_problems(registry, workflow, _worst_portrait(), "")
    assert any("pass_at_1" in problem and "0.9" in problem and "0.3" in problem for problem in problems), problems


def test_a_floor_above_the_portrait_is_red() -> None:
    registry = _registry_floors()
    workflow = _workflow_floors(_workflow_block())
    registry["pass_at_1"] = (">=", 0.6)
    workflow["pass_at_1"] = (">=", 0.6)
    problems = _floor_problems(registry, workflow, (13, 24), "")
    assert any("0.6" in problem and "13/24" in problem for problem in problems), problems


def test_a_zero_floor_is_red() -> None:
    registry = _registry_floors()
    workflow = _workflow_floors(_workflow_block())
    registry["pass_at_1"] = (">=", 0.0)
    workflow["pass_at_1"] = (">=", 0.0)
    problems = _floor_problems(registry, workflow, _worst_portrait(), "")
    assert any("gates nothing" in problem for problem in problems), problems


def test_a_lapsed_comment_is_red() -> None:
    registry = _registry_floors()
    workflow = _workflow_floors(_workflow_block())
    problems = _floor_problems(
        registry, workflow, _worst_portrait(), "real-model v2 accuracy is not yet characterised"
    )
    assert any("not yet characterised" in problem for problem in problems), problems
