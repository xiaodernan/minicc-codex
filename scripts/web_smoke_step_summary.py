"""Report harness failures with their actual coverage in the CI job summary."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from web_smoke_verdict import (  # noqa: E402
    HARNESS_BROWSER_MISSING_CODE,
    HARNESS_CODE,
    HARNESS_LOST_CODE,
    harness_absent,
    harness_browser_missing,
    harness_lost,
)


def render_summary(step_name: str, sentence: str, *, heading: str, code: str, advice: str) -> str:
    return (
        f"### {step_name}: {heading}\n\n"
        f"{sentence}\n\n"
        f"The step named `{code}`. {advice}\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report a harness failure in the job summary.")
    parser.add_argument("--exit-code", type=int, required=True, dest="exit_code")
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--step-name", default="Web smoke")
    args = parser.parse_args(argv)
    if not args.log.is_file():
        # An always() reporter must not fail an already-failing job for lack of evidence.
        return 0
    log = args.log.read_text(encoding="utf-8", errors="replace")
    classifications = (
        (
            harness_absent(args.exit_code, log),
            "no harness - zero tests ran",
            HARNESS_CODE,
            "Check that the web server bound its port before treating this step's result as a statement about the product.",
        ),
        (
            harness_lost(args.exit_code, log),
            "harness lost - partial coverage",
            HARNESS_LOST_CODE,
            "The suite ran partway; restart the web server and re-run rather than reading this step as a product verdict.",
        ),
        (
            harness_browser_missing(args.exit_code, log),
            "browser missing - no browser assertions ran",
            HARNESS_BROWSER_MISSING_CODE,
            "Install Chromium with `npx playwright install chromium` and re-run; static assertions do not replace browser coverage.",
        ),
    )
    for sentence, heading, code, advice in classifications:
        if sentence is None:
            continue
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        with args.summary.open("a", encoding="utf-8") as handle:
            handle.write(render_summary(
                args.step_name,
                sentence,
                heading=heading,
                code=code,
                advice=advice,
            ))
        break
    return 0


if __name__ == "__main__":
    sys.exit(main())
