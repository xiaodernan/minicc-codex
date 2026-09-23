"""Gates for the tool that measures M4-3's HTTP route coverage.

M4-3 says "POST /api/* routes are covered by Python tests". For three audit
batches that number was recorded as unmeasurable; `coverage[toml]` then landed in
the dev extra and a percentage appeared: "dispatch sites GET 20/20, POST 14/14".

Two things were wrong with that evidence, and both are what this file guards:

1. The measurement lived in a scratch file outside the repository, so nobody
   reproducing M4-3 from a clean checkout could recompute the headline number -
   the roadmap's own "the figure is reproducible" was unverified.
2. It asked whether each route's *comparison line* executed (metric A). On a flat
   ``if path == ...: return`` chain that is satisfied by a single request to the
   last route, because every comparison above it runs on the way down. Measured,
   not asserted: one ``POST /api/nope`` gives A = 14/14 = 100% and B = 0/14 = 0%.

So the committed tool reports A and B separately and gates on B ("did a request
ever enter this route's branch"), and these tests keep the tool itself honest:
its readers must see every dispatch shape, its floors must fire when the
denominator shrinks, and the documented command must reproduce the number.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "route_coverage.py"


def _load():
    spec = importlib.util.spec_from_file_location("minicc_route_coverage", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # scripts/ is not a package, so this is an out-of-tree import; @dataclass(slots=...)
    # resolves annotations through sys.modules, so register before executing.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


rc = _load()

#: A dispatcher in the shape webserver.py actually has: a flat if/return chain, so a
#: request for the last route walks past every earlier comparison.
_MINI_DISPATCHER = '''
class Handler:
    def do_POST(self):
        if path == "/api/a":
            self.handle_a()
            return
        if path.startswith("/api/b/") and path.endswith("/events"):
            self.stream_b()
            return
        if path.endswith("/cancel") and path.startswith("/api/b/"):
            self.cancel_b()
            return
        if path == "/api/elsewhere":
            self.other()
            return
        self.not_found()

    def do_GET(self):
        if path == "/api/a":
            self.read_a()
            return

    def do_DELETE(self):
        if path == "/api/a":
            self.delete_a()
            return
'''


def _mini_sites():
    return rc.dispatch_sites(_MINI_DISPATCHER)


def _shapes(sites) -> set[tuple[str, frozenset[str]]]:
    """(verb, route parts) - order-insensitive, so label rendering can't break it."""
    return {(s.verb, frozenset(s.route.split())) for s in sites}


def test_the_walker_sees_every_dispatch_shape() -> None:
    """Exact match, and prefix+suffix compound tests in both operand orders.

    The first version read only ``If.test`` as one whole predicate, so a compound
    test - an ``ast.BoolOp`` - was invisible: the live denominator silently dropped
    from 34 sites to 31 while still reporting 100%.
    """
    assert _shapes(_mini_sites()) == {
        ("POST", frozenset({"/api/a"})),
        ("POST", frozenset({"/api/b/*", "*/events"})),
        ("POST", frozenset({"/api/b/*", "*/cancel"})),
        ("POST", frozenset({"/api/elsewhere"})),
        ("GET", frozenset({"/api/a"})),
    }
    # do_DELETE is not part of M4-3's surface; counting it would inflate the total.
    assert {s.verb for s in _mini_sites()} == {"GET", "POST"}


def test_a_can_be_100_percent_while_no_route_was_dispatched() -> None:
    """The load-bearing property of this whole file.

    Feed the reporter exactly the lines a single fall-through request executes -
    the comparisons, none of the bodies - and metric A still reads complete while
    metric B reads nothing. Any coverage claim built on A alone inherits that hole.
    """
    sites = _mini_sites()
    report = rc.summarize(sites, {s.compare_line for s in sites})
    post = report["POST"]
    assert post["total"] == 4
    assert post["evaluated"] == 4, "A: every comparison line ran, as a fall-through guarantees"
    assert post["entered"] == 0, "B: yet not one route body ran"
    assert len(post["missed_entry"]) == 4


def test_the_entry_metric_turns_green_only_when_a_branch_body_runs() -> None:
    sites = _mini_sites()
    target = next(s for s in sites if s.verb == "POST" and "*/events" in s.route)
    report = rc.summarize(sites, {min(target.body_lines)})
    assert report["POST"]["entered"] == 1
    assert report["POST"]["missed_entry"] == sorted(
        s.label for s in sites if s.verb == "POST" and s.label != target.label
    )


def test_one_body_line_never_satisfies_two_sibling_routes() -> None:
    """B must attribute entry to the branch that owns the line."""
    sites = _mini_sites()
    events = next(s for s in sites if "*/events" in s.route)
    other = next(s for s in sites if "*/cancel" in s.route)
    satisfied = {s.label for s in sites if min(events.body_lines) in s.body_lines}
    assert satisfied == {events.label}
    assert min(events.body_lines) not in other.body_lines


def test_the_live_inventory_exposes_the_surface_the_number_is_quoted_against() -> None:
    source = (REPO_ROOT / "minicc" / "webserver.py").read_text(encoding="utf-8")
    sites = rc.dispatch_sites(source)
    report = rc.summarize(sites, set())
    totals = {verb: int(str(report[verb]["total"])) for verb in ("GET", "POST")}
    assert totals["GET"] >= rc.MIN_SITES["GET"], totals
    assert totals["POST"] >= rc.MIN_SITES["POST"], totals
    # The AST reader must not be blinder than a dumb line-of-text reader.
    blind = sorted(set(rc.text_predicates(source)) - rc.ast_predicates(source))
    assert blind == [], f"predicates the walker did not attribute to any site: {blind}"


def test_a_shrunken_denominator_is_reported_as_a_problem_not_a_percentage() -> None:
    """If routing stops comparing against `path`, the walker returns nothing.

    100% of an empty list is the failure mode the floors exist to catch, so the
    guard has to fire before anyone reads the number beside it.
    """
    problems = rc.inventory_problems(rc.summarize([], set()))
    assert len(problems) == 2
    assert any("GET" in p for p in problems) and any("POST" in p for p in problems)
    blind = rc.inventory_problems(rc.summarize(_mini_sites(), set()), blind_spots=[(99, "/api/hidden")])
    assert any("/api/hidden" in p for p in blind)


def test_the_documented_command_reproduces_the_number() -> None:
    """`python scripts/route_coverage.py --check` is the reproducibility claim.

    It runs the selected tests under coverage into a throwaway data file, so this
    exercises the whole M4-3 measurement end to end - the only proof that a clean
    checkout can recompute the figure the roadmap quotes.
    """
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    for verb in ("GET", "POST"):
        assert f"{verb}: A(compare-line-ran)" in output, output
    assert "NOT ENTERED" not in output, output
    assert "INVENTORY PROBLEM" not in output, output
