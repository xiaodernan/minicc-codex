#!/usr/bin/env python3
"""One-command reliability probe for the M1 core-pipeline defects.

Reproduces every M1 finding (T1-T7) by running the pinned regression cases that
encode the original audit repro scripts. Exits 0 only when all of them pass, so
it can gate a dedicated CI job (red on any regression).

Usage:
    python scripts/reliability_probe.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Each entry maps an M1 defect to the regression case that fails red on the
# pre-fix code and green after. Keeping node IDs explicit means the probe stays
# a precise defect reproduction rather than a whole-suite run.
PROBE_TARGETS: tuple[tuple[str, str], ...] = (
    ("M1-T1 恢复阶段死循环", "tests/test_m1_integrity.py::test_m1t1_recovery_required_does_not_loop_on_plain_text"),
    ("M1-T2 tool_call id 复用", "tests/test_m1_integrity.py::test_m1t2_tool_call_ids_deduplicated"),
    ("M1-T3 流式增量吞字符", "tests/test_m1_integrity.py::test_m1t3_incremental_deltas_concatenated_byte_for_byte"),
    ("M1-T4 非终止 finish_reason 被接受", "tests/test_m1_integrity.py::test_m1t4_nonterminal_finish_reason_never_accepted"),
    ("M1-T4 持续非终止未失败", "tests/test_m1_integrity.py::test_m1t4_persistent_nonterminal_fails"),
    ("M1-T5 缺 finish_reason 整段重放", "tests/test_m1_integrity.py::test_m1t5_stream_without_finish_reason_fails_fast"),
    ("M1-T6/T7 envelope id 与降级丢 tool_calls", "tests/test_m1_integrity.py::test_m1t6_and_t7_envelope_roundtrip"),
    ("M1-T6 缓存记账（Anthropic usage）", "tests/test_anthropic_provider.py::test_response_maps_usage_and_tool_use"),
    ("M1-T3/T5 responses 流式往返", "tests/test_responses_streaming.py"),
)


def main() -> int:
    node_ids = [node for _, node in PROBE_TARGETS]
    print(f"reliability probe: {len(node_ids)} M1 targets under {REPO_ROOT}")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *node_ids, "-q", "--no-header"],
        cwd=str(REPO_ROOT),
    )
    if result.returncode == 0:
        print("reliability probe: PASS (all M1 defects stay fixed)")
    else:
        print(f"reliability probe: FAIL (exit {result.returncode}) — an M1 defect regressed")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
