"""M6-4's "P95 may not degrade past the M4 baseline by more than 15%" needs a reader.

The standard was declared with the fan-out guard and re-measured in batch 185:
``bench_compare`` and ``benchmarks`` contained no 15% constant and no standing
gate, while a real 24-task run (2026-09-25) sat at p95 ~107s against the M4
baseline (826s). Batch 210's door in ``tests/test_ci_hygiene.py`` reconciles
*which* metrics the nightly gates, not how loose each floor is - a floor moved
from 600000ms to an hour would keep that door green while the 15% line stopped
being enforced.

So this door closes the loose direction instead of adding a second, redundant
gate: the nightly's absolute p95 floor must be at least as strict as the
standard (baseline from ``docs/BENCHMARK_EVALUATION.md``, tolerance from
``minicc/bench_compare.M6_4_TOLERANCE``). Removing the gate, or loosening it past
what the standard allows, reds here and names both numbers. The predicate is
also fed synthetic workflows both ways, because "the live file happens to pass"
is not evidence that the check can fail.

Boundary: token/task is the standard's other half. The document records a total
(~11.58M tokens over 30 tasks) and no per-task baseline, so a per-task floor
would be an invented reading; that half stays prose until a real M4 rerun.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
BASELINE_DOC = REPO_ROOT / "docs" / "BENCHMARK_EVALUATION.md"

P95_BASELINE_MS = 826_000  # the M4 reading the standard was written against
_BASELINE_ROW = re.compile(r"\|\s*`latency_p95_ms`\s*\|\s*(\d+(?:\.\d+)?)\s*s\s*\|")


def _documented_p95_baseline_ms() -> int:
    text = BASELINE_DOC.read_text(encoding="utf-8")
    matches = _BASELINE_ROW.findall(text)
    assert len(matches) == 1, (
        f"docs/BENCHMARK_EVALUATION.md must carry exactly one latency_p95_ms baseline row, "
        f"found {matches}"
    )
    return int(float(matches[0]) * 1000)


def _nightly_block(workflow_text: str) -> str:
    start = workflow_text.index("  eval-nightly:")
    rest = workflow_text[start + len("  eval-nightly:"):]
    following = re.search(r"^  \S", rest, re.MULTILINE)
    return rest[: following.start()] if following else rest


def _nightly_p95_floor(block: str) -> int | None:
    match = re.search(r"--gate\s+latency_p95_ms<=(\d+)", block)
    return int(match.group(1)) if match else None


def _coverage_problem(block: str, baseline_ms: int, tolerance: float) -> str | None:
    """Why the nightly no longer enforces the M6-4 line, or None when it does."""
    floor = _nightly_p95_floor(block)
    bound = baseline_ms * (1.0 + tolerance)
    if floor is None:
        return (
            "the nightly has no --gate latency_p95_ms floor, so the M6-4 15% line "
            f"(baseline {baseline_ms}ms) has no reader"
        )
    if floor > bound:
        return (
            f"the nightly permits latency_p95_ms up to {floor}ms, but the M6-4 standard "
            f"allows at most {bound:.0f}ms ({baseline_ms}ms baseline + {tolerance:.0%})"
        )
    return None


def test_the_documented_baseline_is_the_m4_reading_the_standard_names() -> None:
    """The baseline is data the door reads, not a number it retypes.

    Pinning 826s is deliberate: the M6-4 line was defined against that M4 run, so
    re-baselining it is a new decision. Editing the document alone would loosen
    the standard while every test stayed green - exactly the failure this file is
    about, one file up.
    """
    assert _documented_p95_baseline_ms() == P95_BASELINE_MS, (
        "docs/BENCHMARK_EVALUATION.md now names a different p95 baseline; the M6-4 "
        "standard was written against the M4 reading, so moving it needs a recorded "
        "decision rather than a silent edit"
    )


def test_the_nightly_floor_is_at_least_as_strict_as_the_m6_4_standard() -> None:
    import minicc.bench_compare as bench

    problem = _coverage_problem(
        _nightly_block(WORKFLOW.read_text(encoding="utf-8")),
        _documented_p95_baseline_ms(),
        bench.M6_4_TOLERANCE,
    )
    assert problem is None, problem


def test_the_coverage_predicate_sees_a_loosened_and_a_missing_floor() -> None:
    """Both failure directions, on synthetic workflows.

    Without these the live cell above could be green because the predicate never
    looks: a regex that matches nothing reads every workflow as compliant until
    the missing-floor branch is exercised too.
    """
    baseline, tolerance = 826_000, 0.15
    strict = "  eval-nightly:\n          --gate latency_p95_ms<=600000\n"
    assert _coverage_problem(strict, baseline, tolerance) is None

    loose = "  eval-nightly:\n          --gate latency_p95_ms<=1000000\n"
    problem = _coverage_problem(loose, baseline, tolerance)
    assert problem is not None and "1000000ms" in problem and "949900ms" in problem, problem

    missing = "  eval-nightly:\n          --gate pass_at_1>=0.3\n"
    problem = _coverage_problem(missing, baseline, tolerance)
    assert problem is not None and "no --gate latency_p95_ms floor" in problem, problem


def test_the_standard_names_a_metric_the_nightly_actually_gates() -> None:
    from minicc.bench_compare import GATE_FLOORS, GATE_METRICS, M6_4_METRIC, M6_4_TOLERANCE

    assert M6_4_TOLERANCE == 0.15, (
        "the standard is 15%; a different constant is a different standard"
    )
    assert M6_4_METRIC in GATE_METRICS, f"{M6_4_METRIC} is not a gateable metric"
    assert GATE_FLOORS[M6_4_METRIC].startswith("nightly"), (
        f"{M6_4_METRIC} must name the nightly as its floor owner; the M6-4 line is "
        "enforced through that floor"
    )
