"""M8-T1306: a web-smoke step that tested nothing says so in the job summary.

The smoke exits 3 naming HARNESS_UNREACHABLE when its own server is absent, and
``web_smoke_verdict`` can tell that from a caught or missed mutation. But CI only
showed a red step: a human had to open the log to learn that no assertion ran at
all. This helper appends one clearly-marked block to ``$GITHUB_STEP_SUMMARY`` so
"this step tested nothing, go check the web server" is visible on the job page.

It is an ``if: always()`` reporter: it never changes the step's outcome (always
exits 0) and it reuses the verdict's detector instead of growing a second copy.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from web_smoke_verdict import HARNESS_CODE, harness_absent  # noqa: E402


def render_summary(step_name: str, sentence: str) -> str:
    return (
        f"### {step_name}: no harness - zero tests ran\n\n"
        f"{sentence}\n\n"
        f"The smoke named `{HARNESS_CODE}`. Check that the web server bound its port "
        f"before treating this step's result as a statement about the product.\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report a harness-absent smoke step in the job summary.")
    parser.add_argument("--exit-code", type=int, required=True, dest="exit_code")
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--step-name", default="Web smoke")
    args = parser.parse_args(argv)
    if not args.log.is_file():
        # No log means this reporter has nothing honest to add; it must not fail
        # an already-failing (or passing) job for lack of evidence.
        return 0
    log = args.log.read_text(encoding="utf-8", errors="replace")
    absent = harness_absent(args.exit_code, log)
    if absent is None:
        return 0
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    with args.summary.open("a", encoding="utf-8") as handle:
        handle.write(render_summary(args.step_name, absent))
    return 0


if __name__ == "__main__":
    sys.exit(main())
