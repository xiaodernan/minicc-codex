"""Reverse-control cells for the return-swallow gate (M8-T248).

``test_broad_except_return_swallows_state_reason.py`` shipped with six cells and no
mutation sibling, so nothing measured whether those cells still react. Measured on the
shipped tree: blinding the shared reason detector to always claim a reason turned
**one** cell red, and it was a synthetic parametrized fixture - not the load-bearing
one.

The load-bearing cell asserts ``unstated == []`` over the real tree. A detector that
always reports a reason makes that list trivially empty, so the gate cannot notice an
over-permissive detector at all. That is the same defect class M8-T245 found in the
M8-T200 files, and it is why this file exists.

So each cell here does one of two things:

  * walks a **temporary** tree through the shared ``census_silent`` and asserts the
    gate's own load-bearing condition *fails* on a known-bad fixture, or
  * asserts the file holds no private copy of the predicate it borrows.

Nothing here writes inside the repository: the fixture tree is pytest's ``tmp_path``.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _silence_reason_shared import census_silent, stated_reason  # noqa: E402
from test_broad_except_return_swallows_state_reason import (  # noqa: E402
    REPO,
    _is_return_swallow,
)

SOURCE_DIR = REPO / "minicc"

BARE = '''"""A fixture module with a return-swallow nobody explained."""


def probe():
    try:
        run()
    except Exception:
        return
'''

NOQA = '''"""The same probe with a noqa on the handler line."""


def probe():
    try:
        run()
    except Exception:  # noqa: BLE001 - tracing must never fail a run
        return
'''

COMMENT = '''"""The same probe with a comment between the handler line and its body."""


def probe():
    try:
        run()
    except Exception:
        # Status reporting must never turn a failure into a task failure.
        return
'''

NARROW = '''"""A narrow handler is a named decision, not a silent broad one."""


def probe():
    try:
        run()
    except OSError:
        return
'''

RETURN_VALUE = '''"""`return self.fallback` hands back a real value; it is not a silent discard."""


def probe():
    try:
        run()
    except Exception:
        return self.fallback
'''


def _tree(tmp_path: Path, source: str) -> Path:
    root = tmp_path / "fixture_tree"
    root.mkdir(parents=True, exist_ok=True)
    (root / "probe_mod.py").write_text(source, encoding="utf-8")
    return root


def _unstated(source_dir: Path) -> list[str]:
    """The exact condition ``test_every_return_swallow_states_why_it_is_silent`` asserts."""
    return [site for site, reason in census_silent(_is_return_swallow, source_dir)
            if not reason]


def _bare_handler_line(source: str) -> int:
    """Which line of ``source`` holds the ``except`` - so the cell cannot drift.

    Hard-coding it made the sibling file fail on a fixture it had written itself;
    reading it back keeps the assertion about one unstated swallow at a known handler.
    """
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ExceptHandler) and _is_return_swallow(node):
            return node.lineno
    raise AssertionError("the fixture has no return-swallow to test")


# --- the shipped tree still answers, and still answers "nothing unstated" ---


def test_the_shipped_tree_still_reports_a_return_swallow() -> None:
    """A walk that has stopped finding handlers would make every cell below vacuous."""
    found = census_silent(_is_return_swallow, SOURCE_DIR)
    assert len(found) >= 1, (
        "the shared census found no broad return-only swallows under minicc/; the "
        "parent gate measured 3 at M8-T230, so the walk has gone blind"
    )
    assert len({site for site, _ in found}) == len(found), "duplicate sites in the census"


def test_the_shipped_tree_has_no_unstated_return_swallow() -> None:
    """The gate's load-bearing condition, over the real tree."""
    assert _unstated(SOURCE_DIR) == [], (
        "these broad handlers swallow the exception via a bare return without saying why: "
        f"{_unstated(SOURCE_DIR)}"
    )


# --- mutations of a tree the gate has never seen ---------------------------


def test_a_bare_return_swallow_in_a_new_tree_is_flagged(tmp_path: Path) -> None:
    """The reverse-control cell: a swallow with no reason must be *found*.

    This is the assertion that the parent gate cannot make for itself. Its
    load-bearing cell asserts ``unstated == []``, which a detector that always
    reports a reason satisfies trivially. Feed the shared census a tree whose only
    handler never says why and the gate's condition must fire - if it does not,
    the detector has gone blind in the permissive direction.
    """
    unstated = _unstated(_tree(tmp_path, BARE))
    expected = _bare_handler_line(BARE)
    assert unstated == [f"probe_mod.py:{expected}"], (
        "the census must report exactly the bare return-swallow as unstated; got "
        f"{unstated} - either the handler moved or the detector stopped noticing "
        "a swallow with no reason"
    )


def test_noqa_clears_the_same_tree(tmp_path: Path) -> None:
    """Control for the cell above: adding the documented spelling clears it."""
    assert _unstated(_tree(tmp_path, NOQA)) == [], (
        "a noqa marker on the handler line must count as a stated reason"
    )


def test_a_comment_clears_the_same_tree(tmp_path: Path) -> None:
    """The other spelling the tree already uses must clear it too."""
    assert _unstated(_tree(tmp_path, COMMENT)) == [], (
        "a comment between the handler line and the body must count as a stated reason"
    )


def test_a_narrow_handler_is_never_counted(tmp_path: Path) -> None:
    """``except OSError: return`` names its exception; counting it would fake a floor."""
    found = census_silent(_is_return_swallow, _tree(tmp_path, NARROW))
    assert found == [], f"a narrow handler was counted as a broad swallow: {found}"


def test_a_return_with_a_value_is_not_counted(tmp_path: Path) -> None:
    """``return self.fallback`` hands back a value, so it is not a silent discard."""
    found = census_silent(_is_return_swallow, _tree(tmp_path, RETURN_VALUE))
    assert found == [], f"a value-returning handler was counted as a swallow: {found}"


# --- the predicate is imported, not copied ----------------------------------


def test_this_file_carries_no_private_copy_of_the_predicate() -> None:
    """The defect M8-T200 shipped: a second implementation hiding beside the first.

    Read by AST, not by substring: this file's own docstring names the borrowed
    functions, and a substring check trips over itself on the first run.
    """
    import tests.test_broad_except_return_swallows_state_reason_mutation as self_module

    tree = ast.parse(Path(self_module.__file__).read_text(encoding="utf-8"))
    defined = {node.name for node in ast.walk(tree)
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    for borrowed in ("stated_reason", "census_silent", "_is_return_swallow"):
        assert borrowed not in defined, (
            f"{borrowed} is defined here instead of being imported - this file would "
            "keep passing while the shared detector is broken"
        )
    assert stated_reason is not None and _is_return_swallow is not None


def test_the_predicate_here_is_the_parent_gate_s_object() -> None:
    """Same identity check the parent gate runs on its detector, applied to the predicate."""
    from test_broad_except_return_swallows_state_reason import _is_return_swallow as shared

    assert _is_return_swallow is shared, "this file reached a different _is_return_swallow"
