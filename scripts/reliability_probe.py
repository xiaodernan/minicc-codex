#!/usr/bin/env python3
"""One-command reliability probe for the M1 core-pipeline defects.

Reproduces every M1 finding (T1-T7) by running the pinned regression cases that
encode the original audit repro scripts. Exits 0 only when all of them pass, so
it can gate a dedicated CI job (red on any regression).

The second phase is the M3 credential gate, made measurable: the roadmap's
literal "`grep -rn sk-` 零命中" cannot be satisfied by this codebase, because
`task-<hex>` ids contain the substring `sk-` - a month-old local web log holds
19k such matches. The scan therefore looks for credential *shapes* and reports
only file paths and rule names, never the matched text.

Since M8-T528 the gate's rule table is *derived* from the product's own
redaction table (``minicc.tools.registry``): the CI gate may not read narrower
than what minicc itself masks. Two gate-only extras stay on top of the product
table: the bare PEM banner (the product rule needs a closed ``BEGIN..END``
block; an unclosed banner is still a leak shape) and the configured
``MINICC_API_KEY`` value itself, read through the product's own ``.env`` loader
(``config._parse_env_file``) so it sees every spelling the product sees.

A finding whose matched value already occurs verbatim in a git-tracked file is
classified *published*: it is a copy of something the repository already
discloses (the audit doc's own illustration text, for example), reported as
counts and paths, never content, and it does not fail the gate. Every verdict
line reports how many files were actually read, so a scan over an absent state
directory can never look like a clean scan over hundreds of files.

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
sys.path.insert(0, str(REPO_ROOT))

from minicc.config import ConfigError, _parse_env_file  # noqa: E402
from minicc.tools import registry  # noqa: E402

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

#: The product marks its redactions ``[REDACTED:llm_api_key]`` and
#: ``[REDACTED PRIVATE KEY]``. The gate names each rule after the marker token,
#: so a rule the product renames or adds renames or adds a gate rule with it.
_MARKER = re.compile(r"\[REDACTED[: ]([a-z_]+)\]")


def _product_rules() -> tuple[tuple[str, re.Pattern[str]], ...]:
    rules: list[tuple[str, re.Pattern[str]]] = []
    for pattern, replacement in registry._REDACT_RULES:
        found = _MARKER.search(replacement)
        rules.append((found.group(1) if found else "private_key_block", pattern))
    return tuple(rules)


#: The CI credential gate reads the product's own redaction table, plus one
#: gate-only extra: the bare banner, which the product's closed-block rule
#: cannot see.
CREDENTIAL_RULES: tuple[tuple[str, re.Pattern[str]], ...] = _product_rules() + (
    ("pem_banner", re.compile(re.escape(_PEM_BANNER))),
)

SCAN_SUFFIXES = {".log", ".json", ".jsonl", ".txt", ".md", ".sqlite3", ""}


def _configured_key(env_path: Path | None = None) -> str:
    """Read the configured key the way the product reads it, so every loader
    spelling (``export`` prefix, spaces around ``=``, indentation, quoting,
    inline comments) is visible to the configured-key rule too."""
    try:
        values = _parse_env_file(env_path or (REPO_ROOT / ".env"))
    except ConfigError:
        # The error message quotes the offending line - never print it.
        print("  credential phase: .env unreadable (ConfigError, line content withheld); "
              "configured-key rule disabled this run")
        return ""
    return values.get("MINICC_API_KEY", "")


def _label(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:  # scanned a directory outside the repo
        return str(path)


_TRACKED: list[str] | None = None


def _published_texts() -> list[str]:
    """Contents of every git-tracked file; computed once, only when findings exist."""
    global _TRACKED
    if _TRACKED is None:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=str(REPO_ROOT), capture_output=True)
        names = [raw.decode("utf-8", "replace") for raw in out.stdout.split(b"\0") if raw]
        texts: list[str] = []
        for name in names:
            try:
                texts.append((REPO_ROOT / name).read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
        _TRACKED = texts
    return _TRACKED


def _is_published(value: str, published_texts: list[str]) -> bool:
    return any(value in text for text in published_texts)


def scan_credentials(
    paths: list[Path],
    published_provider=None,
) -> tuple[list[str], list[str], int]:
    """Return ``(leak, published, files_read)``. Findings are "``file: rule``"
    strings; matched content never reaches them.

    A rule's finding in a file is *published* only when every value that rule
    matched there occurs verbatim in a tracked file; one un-published value
    makes the whole finding a leak."""
    leak: list[str] = []
    published: list[str] = []
    files_read = 0
    raw: list[tuple[Path, str, list[str]]] = []
    key = _configured_key()
    for root in paths:
        if not root.is_dir():
            print(f"  credential target is not a directory, skipped: {root}")
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
            files_read += 1
            for name, pattern in CREDENTIAL_RULES:
                values = [m.group(0) for m in pattern.finditer(text)]
                if values:
                    raw.append((candidate, name, values))
            if len(key) >= 12 and key in text:
                raw.append((candidate, "configured_api_key", [key]))
    published_texts = published_provider() if (raw and published_provider is not None) else None
    for candidate, name, values in raw:
        finding = f"{_label(candidate)}: {name}"
        if published_texts is not None and all(_is_published(v, published_texts) for v in values):
            published.append(finding)
        else:
            leak.append(finding)
    return leak, published, files_read


def credential_phase(targets: list[Path]) -> int:
    """Run the credential scan and print an honest verdict; return the exit code."""
    leak, published, files_read = scan_credentials(targets, published_provider=_published_texts)
    print(f"reliability probe: credential scan: {files_read} file(s) read over {len(targets)} target(s), "
          f"{len(leak)} leak finding(s), {len(published)} published finding(s)")
    if files_read == 0:
        print("  no file was read; a scan over zero files certifies nothing about local state")
        for target in targets:
            print(f"  target: {target} ({'present' if target.is_dir() else 'ABSENT'})")
    for finding in leak[:20]:
        print(f"  leak: {finding}")
    for finding in published[:20]:
        print(f"  published: {finding} (value occurs in tracked files; disclosure, not a leak)")
    if leak:
        print("reliability probe: FAIL (M3 credential gate) — local state holds secret shapes")
        return 1
    if files_read == 0:
        print("reliability probe: PASS (M1 defects stay fixed; credential scan read zero files - "
              "nothing was certified about local state)")
    else:
        print("reliability probe: PASS (M1 defects stay fixed; no un-published credential shapes in state)")
    return 0


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
    return credential_phase(targets)


if __name__ == "__main__":
    raise SystemExit(main())
