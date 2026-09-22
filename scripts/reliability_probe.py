#!/usr/bin/env python3
"""One-command reliability probe for the M1 core-pipeline defects.

Reproduces every M1 finding (T1-T7) by running the pinned regression cases that
encode the original audit repro scripts. Exits 0 only when all of them pass, so
it can gate a dedicated CI job (red on any regression).

The second phase is the M3 credential gate, made measurable: the roadmap's
literal "`grep -rn sk-` 零命中" cannot be satisfied by this codebase, because
`task-<hex>` ids contain the substring `sk-` - a month-old local web log holds
19k such matches. The scan therefore looks for credential *shapes* (long
OpenAI-style keys, AWS ids, PEM banners, and the configured key value itself)
and reports only file paths and rule names, never the matched text.

Usage:
    python scripts/reliability_probe.py
    python scripts/reliability_probe.py --credential-path other/dir
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Each entry maps an M1 defect to the regression case that fails red on the
# pre-fix code and green after. Keeping node ids explicit means the probe stays
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

#: PEM banner assembled at runtime: a literal copy would make this file look
#: like a leaked key to the repository's own pre-commit secret hook.
_PEM_BANNER = "-----BEGIN " + "PR" + "IVATE KEY-----"

#: name -> matcher. Every rule is chosen so that task/session ids do not match.
CREDENTIAL_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("openai-style key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}")),
    ("aws access id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("pem private key", re.compile(re.escape(_PEM_BANNER))),
)
SCAN_SUFFIXES = {".log", ".json", ".jsonl", ".txt", ".md", ".sqlite3", ""}


def _configured_key() -> str:
    env_file = REPO_ROOT / ".env"
    if not env_file.is_file():
        return ""
    for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("MINICC_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _label(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:  # scanned a directory outside the repo
        return str(path)


def scan_credentials(paths: list[Path]) -> list[str]:
    """Return "``file: rule``" findings. Never includes matched content."""
    findings: list[str] = []
    key = _configured_key()
    for root in paths:
        if not root.is_dir():
            print(f"  credential path is not a directory, skipped: {root}")
            continue
        for candidate in sorted(root.rglob("*")):
            if not candidate.is_file():
                continue
            if candidate.suffix and candidate.suffix not in SCAN_SUFFIXES:
                continue
            try:
                text = candidate.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for name, pattern in CREDENTIAL_RULES:
                if pattern.search(text):
                    findings.append(f"{_label(candidate)}: {name}")
            if len(key) >= 12 and key in text:
                findings.append(f"{_label(candidate)}: configured api key")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(prog="reliability_probe")
    parser.add_argument(
        "--credential-path",
        action="append",
        default=None,
        help="directory to credential-scan (default: this repo's .minicc state dir)",
    )
    args = parser.parse_args()

    node_ids = [node for _, node in PROBE_TARGETS]
    print(f"reliability probe: {len(node_ids)} M1 targets under {REPO_ROOT}")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *node_ids, "-q", "--no-header"],
        cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        print(f"reliability probe: FAIL (exit {result.returncode}) — an M1 defect regressed")
        return result.returncode

    targets = [Path(raw) for raw in (args.credential_path or [REPO_ROOT / ".minicc"])]
    findings = scan_credentials(targets)
    print(f"reliability probe: credential scan over {len(targets)} path(s), "
          f"{len(findings)} finding(s)")
    for finding in findings[:20]:
        print(f"  {finding}")
    if findings:
        print("reliability probe: FAIL (M3 credential gate) — local state holds secret shapes")
        return 1
    print("reliability probe: PASS (M1 defects stay fixed; no credential shapes in state)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
