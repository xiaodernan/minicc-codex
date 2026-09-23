#!/usr/bin/env python
"""Measure how much of the HTTP dispatch surface the Python tests actually reach.

M4-3's criterion is "POST /api/* routes covered by Python tests". Two different
questions hide behind that sentence, and only one of them is worth reporting:

    A  evaluate-coverage  did the dispatcher *compare* against this route path
    B  entry-coverage     did a request ever *enter* this route's branch body

A is what a naive line-coverage reading gives, and it is gameable on this shape
of code: ``do_GET``/``do_POST`` are flat ``if path == "/api/x": ... return``
chains, so a single request to the last route in the chain runs every comparison
above it. A can report 100% while almost no route was ever dispatched.

B is the criterion: a statement inside that branch's body executed, which cannot
happen unless control entered the branch. This script reports both, gates on B,
and refuses to trust the number when the inventory itself looks broken.

Usage (repo root, dev venv with `pip install -e ".[dev]"`):

    python scripts/route_coverage.py                     # run the selection, report
    python scripts/route_coverage.py --check             # exit 1 unless all B == 100%
    python scripts/route_coverage.py --tests tests/test_http_surface.py
    python scripts/route_coverage.py --reuse             # reuse the root .coverage

Exit code 0 means the measurement ran and the inventory is intact; ``--check``
additionally requires every dispatch site to be entered by the selected tests.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WEBSERVER = REPO_ROOT / "minicc" / "webserver.py"

#: The selection M4-3's number is quoted against. Deliberately narrow: a figure
#: measured over the whole suite says "something somewhere touched this", which
#: is the weakening this script exists to prevent.
DEFAULT_TESTS = (
    "tests/test_http_surface.py",
    "tests/test_http_route_inventory.py",
)

#: Floors for the inventory itself. If routing ever stops comparing against
#: ``path`` (a table, a decorator, a regex) the walker returns nothing, and
#: 100% of an empty list is exactly how a dead measurement reports success.
MIN_SITES = {"GET": 15, "POST": 10}

_VERBS = {"do_GET": "GET", "do_POST": "POST"}


@dataclass(frozen=True, slots=True)
class DispatchSite:
    verb: str
    route: str
    #: line of the ``path == "/api/x"`` comparison - metric A reads this
    compare_line: int
    #: lines inside the branch body - metric B needs one of these to have run
    body_lines: frozenset[int] = field(default_factory=frozenset)

    @property
    def label(self) -> str:
        return f"{self.verb} {self.route} (line {self.compare_line})"


def _route_of(node: ast.AST) -> tuple[str, str] | None:
    """Render one ``path`` predicate as ``(label, raw literal)``, or None.

    A suffix test such as ``path.endswith("/resume")`` is kept for the label but
    carries no ``/api/`` prefix, so it can never qualify a branch as a route on its
    own - see :func:`dispatch_sites`.
    """
    if (
        isinstance(node, ast.Compare)
        and isinstance(node.left, ast.Name)
        and node.left.id == "path"
        and len(node.comparators) == 1
    ):
        comparator = node.comparators[0]
        if isinstance(comparator, ast.Constant) and isinstance(comparator.value, str):
            return comparator.value, comparator.value
        return None
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"startswith", "endswith"}
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "path"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    ):
        literal = node.args[0].value
        # A compound test like `path.endswith("/resume") and path.startswith("/api/tasks/")`
        # splits its two halves across the BoolOp; keep which side of the path each
        # literal anchors to, so the label still reads as one route.
        return (f"{literal}*" if node.func.attr == "startswith" else f"*{literal}"), literal
    return None


def _test_predicates(test: ast.expr) -> list[tuple[int, str, str]]:
    """Every ``path`` predicate inside a condition, including BoolOp operands.

    Reading only ``If.test`` as one whole predicate is what made the first version of
    this walker blind: ``if path.startswith("/api/tasks/") and path.endswith("/events")``
    is an ``ast.BoolOp``, so three dispatch sites in ``webserver.py`` silently left the
    denominator - and a smaller denominator is how 100% gets reported for less surface.
    """
    found: list[tuple[int, str, str]] = []
    for node in ast.walk(test):
        rendered = _route_of(node)
        if rendered is not None:
            found.append((node.lineno, rendered[0], rendered[1]))
    found.sort()
    return found


def _body_lines(body: list[ast.stmt]) -> frozenset[int]:
    lines: set[int] = set()
    for stmt in body:
        for child in ast.walk(stmt):
            if isinstance(child, ast.stmt):
                lineno = getattr(child, "lineno", None)
                if lineno is not None:
                    lines.add(lineno)
    return frozenset(lines)


def _route_branches(source_text: str):
    """Yield ``(verb, predicates, body)`` for each qualifying route branch."""
    tree = ast.parse(source_text)
    for func in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)):
        verb = _VERBS.get(func.name)
        if verb is None:
            continue
        for node in ast.walk(func):
            if not isinstance(node, ast.If):
                continue
            predicates = _test_predicates(node.test)
            if not any(raw.startswith("/api/") for _, _, raw in predicates):
                continue
            yield verb, predicates, node.body


def dispatch_sites(source_text: str) -> list[DispatchSite]:
    """Every route branch the dispatcher owns, with its comparison and body lines."""
    sites = [
        DispatchSite(
            verb=verb,
            route=" ".join(label for _, label, _ in predicates),
            compare_line=min(line for line, _, _ in predicates),
            body_lines=_body_lines(body),
        )
        for verb, predicates, body in _route_branches(source_text)
    ]
    sites.sort(key=lambda s: (s.verb, s.compare_line))
    return sites


def ast_predicates(source_text: str) -> set[tuple[int, str]]:
    """The /api/ predicates the AST attributes to a route branch, as (line, literal)."""
    return {
        (line, raw)
        for _, predicates, _ in _route_branches(source_text)
        for line, _, raw in predicates
        if raw.startswith("/api/")
    }


def summarize(sites: list[DispatchSite], executed: set[int]) -> dict[str, dict[str, object]]:
    """Compute A (comparison ran) and B (branch body entered) per verb."""
    report: dict[str, dict[str, object]] = {}
    for verb in ("GET", "POST"):
        group = [s for s in sites if s.verb == verb]
        evaluated = {s.label for s in group if s.compare_line in executed}
        entered = {s.label for s in group if s.body_lines & executed}
        report[verb] = {
            "total": len(group),
            "evaluated": len(evaluated),
            "entered": len(entered),
            "missed_entry": sorted(s.label for s in group if s.label not in entered),
            "missed_evaluate": sorted(s.label for s in group if s.label not in evaluated),
        }
    return report


def inventory_problems(report: dict[str, dict[str, object]], *, blind_spots: list[tuple[int, str]] = ()) -> list[str]:
    problems: list[str] = []
    for verb, floor in MIN_SITES.items():
        total = int(str(report[verb]["total"]))
        if total < floor:
            problems.append(
                f'{verb}: only {total} dispatch sites found (floor {floor}). The dispatcher '
                f'no longer matches the `path == "/api/..."` idiom this walker reads, so the '
                f'percentage beside it is not measuring the HTTP surface.'
            )
    for line, literal in blind_spots:
        problems.append(
            f"webserver.py:{line} compares `path` against {literal!r} in plain text but no "
            f"dispatch site claims it - the AST walker grew a blind spot, so the denominator "
            f"below is smaller than the real surface."
        )
    return problems


_TEXT_PREDICATE = re.compile(
    r'path\s*(?:==|!=|\.startswith\(|\.endswith\()\s*[\'"](/api/[^\'"]*)[\'"]'
)


def text_predicates(source_text: str) -> list[tuple[int, str]]:
    """A deliberately dumb second reader of the same surface.

    It only knows how to find ``path == "/api/x"``, ``path.startswith("/api/x")`` and
    ``path.endswith("/api/x")`` on a line of ``do_GET``/``do_POST``. Its job is not to
    replace the AST walker - it is to disagree with it when the walker grows a blind
    spot, which it did on the first run of this file (three compound tests). A single
    extraction routine cannot notice its own gaps.
    """
    tree = ast.parse(source_text)
    ranges = {
        (node.lineno, node.end_lineno or node.lineno)
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name in _VERBS
    }
    found: list[tuple[int, str]] = []
    for lineno, line in enumerate(source_text.splitlines(), start=1):
        if not any(start <= lineno <= end for start, end in ranges):
            continue
        for match in _TEXT_PREDICATE.finditer(line):
            found.append((lineno, match.group(1)))
    return found


def _coverage_json(data_file: Path, out_file: Path) -> None:
    subprocess.run(
        [sys.executable, "-m", "coverage", "json", f"--data-file={data_file}", "-o", str(out_file), "-q"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )


def _executed_lines(json_file: Path, suffix: str) -> set[int]:
    payload = json.loads(json_file.read_text(encoding="utf-8"))
    for key, entry in payload["files"].items():
        if key.replace("\\", "/").endswith(suffix):
            return set(entry.get("executed_lines", []))
    raise SystemExit(
        f"coverage data has no entry for {suffix}; files seen: {sorted(payload['files'])[:8]}"
    )


def measure(tests: tuple[str, ...], *, reuse: bool, source: str) -> tuple[list[DispatchSite], set[int]]:
    """Return (dispatch sites, lines of webserver.py executed by `tests`)."""
    sites = dispatch_sites(WEBSERVER.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="minicc-cov-") as tmp:
        tmp_path = Path(tmp)
        data_file = tmp_path / "coverage.dat"
        json_file = tmp_path / "coverage.json"
        env = {**os.environ, "COVERAGE_FILE": str(data_file), "PYTHONIOENCODING": "utf-8"}
        if reuse:
            root_data = REPO_ROOT / ".coverage"
            if not root_data.is_file():
                raise SystemExit("--reuse needs a .coverage data file at the repo root")
            shutil.copy2(root_data, data_file)
        else:
            subprocess.run(
                [sys.executable, "-m", "coverage", "run", f"--source={source}",
                 "-m", "pytest", *tests, "-q"],
                cwd=REPO_ROOT,
                check=True,
                env=env,
            )
        _coverage_json(data_file, json_file)
        executed = _executed_lines(json_file, "minicc/webserver.py")
    return sites, executed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report HTTP dispatch coverage (A: evaluated, B: entered).")
    parser.add_argument("--tests", nargs="*", default=list(DEFAULT_TESTS))
    parser.add_argument("--check", action="store_true", help="exit 1 unless every dispatch site is entered")
    parser.add_argument("--reuse", action="store_true", help="reuse the repo-root .coverage instead of running pytest")
    parser.add_argument("--source", default="minicc.webserver", help="coverage --source value")
    parser.add_argument("--only", metavar="SUBSTR", help="only list un-entered routes containing SUBSTR")
    args = parser.parse_args(argv)

    sites, executed = measure(tuple(args.tests) or DEFAULT_TESTS, reuse=args.reuse, source=args.source)
    source_text = WEBSERVER.read_text(encoding="utf-8")
    blind_spots = sorted(set(text_predicates(source_text)) - ast_predicates(source_text))
    report = summarize(sites, executed)
    problems = inventory_problems(report, blind_spots=blind_spots)
    for problem in problems:
        print(f"INVENTORY PROBLEM: {problem}")

    incomplete = False
    print(f"dispatch sites found: {len(sites)}   webserver.py lines executed: {len(executed)}")
    for verb in ("GET", "POST"):
        row = report[verb]
        total = int(str(row["total"]))
        evaluated = int(str(row["evaluated"]))
        entered = int(str(row["entered"]))
        pct_a = 100.0 * evaluated / total if total else 0.0
        pct_b = 100.0 * entered / total if total else 0.0
        print(
            f"{verb}: A(compare-line-ran)   {evaluated}/{total} = {pct_a:.1f}%"
            f"\n     B(branch-body-ran)   {entered}/{total} = {pct_b:.1f}%"
        )
        missed = [str(x) for x in row["missed_entry"]]
        if args.only:
            missed = [x for x in missed if args.only in x]
        for item in missed:
            print(f"  NOT ENTERED: {item}")
        incomplete = incomplete or entered < total
    print("A can be satisfied by one request that falls through to the end of the chain; "
          "B is the number M4-3 asks for.")
    return 1 if (problems or (incomplete and args.check)) else 0


if __name__ == "__main__":
    raise SystemExit(main())
