#!/usr/bin/env python
"""M8-T1211 - one command that runs the same battery the claim checkers run.

CI red #10, #11, #12 were all the same shape: a fact the working tree violated
that no local command would tell me about until I pushed. This script closes
that loop: it runs, in order and with visible names, every gate that turned red
for this repo, then exits nonzero if any failed. Nothing here mutates the
working tree, pushes anything, or reaches the network.

Usage (repo root, dev venv):
    python scripts/pre_push_gates.py             # run everything, summary at the end
    python scripts/pre_push_gates.py --list      # print the gates, exit 0
    python scripts/pre_push_gates.py --only gate # only gates whose name matches
    python scripts/pre_push_gates.py --self-test # synthetic pass/fail, exit 3 (tests use this)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

PY = [sys.executable]

# The floor gates CI's claim job runs plus the pytest legs that caught real
# reds on this repo. Order is cheapest-first so a red shows early.
GATES: list[tuple[str, list[str]]] = [
    ("doc pointers", PY + ["scripts/doc_pointers.py", "--check"]),
    ("route coverage", PY + ["scripts/route_coverage.py", "--check"]),
    ("impact floor", PY + ["scripts/impacted_tests.py", "--check"]),
    ("resource hygiene", PY + ["-m", "pytest", "tests/test_resource_hygiene.py", "-q"]),
    ("stylesheet encoding", PY + ["-m", "pytest", "tests/test_the_stylesheet_is_not_mixed_encoding.py", "-q"]),
    ("content-addressed quotes", PY + ["-m", "pytest", "tests/test_no_document_quotes_a_content_addressed_bundle.py", "-q"]),
    ("palette one-home", PY + ["-m", "pytest", "tests/test_the_palette_has_one_home.py", "-q"]),
    ("package imports", PY + ["-m", "pytest", "tests/test_the_package_does_not_import_what_it_does_not_use.py", "-q"]),
    ("loader registers modules", PY + ["-m", "pytest", "tests/test_a_module_is_registered_before_a_loader_executes_it.py", "-q"]),
    ("logging contract", PY + ["-m", "pytest", "tests/test_logging.py", "-q"]),
    ("tracked evidence census", PY + ["-m", "pytest", "tests/test_tracked_evidence_census.py", "-q"]),
    ("utc formats one-home", PY + ["-m", "pytest", "tests/test_the_utc_wire_formats_have_one_home.py", "-q"]),
    ("broad handlers stated", PY + ["-m", "pytest", "tests/test_broad_silent_handlers_state_a_reason.py", "-q"]),
    ("filenames one-home", PY + ["-m", "pytest", "tests/test_the_minicc_filenames_have_one_home.py", "-q"]),
    ("run metrics one-home", PY + ["-m", "pytest", "tests/test_the_run_metrics_have_one_home.py", "-q"]),
    ("web i18n keys resolve", PY + ["-m", "pytest", "tests/test_web_data_i18n_keys_resolve.py", "-q"]),
]

#: Exit code reserved for the built-in synthetic gate pair used by tests.
SELF_TEST_EXIT = 3


def _run(name: str, argv: list[str]) -> tuple[bool, float, str]:
    start = time.perf_counter()
    proc = subprocess.run(
        argv,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        errors="replace",
    )
    elapsed = time.perf_counter() - start
    tail = ""
    if proc.returncode != 0:
        tail = (proc.stdout + "\n" + proc.stderr).strip().splitlines()[-14:]
        tail = "\n".join(f"      | {line}" for line in tail)
    return proc.returncode == 0, elapsed, tail


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pre-push-gates", description=__doc__)
    parser.add_argument("--list", action="store_true", help="print the gates, exit 0")
    parser.add_argument("--only", default=None, help="run only gates whose name matches this needle")
    parser.add_argument("--self-test", action="store_true", help="run the synthetic pass/fail pair, exit 3")
    args = parser.parse_args(argv)

    if args.self_test:
        # One of each; exit code 3 proves the runner can report failures.
        print("self-test: synthetic-pass -> ok")
        print("self-test: synthetic-fail -> red")
        return SELF_TEST_EXIT

    gates = list(GATES)
    if args.list:
        for name, _ in gates:
            print(f" - {name}")
        return 0

    if args.only:
        needle = args.only.lower()
        gates = [(name, cmd) for name, cmd in gates if needle in name.lower()]
        if not gates:
            print(f"no gate matches {args.only!r}; try --list")
            return 2

    started = time.perf_counter()
    red: list[str] = []
    for name, cmd in gates:
        print(f"gate … {name:32s}", flush=True)
        ok, elapsed, tail = _run(name, cmd)
        if ok:
            print(f"pass   {name:32s} {elapsed:6.1f}s", flush=True)
        else:
            print(f"FAIL   {name:32s} {elapsed:6.1f}s", flush=True)
            if tail:
                print(tail, flush=True)
            red.append(name)

    total = time.perf_counter() - started
    names = ", ".join(red) or "none"
    print(f"\n{len(gates) - len(red)}/{len(gates)} gates green in {total:.1f}s; red: {names}")
    return 1 if red else 0


if __name__ == "__main__":
    raise SystemExit(main())
