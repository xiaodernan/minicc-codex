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

import ast
import importlib.util
import os
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
        env=dict(os.environ, PYTHONIOENCODING="utf-8"),
        timeout=900,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    for verb in ("GET", "POST"):
        assert f"{verb}: A(compare-line-ran)" in output, output
    assert "NOT ENTERED" not in output, output
    assert "INVENTORY PROBLEM" not in output, output


# ---------------------------------------------------------------------------
# M8-T36: reconcile the two route readers against each other.
#
# ``tests/test_http_route_inventory.py`` builds its own inventory: an AST scan of
# ``path == "..."`` plus a **hand-copied** ``_DYNAMIC_ROUTES`` list, because that
# scan cannot see prefix dispatch. ``scripts/route_coverage.py`` reads the same
# file with a different walker that *does* see ``startswith``/``endswith``.
# Neither reader notices the other going stale: add ``if
# path.startswith("/api/jobs/")`` to webserver.py and the inventory test keeps
# reporting a full, green table, because nothing compares its hand-copied list to
# what the source now says. A list copied by hand is exactly the failure M8-T32
# recorded ("a vocabulary read from the wrong pattern is as misleading as a
# hand-copied one"), so the two have to be reconciled in both directions:
# no prefix family without a template, no template without a family behind it.


#: The dispatcher's catch-all is not a route family to probe; like
#: ``_PARKED_FAMILIES`` in the inventory test, an exception has to carry a reason,
#: and an exception whose pattern no longer matches anything is stale and reported.
_CATCH_ALL = {("GET", "/api/*"): "unknown /api/ 404 fallback, not a real route"}

_TEMPLATE_MARK = "{task_id}"


def _declared_dynamic_routes() -> dict[str, list[str]]:
    """Read ``_DYNAMIC_ROUTES`` out of the inventory test without importing it.

    The declaration is annotated (``_DYNAMIC_ROUTES: dict[str, list[str]] = { … }``)
    so it is an ``AnnAssign``; reading only bare ``Assign`` made this extractor
    report the list as missing, which is the same self-inflicted blindness the
    script's own walker had once.
    """
    source = (REPO_ROOT / "tests" / "test_http_route_inventory.py").read_text(encoding="utf-8")
    for node in ast.parse(source).body:
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target]
        if any(isinstance(target, ast.Name) and target.id == "_DYNAMIC_ROUTES" for target in targets):
            assert node.value is not None
            return ast.literal_eval(node.value)
    raise AssertionError("_DYNAMIC_ROUTES 没了：手抄清单被删掉也要被这门看见")


def _prefix_labels(source_text: str) -> dict[str, set[str]]:
    """Raw ``verb -> route label`` pairs for every prefix/suffix dispatch site."""
    labels: dict[str, set[str]] = {}
    for site in rc.dispatch_sites(source_text):
        if "*" in site.route:
            labels.setdefault(site.verb, set()).add(site.route)
    return labels


def _prefix_families(source_text: str) -> dict[str, set[frozenset[str]]]:
    """Route families the AST reader reaches by prefix/suffix, as literal sets."""
    families: dict[str, set[frozenset[str]]] = {}
    for site in rc.dispatch_sites(source_text):
        if "*" not in site.route:
            continue
        if (site.verb, site.route) in _CATCH_ALL:
            continue
        parts = {token.strip("*") for token in site.route.split()}
        families.setdefault(site.verb, set()).add(frozenset(parts))
    return families


def _literal_parts(template: str) -> frozenset[str]:
    """The fixed segments of a declared template: ``/api/tasks/{id}/events`` -> two.

    A template with no ``{task_id}`` is not dynamic at all; the inventory test's
    generic probe skips those, so claiming one here would be a phantom.
    """
    assert _TEMPLATE_MARK in template, f"{template} 不是动态路由模板，不该出现在手抄清单里"
    prefix, _, suffix = template.partition(_TEMPLATE_MARK)
    return frozenset({piece for piece in (prefix, suffix) if piece})


def _reconcile(
    families: dict[str, set[frozenset[str]]],
    declared: dict[str, list[str]],
    labels: dict[str, set[str]] | None = None,
) -> list[str]:
    """Complain about every disagreement between the two readers."""
    complaints: list[str] = []
    verbs = sorted(set(families) | set(declared))
    for verb in verbs:
        group = families.get(verb, set())
        templates = declared.get(verb, [])
        for parts in sorted(group, key=lambda p: sorted(p)):
            if any(parts == _literal_parts(template) for template in templates):
                continue
            complaints.append(f"{verb} 源码里有前缀分派 {sorted(parts)}，手抄清单没有对应模板：它不会被任何探针驱动")
        for template in sorted(templates):
            parts = _literal_parts(template)
            if any(parts == declared_parts for declared_parts in group):
                continue
            complaints.append(f"{verb} 手抄清单声明了 {template}，源码里已没有这条前缀分派：幻影探针")
    if labels is not None:
        for verb, route in _CATCH_ALL:
            if route not in labels.get(verb, set()):
                complaints.append(f"{verb} {route} 这条豁免已经对不上源码里的任何前缀分派：豁免也会过期")
    return complaints


def test_the_dynamic_route_list_still_matches_the_source() -> None:
    """The load-bearing one: run the reconciliation over the real files."""
    source = (REPO_ROOT / "minicc" / "webserver.py").read_text(encoding="utf-8")
    labels = _prefix_labels(source)
    families = _prefix_families(source)
    declared = _declared_dynamic_routes()
    assert families, "前缀分派一族都没读到，这门就空转了"
    assert sum(len(paths) for paths in declared.values()) >= 4, declared
    assert _reconcile(families, declared, labels) == []
    # An exception without a reason is not an exception, it is an unrecorded hole.
    assert all(reason.strip() for reason in _CATCH_ALL.values()), _CATCH_ALL


def test_an_undeclared_prefix_family_is_reported() -> None:
    source = _MINI_DISPATCHER + '''
class More:
    def do_GET(self):
        path = self.path
        if path.startswith("/api/jobs/"):
            return 200
'''
    families = _prefix_families(source)
    complaints = _reconcile(families, {"GET": []})
    assert any("/api/jobs/" in text for text in complaints), complaints


def test_a_template_without_a_branch_behind_it_is_reported() -> None:
    families = _prefix_families(_MINI_DISPATCHER)
    complaints = _reconcile({"POST": {frozenset({"/api/tasks/"})}}, {"POST": ["/api/reports/{task_id}/export"]})
    assert any("幻影探针" in text for text in complaints), complaints
    assert families  # the mini dispatcher still exercises the reader


def test_an_exemption_that_no_longer_matches_anything_is_reported() -> None:
    """The catch-all the test excuses has to still exist in the dispatcher."""
    complaints = _reconcile({"GET": set()}, {"GET": []}, {"GET": {"/api/somewhere-else/*"}})
    assert any("豁免也会过期" in text for text in complaints), complaints
    assert _reconcile({"GET": set()}, {"GET": []}, {"GET": {"/api/*"}}) == []
