"""The exemption for pytest's own scandir leak must not be able to hide ours.

``conftest._skip_upstream_scandir_sweep`` stops pytest's session-end GC sweep
because ``_pytest.pathlib.find_prefixed()`` abandons an ``os.scandir()``
iterator and the resulting ``ResourceWarning`` was failing green runs under
``-W error``. An exemption like that is only honest if our own code *cannot*
produce the thing being exempted - otherwise it would swallow a real leak with
the same message. Three claims make that argument checkable instead of
asserted:

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
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIRS = (REPO_ROOT / "minicc", REPO_ROOT / "scripts")

#: Anti-vacuity floor: the walker must find the iterdir() sites that exist
#: today. If a refactor renames the pattern, this gate fails loudly instead of
#: passing because it found nothing to check.
_MIN_ITERDIR_SITES = 4

#: Calls that consume an iterator in the same expression.
_CONSUMERS = {"list", "sorted", "set", "tuple", "frozenset", "any", "all", "sum", "max", "min"}


def _sources() -> list[Path]:
    files: list[Path] = []
    for directory in PACKAGE_DIRS:
        files.extend(sorted(path for path in directory.rglob("*.py") if "__pycache__" not in path.parts))
    return files


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
