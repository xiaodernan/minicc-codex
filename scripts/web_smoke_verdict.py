"""M8-T534: the mutation step must name why the smoke failed, not just that it did.

``web-smoke-mutation`` runs the Playwright smoke against a server whose provider
is unreachable and expects a non-zero exit. Read that way, any failure satisfies
the gate: a missing Chromium, a web server that never bound its port, or a
syntax error in the smoke all "catch the mutation" while the product path the
gate exists to protect was never exercised.

The smoke prints ``SMOKE_FAILURE_CODE=<CODE>`` from its own product-path
assertions. This script decides, from the exit code and the captured log,
whether the failure that happened is the one the mutation injected. Only
``PRODUCT_PATH_NO_COMPLETION_VERDICT`` proves the submit -> provider -> agent ->
verifier -> completion chain ran and did not complete; every other failure is
reported as unattributed and exits non-zero.

M8-T1304 adds one more answer. A smoke now probes its own server before
launching a browser and exits 3 naming ``HARNESS_UNREACHABLE`` when nothing
answers. That step ran zero suites, which used to be explained with the same
sentence as a step that ran the wrong suite; it now says the harness was missing
and exits ``HARNESS_EXIT`` so a run that tested nothing cannot be read as either
a caught mutation or a misattributed one.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

CODE_PREFIX = "SMOKE_FAILURE_CODE="
EXPECTED_CODE = "PRODUCT_PATH_NO_COMPLETION_VERDICT"
HARNESS_CODE = "HARNESS_UNREACHABLE"
HARNESS_EXIT = 3
_CODE_LINE = re.compile(r"^" + re.escape(CODE_PREFIX) + r"([A-Z0-9_]+)\s*$", re.MULTILINE)


def failure_code(log: str) -> str | None:
    """The last failure code the smoke emitted, or None when it named no reason."""
    codes = _CODE_LINE.findall(log)
    return codes[-1] if codes else None


def codes(log: str) -> list[str]:
    """Every failure code the smoke named, in the order it named them."""
    return _CODE_LINE.findall(log)


def harness_absent(exit_code: int, log: str) -> str | None:
    """The sentence for a step that ran zero suites, or None when a suite ran.

    M8-T1304: the smoke probes ``/api/health`` before it launches a browser, and
    names ``HARNESS_CODE`` when nothing answers. No assertion of any suite -
    including the product path this step exists to protect - was exercised, so
    the code wins over any product code that follows it: a run that never reached
    its own server has no standing to report what the product did.
    """
    if HARNESS_CODE not in codes(log):
        return None
    return (
        f"harness absent: the smoke never reached its own web server and named {HARNESS_CODE} "
        f"(the smoke exited {exit_code}); zero suites ran, so this step tested nothing and can "
        "report neither a caught mutation nor a missed one"
    )


def decide(exit_code: int, log: str) -> tuple[bool, str]:
    """Whether this run caught the injected mutation, and the reason either way."""
    if exit_code == 0:
        return False, (
            "MUTATION NOT CAUGHT: the smoke passed against an unreachable provider; "
            "its product-path assertions no longer gate the chain"
        )
    code = failure_code(log)
    if code == EXPECTED_CODE:
        return True, f"mutation caught: {code}"
    if code is None:
        return False, (
            f"mutation not attributed: the smoke exited {exit_code} without naming a failure "
            "code; an infrastructure error (browser, server, syntax) must not read as a caught mutation"
        )
    return False, f"mutation not attributed: the smoke failed with {code}, not {EXPECTED_CODE}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Decide whether the web-smoke mutation was caught.")
    parser.add_argument("--exit-code", type=int, required=True, dest="exit_code")
    parser.add_argument("--log", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.log.is_file():
        print(f"mutation not attributed: the smoke log {args.log} was never written")
        return 1
    log = args.log.read_text(encoding="utf-8", errors="replace")
    absent = harness_absent(args.exit_code, log)
    if absent is not None:
        print(absent)
        return HARNESS_EXIT
    caught, verdict = decide(args.exit_code, log)
    print(verdict)
    return 0 if caught else 1


if __name__ == "__main__":
    sys.exit(main())
