# -*- coding: utf-8 -*-
"""Forge facts — assemble an honest fact sheet for the almanac forge from the repo itself.

The forge (``scripts/almanac_forge.py``) takes a plain-text FACTS file and nothing
else. This script builds that file from real, re-checkable artifacts so chapters
are never written against vibes:

- ``git log`` (subprocess, last N commits of HEAD) — real commit subjects and dates;
- ``docs/latest.json`` — the machine-generated fact pack the fact-pack bot commits
  after every push (head, commit counter, almanac count, roadmap lines);
- ``docs/CACHE_AFFINITY_MATRIX.md`` — regex-extracted measurement lines that mention
  the frozen anchor numbers (97.6 / 71.6 / 48.0 / 150 s / 60 s / 8,362);
- ``docs/LOAD_TESTING.md`` — regex-extracted pressure lines (59,070 / 33,600 / 400/400);
- ``minicc-cloud/pom.xml`` — the Maven module list.

Everything the script cannot read is reported as a gap line ("(fact pack missing)")
instead of being filled in with a plausible number. Never prints a secret.

Usage:
    python scripts/forge_facts.py --out docs/_facts.txt --chapter LXII

This file is exercised by ``tests/test_forge_facts.py`` against a fixture repo.
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

_CACHE_MARKERS = re.compile(r"(97\.6|71\.6|48\.0|8,362|8,566|150\s*s|150 s|60\s*s|60 s|cache-hit|hit_pct|cache_hit)")
_PRESSURE_MARKERS = re.compile(r"(59,070|33,600|14,280|400/400|25,470)")
_MODULE_RE = re.compile(r"<module>([^<]+)</module>")


def _bounded(lines, limit=24, width=200):
    out = []
    for line in lines[:limit]:
        line = line.rstrip()
        if len(line) > width:
            line = line[: width - 1] + "…"
        out.append(line)
    return out


def _git_log(repo: Path, count: int = 10) -> list[str]:
    try:
        raw = subprocess.check_output(
            ["git", "log", f"-n", str(count), "--pretty=format:%h | %ad | %s", "--date=short"],
            cwd=str(repo),
            stderr=subprocess.DEVNULL,
        ).decode("utf-8", errors="replace")
        return [ln for ln in raw.splitlines() if ln.strip()]
    except Exception:
        # Deliberate boundary: git is only a *data source* for the fact sheet.
        # If a repo has no commits yet (or git is unavailable), the section
        # degrades to the honest "(git log unavailable)" marker instead of
        # killing the whole fact sheet — the model is told to say so.
        return []


def generate_facts(repo: Path, *, chapter: str = "?") -> str:
    repo = Path(repo)
    sections: list[str] = []

    sections.append(f"# Fact pack for Almanac {chapter} — generated {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n")

    # 1) recent commits
    commits = _git_log(repo, 10)
    sections.append("## Recent commits (git log, verbatim)\n" + ("\n".join(_bounded(commits)) or "(git log unavailable)") + "\n")

    # 2) machine fact pack
    pack_path = repo / "docs" / "latest.json"
    try:
        pack = json.loads(pack_path.read_text(encoding="utf-8"))
        keep = {k: pack.get(k) for k in ("head", "generated_at", "total_commits", "roadmap_batches",
                                         "almanac_chapters", "test_files", "tracked_files", "roadmap_lines")}
        sections.append("## Fact pack (docs/latest.json, verbatim fields)\n" + json.dumps(keep, ensure_ascii=False, indent=2) + "\n")
    except Exception:
        sections.append("## Fact pack (docs/latest.json, verbatim fields)\n(fact pack missing)\n")

    # 3) spring cloud modules, straight out of pom.xml
    pom = repo / "minicc-cloud" / "pom.xml"
    try:
        modules = _MODULE_RE.findall(pom.read_text(encoding="utf-8"))
        sections.append("## Spring Cloud modules (minicc-cloud/pom.xml <modules>)\n" + "\n".join(modules) + "\n")
    except Exception:
        sections.append("## Spring Cloud modules (minicc-cloud/pom.xml <modules>)\n(pom missing)\n")

    # 4) measurement lines from the cache matrix
    matrix = repo / "docs" / "CACHE_AFFINITY_MATRIX.md"
    hits: list[str] = []
    try:
        for raw in matrix.read_text(encoding="utf-8").splitlines():
            line = raw.rstrip()
            if _CACHE_MARKERS.search(line):
                hits.append(line)
        sections.append("## Cache-affinity measurements (regex-extracted from docs/CACHE_AFFINITY_MATRIX.md)\n" + "\n".join(_bounded(hits, 24, 240)) + "\n")
    except Exception:
        sections.append("## Cache-affinity measurements (regex-extracted from docs/CACHE_AFFINITY_MATRIX.md)\n(cache matrix missing)\n")

    # 5) pressure lines from the load-testing ledger
    load = repo / "docs" / "LOAD_TESTING.md"
    phits: list[str] = []
    try:
        for raw in load.read_text(encoding="utf-8").splitlines():
            line = raw.rstrip()
            if _PRESSURE_MARKERS.search(line):
                phits.append(line)
        sections.append("## Pressure-test ledger (regex-extracted from docs/LOAD_TESTING.md)\n" + "\n".join(_bounded(phits, 16, 240)) + "\n")
    except Exception:
        sections.append("## Pressure-test ledger (regex-extracted from docs/LOAD_TESTING.md)\n(load-testing ledger missing)\n")

    header = [
        "FACTS for the almanac forge — every line below is either verbatim from the repo,",
        "regex-extracted from a tracked document, or explicitly marked 'missing'. Nothing",
        "between sections is embellished; if a section is missing, the model must say so.",
        f"Target chapter: {chapter}. Keep the same measured numbers when writing prose.\n",
    ]
    return "\n".join(header + sections) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="forge-facts")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--chapter", required=True)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args(argv)

    text = generate_facts(args.repo, chapter=args.chapter)
    args.out.write_text(text, encoding="utf-8")
    print(f"forge facts written: {args.out} ({len(text.encode('utf-8'))} bytes, chapter {args.chapter})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
