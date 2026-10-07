"""The latency baselines M4 promised must exist, and must agree with their source.

M4's fifth exit criterion says the P50/P95 baselines are written into
``docs/BENCHMARK_EVALUATION.md``. They were not: ``git log -S latency_p95_ms --``
that file returned nothing, so the numbers only ever lived in the audit document
that quoted them. The tracking table in section six pointed at this file anyway, and
M6 was supposed to gate on them.

Two things are therefore asserted: the baseline section exists with both metrics, and
its numbers equal the ones the audit document states. The cross-check is the point -
a baseline that is updated in one document and not the other is a claim with two
values, and the regression gate built on it would be measuring whichever one it
happened to read.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EVALUATION = REPO_ROOT / "docs" / "BENCHMARK_EVALUATION.md"
AUDIT = REPO_ROOT / "docs" / "AUDIT_2026-09-20.md"

BASELINES = {"latency_p50_ms": 115, "latency_p95_ms": 826}


def _evaluation_numbers() -> dict[str, int]:
    """The values this document states for the two baseline metrics."""
    text = EVALUATION.read_text(encoding="utf-8")
    found: dict[str, int] = {}
    for metric in BASELINES:
        # A table row such as: | `latency_p95_ms` | 826s | ...
        match = re.search(rf"`{metric}`\s*\|\s*(\d+)\s*s", text)
        if match:
            found[metric] = int(match.group(1))
    return found


def test_the_baseline_section_states_both_metrics() -> None:
    text = EVALUATION.read_text(encoding="utf-8")
    assert "延迟基线" in text, "the M4 baseline section is gone from the evaluation document"
    found = _evaluation_numbers()
    assert set(found) == set(BASELINES), (
        f"the evaluation document states {sorted(found)}; both baselines must be spelled out "
        f"as `metric` | <number>s rows"
    )


def test_the_baseline_agrees_with_the_audit_that_recorded_it() -> None:
    audit = AUDIT.read_text(encoding="utf-8")
    stated = re.search(r"P50\s*(\d+)s\s*、\s*P95\s*(\d+)s", audit)
    assert stated, "the audit document no longer states the P50/P95 pair this baseline came from"
    from_audit = {"latency_p50_ms": int(stated.group(1)), "latency_p95_ms": int(stated.group(2))}
    assert _evaluation_numbers() == from_audit, (
        "the two documents disagree about the baseline: "
        f"evaluation={_evaluation_numbers()} audit={from_audit} - update both or neither"
    )
    assert from_audit == BASELINES, (
        f"the recorded baseline changed to {from_audit}; re-baselining is deliberate, so update "
        "BASELINES here in the same commit and say what the new run was"
    )
