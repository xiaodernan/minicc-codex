"""The exemption for pytest's own scandir leak must not be able to hide ours.

``conftest._skip_upstream_scandir_sweep`` stops pytest's session-end GC sweep
because ``_pytest.pathlib.find_prefixed()`` abandons an ``os.scandir()``
iterator and the resulting ``ResourceWarning`` was failing green runs under
``-W error``. An exemption like that is only honest if our own code *cannot*
produce the thing being exempted - otherwise it would swallow a real leak with
the same message. The subject is therefore any resource this suite leaves to
the collector, and five claims make that checkable instead of asserted:

1. ``minicc/`` and ``scripts/`` never call ``os.scandir`` - the only API that
   raises "unclosed scandir iterator" directly.
2. Every ``Path.iterdir()`` call is consumed inside the same expression. On the
   pinned 3.11 interpreter ``Path.iterdir`` is implemented over ``os.listdir``
   (measured, batch 202), so its generator wraps a list and cannot raise that
   warning at all; the rule is kept because that is an interpreter
   implementation detail, not a contract - on an interpreter whose ``iterdir``
   is scandir-based, an abandoned generator raises the identical warning, so
   this is the second half of the same hole.
3. The walks that *do* create ``ScandirIterator`` objects here - ``os.walk``
   and ``Path.glob``/``rglob``, both measured - close them. The real budgeted
   walk sites run under a ResourceWarning-as-error filter with an unraisable
   hook installed, and a deliberately abandoned scandir proves the detector is
   alive before the walks are measured. 3.11's ``os.walk`` and pathlib globbers
   wrap their scandir in ``with``, which is why today's reading is clean; the
   gate keeps it that way instead of trusting that forever.
4. A file handle nobody can close. ``open(path).read()`` looks like a read and
   is a hand-off: the handle has no name, so nothing in this suite can close it
   and it dies at the mercy of whoever drops the last reference. Under the
   suite's ``-W error`` that death is an error, and claim 5 measures who pays
   for it. Measured (M8-T531): the suite's own
   ``test_the_task_stream_length_has_one_meaning.py`` had been red in three
   consecutive full fences for exactly that reason, reporting an ``unclosed
   TextIOWrapper`` and an unraisable ``FileIO`` for a read its own test had
   already finished with. No code in ``tests/``, ``minicc/`` or ``scripts/``
   may hand a file handle to the collector.
5. The billing model behind claim 4 is measured, not assumed: holding the
   handle is silent, and the warning fires at the *release*. Whoever drops the
   last reference pays for the open - which is why a leaked handle parked in a
   holder (a module list, a fixture that forgets to tear down) arrives as a red
   in the next test, not the one that opened it.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIRS = (REPO_ROOT / "minicc", REPO_ROOT / "scripts")
TESTS_DIR = REPO_ROOT / "tests"

#: Anti-vacuity floor: the walker must find the iterdir() sites that exist
#: today. If a refactor renames the pattern, this gate fails loudly instead of
#: passing because it found nothing to check.
_MIN_ITERDIR_SITES = 4

#: Anti-vacuity floor for claim 4: measured at 60 files carrying open() across
#: tests/, minicc/ and scripts/ (M8-T531). Below this the census is not clean,
#: it is blind.
_MIN_OPEN_CARRIER_FILES = 20

#: Calls that consume an iterator in the same expression.
_CONSUMERS = {"list", "sorted", "set", "tuple", "frozenset", "any", "all", "sum", "max", "min"}

#: ``open(p).close()`` is not a leak: that expression closes what it opened.
#: Anything else called straight off the call - ``read``, ``readline``,
#: ``write``, ``seek`` - leaves the handle with no name to close it by.
_CLOSING_ATTRS = {"close"}


def _sources() -> list[Path]:
    files: list[Path] = []
    for directory in PACKAGE_DIRS:
        files.extend(sorted(path for path in directory.rglob("*.py") if "__pycache__" not in path.parts))
    return files


def _censused_sources() -> list[Path]:
    """Every tree the read census walks, pre-filtered on a necessary truth.

    The shape needs the literal bytes ``open(`` to exist, so a file without
    them cannot hold it; skipping those is a speed fact, not a looseness - the
    parse itself still decides what counts.
    """
    files = sorted(TESTS_DIR.glob("*.py")) + _sources()
    return [path for path in files if b"open(" in path.read_bytes()]


def _parse(path: Path) -> ast.AST:
    """Parse the bytes, decoded the way the interpreter would decode them.

    A census that reads through a text-mode ``open()`` is itself a handle the
    collector has to close - the instrument would carry the defect it measures.
    """
    return ast.parse(path.read_bytes().decode("utf-8"))


def _is_open_call(node: ast.AST) -> bool:
    func = node.func if isinstance(node, ast.Call) else None
    if isinstance(func, ast.Name):
        return func.id == "open"
    if isinstance(func, ast.Attribute):
        return func.attr == "open"
    return False


def _unclosable_reads(tree: ast.AST) -> list[tuple[int, str]]:
    """Calls made directly on an ``open(...)`` result: no name, nothing to close it.

    A handle parked in a name (``handle = open(lock_path, "a+")``) is a
    deliberate holder and is out of scope here; this is the shape where the
    *only* reference is the expression that consumes it.
    """
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if not _is_open_call(node.func.value):
            continue
        if node.func.attr in _CLOSING_ATTRS:
            continue
        found.append((node.lineno, node.func.attr))
    return found


def _scandir_calls(tree: ast.AST) -> list[int]:
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "scandir":
            lines.append(node.lineno)
    return lines


def _iterdir_calls(tree: ast.AST) -> list[int]:
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "iterdir"
    ]


def _consumed_iterdir_lines(tree: ast.AST) -> set[int]:
    """Lines where an iterdir() call is consumed by its enclosing expression."""
    consumed: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.For, ast.comprehension)):
            for child in ast.walk(node.iter):
                if (
                    isinstance(child, ast.Call)
                    and isinstance(child.func, ast.Attribute)
                    and child.func.attr == "iterdir"
                ):
                    consumed.add(child.lineno)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _CONSUMERS:
            for child in ast.walk(node):
                if (
                    isinstance(child, ast.Call)
                    and isinstance(child.func, ast.Attribute)
                    and child.func.attr == "iterdir"
                ):
                    consumed.add(child.lineno)
    return consumed


def test_project_code_never_opens_a_scandir_iterator() -> None:
    offenders = [
        f"{path.relative_to(REPO_ROOT)}:{line}"
        for path in _sources()
        for line in _scandir_calls(ast.parse(path.read_text(encoding="utf-8")))
    ]
    assert offenders == [], (
        "os.scandir must be used as a context manager (or not at all): the "
        "session-end sweep that reports abandoned scandir iterators is exempted "
        "for pytest's own leak, so an unclosed one here would be swallowed. "
        f"Offenders: {offenders}"
    )


def test_every_iterdir_call_is_consumed_in_the_same_expression() -> None:
    sites: list[tuple[str, int]] = []
    abandoned: list[str] = []
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        consumed = _consumed_iterdir_lines(tree)
        for line in _iterdir_calls(tree):
            sites.append((str(path.relative_to(REPO_ROOT)), line))
            if line not in consumed:
                abandoned.append(f"{path.relative_to(REPO_ROOT)}:{line}")
    assert len(sites) >= _MIN_ITERDIR_SITES, (
        f"only {len(sites)} iterdir() site(s) found; the walker is looking at the "
        f"wrong shape, not at a clean tree. Sites: {sites}"
    )
    assert abandoned == [], (
        "iterdir() returns a generator over os.scandir; assigning it and not "
        "consuming it to exhaustion leaves the iterator to the GC, which is the "
        "same unraisable the exemption above covers. Consume it in one "
        f"expression (for/comprehension/list()/sorted()): {abandoned}"
    )


def test_our_directory_walks_leave_no_unraisable_scandir(tmp_path: Path) -> None:
    """Measure, do not argue: the real walks cannot raise the exempted warning.

    The two AST rules above argue our code cannot produce an abandoned
    ``ScandirIterator``. An argument can be wrong about a mechanism - this
    file's own second claim was, until batch 202 measured that 3.11's
    ``Path.iterdir`` is listdir-based. So the walks that really do create
    scandir iterators here (``os.walk`` in the evidence index and the impact
    scan) are run for real, each with a budget small enough to abandon the
    directory iterator mid-iteration, under ``ResourceWarning``-as-error with
    an unraisable hook installed.

    The detector proves itself first: a deliberately abandoned ``os.scandir``
    must be heard, otherwise a clean reading below would mean nothing. A
    hand-rolled walk that forgets to close its iterator turns this red.
    """
    import gc
    import os
    import sys
    import warnings

    from minicc.agent.retrieval import LocalEvidenceIndex
    from minicc.impact import analyze_change_impact

    events: list[str] = []
    previous_hook = sys.unraisablehook

    def hook(unraisable) -> None:  # noqa: ANN001 - mirrors sys.unraisablehook
        text = str(unraisable.exc_value)
        if "scandir" in text:
            events.append(f"{unraisable.exc_type.__name__}: {text}")

    def abandon_one_scandir(root: Path) -> None:
        for _entry in os.scandir(root):
            break

    # The control needs a non-empty directory: against an empty one the
    # for-loop's first next() raises StopIteration, which exhausts and
    # closes the iterator - that is the safe path, not the leak.
    (tmp_path / "marker.py").write_text("MARKER = 1\n", encoding="utf-8")
    sys.unraisablehook = hook
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", ResourceWarning)
            abandon_one_scandir(tmp_path)
            for _ in range(3):
                gc.collect()
            assert events, (
                "the unraisable hook did not hear a deliberately abandoned "
                "os.scandir iterator; the detector this gate relies on is deaf"
            )
            events.clear()

            workspace = tmp_path / "ws"
            (workspace / "pkg").mkdir(parents=True)
            (workspace / "pkg" / "one.py").write_text("ONE = 1\n", encoding="utf-8")
            (workspace / "pkg" / "two.py").write_text("TWO = 2\n", encoding="utf-8")
            # A second subdirectory: with only one, a walk that forgets to
            # close its scandir still exhausts it naturally, and the leak
            # never happens. Two entries is what makes abandonment possible.
            (workspace / "other").mkdir()
            (workspace / "README.md").write_text("# readme\n", encoding="utf-8")

            # max_files=1 forces the walk's own early return, which is what
            # abandons the directory iterator mid-iteration.
            index = LocalEvidenceIndex(workspace, max_files=1, max_directories=1)
            index.search("readme")

            report = analyze_change_impact(workspace, ["pkg/one.py"], max_files=1)
            assert report["stats"]["scanned_files"] >= 1, (
                "the impact scan must walk at least one file for this gate to "
                "mean anything"
            )

            for _ in range(3):
                gc.collect()
            assert events == [], (
                "a directory walk in minicc/ left a scandir iterator to the GC - "
                "exactly what the conftest exemption would swallow; "
                f"events={events}"
            )
    finally:
        sys.unraisablehook = previous_hook


def test_no_code_reads_a_file_with_a_handle_nobody_can_close() -> None:
    """Claim 4: ``open(p).read()`` hands the handle to the collector.

    The bill is not paid where it is incurred. Measured on 3.11.1: parking the
    handle is silent, releasing it is what raises - so the ``ResourceWarning``
    arrives inside whichever test happens to run when the last reference
    drops, and under the suite's ``-W error`` that test goes red for a read it
    never made.
    """
    censused = _censused_sources()
    offenders = [
        f"{path.relative_to(REPO_ROOT)}:{line}.{attr}"
        for path in censused
        for line, attr in _unclosable_reads(_parse(path))
    ]
    assert len(censused) >= _MIN_OPEN_CARRIER_FILES, (
        f"only {len(censused)} files even mention open() across "
        "tests/, minicc/ and scripts/ - the census is looking at the wrong "
        "tree, not at a clean one"
    )
    assert offenders == [], (
        "a file handle with no name to close it is a landmine planted on "
        "whoever runs next; use `with open(...) as handle:` or "
        f"Path(...).read_text(): {offenders}"
    )


def test_the_read_census_charges_a_call_and_not_a_string_of_one() -> None:
    """The census is an AST census, and that distinction is the whole claim.

    ``tests/test_hooks.py`` builds child-process sources as strings, so a text
    scan reports two sites where the tree says one (measured: text=2, AST=1).
    A walker that cannot tell the two apart either cries at legitimate code or,
    once loosened to tolerate it, stops seeing the real thing - so the shape
    that leaked is planted here and proved visible, and the same shape written
    inside a string is proved invisible.
    """
    planted = ast.parse(
        "src = open('somewhere.py', encoding='utf-8').read()\n"
        "CMD = \"print(open('secret.txt').read())\"\n"
        "with open('fine.py', encoding='utf-8') as handle:\n"
        "    text = handle.read()\n"
        "open('marked', 'a').close()\n"
        "raw = io.open('other.py').read()\n"
        "tail = Path('third.py').open().readline()\n"
    )
    found = _unclosable_reads(planted)
    assert found == [(1, "read"), (6, "read"), (7, "readline")], (
        "the census must charge the three calls made straight off an open - "
        "built-in, io.open and Path.open - and nothing else: the string on line "
        "2 is a child process's source, line 3-4 closes what it opens and line 5 "
        f"closes what it opens: {found}"
    )


def test_a_parked_handle_is_paid_for_at_the_release(tmp_path: Path) -> None:
    """Claim 5: measure the billing moment instead of arguing about it.

    If the warning came out at the ``open``, the census above would only be a
    style rule. It comes out when the last reference drops - which is what
    makes one gate's leak another gate's red, and what makes the shape worth a
    standing gate.
    """
    import gc
    import warnings

    victim = tmp_path / "handle_victim.txt"
    victim.write_text("payload\n", encoding="utf-8")

    def resource_warnings(events: list[warnings.WarningMessage]) -> list[str]:
        return [
            str(event.message)
            for event in events
            if issubclass(event.category, ResourceWarning) and victim.name in str(event.message)
        ]

    with warnings.catch_warnings(record=True) as events:
        warnings.simplefilter("always")
        parked = [open(victim, encoding="utf-8")]
        gc.collect()
        at_park = resource_warnings(events)
        assert at_park == [], (
            "the warning fired while the handle was still referenced, so the "
            f"release is not the billing moment: {at_park}"
        )
        parked.clear()
        gc.collect()
        at_release = resource_warnings(events)

    assert len(at_release) == 1, (
        "dropping the last reference to an unclosed file must raise exactly one "
        f"ResourceWarning for it; the model this gate stands on is: {at_release}"
    )
    assert "unclosed file" in at_release[0], (
        f"the warning is not the unclosed-file one: {at_release[0]}"
    )
