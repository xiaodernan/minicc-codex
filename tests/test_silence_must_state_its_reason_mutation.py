"""Reverse-control cells for the silence gate (M8-T239).

The file this replaces shipped with M8-T200 and was measured at M8-T239 as not
carrying its weight: three of its nine cells were no-ops (``assert True`` twice, a
bare ``pass`` once), it carried a second copy of ``_count_silent_handlers``, and it
walked the tree with its own private detector instead of the shared one - the exact
drift ``test_reason_detector_is_the_shared_one_not_a_private_copy`` exists to stop.
Worst, the walk reported ``path.relative_to(Path.cwd())``, so the file went red on
any plane whose cwd was not the repo root.

The reverse control that found this: blind the code each cell claims to protect
(``stated_reason`` always claims a reason) and count how many cells notice. Before
this rewrite **none** of the nine went red; the file could not tell the gate was
broken.

So each cell here does one of two things:

  * walks a **temporary** tree through the shared ``census_silent`` and asserts the
    gate's own load-bearing condition (``unstated == []``) *fails*, or
  * asserts the file holds no private copy of the detector.

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
from test_silence_must_state_its_reason import (  # noqa: E402
    REPO,
    _is_silent_broad,
)

SOURCE_DIR = REPO / "minicc"

BARE = '''"""A fixture module with a silence nobody explained."""


def probe():
    try:
        run()
    except Exception:
        pass
'''

NOQA = '''"""The same probe with a noqa on the handler line."""


def probe():
    try:
        run()
    except Exception:  # noqa: BLE001 - telemetry must not break the run
        pass
'''

COMMENT = '''"""The same probe with a comment between the handler line and its body."""


def probe():
    try:
        run()
    except Exception:
        # A poisoned pool must never block task-level recovery from replacing it.
        pass
'''

NARROW = '''"""A narrow handler is a named decision, not a silent broad one."""


def probe():
    try:
        run()
    except OSError:
        pass
'''


def _tree(tmp_path: Path, source: str) -> Path:
    root = tmp_path / "fixture_tree"
    root.mkdir(parents=True, exist_ok=True)
    (root / "probe_mod.py").write_text(source, encoding="utf-8")
    return root


def _unstated(source_dir: Path) -> list[str]:
    """The exact condition ``test_every_silent_broad_handler_states_why_it_is_silent`` asserts."""
    return [site for site, reason in census_silent(_is_silent_broad, source_dir)
            if not reason]


def _bare_handler_line(source: str) -> int:
    """Which line of ``source`` holds the ``except`` - so the cell cannot drift.

    Hard-coding it made the cell fail on a fixture it had written itself; reading it
    back keeps the assertion about *one unstated silence at a known handler*.
    """
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ExceptHandler) and _is_silent_broad(node):
            return node.lineno
    raise AssertionError("the fixture has no silent broad handler to test")


# --- the shipped tree still answers, and still answers "nothing unstated" ---


def test_the_shipped_tree_still_reports_every_silent_handler() -> None:
    """A walk that has stopped finding handlers would make every cell below vacuous."""
    found = census_silent(_is_silent_broad, SOURCE_DIR)
    assert len(found) >= 10, (
        f"the shared census found only {len(found)} silent broad handlers under minicc/; "
        "M8-T190 measured 14, so the walk has gone blind"
    )
    assert len({site for site, _ in found}) == len(found), "duplicate sites in the census"


def test_the_shipped_tree_has_no_unstated_silence() -> None:
    """The gate's load-bearing condition, over the real tree."""
    assert _unstated(SOURCE_DIR) == [], (
        "these broad handlers swallow the exception without saying why: "
        f"{_unstated(SOURCE_DIR)}"
    )


# --- mutations of a tree the gate has never seen ---------------------------


def test_a_bare_silence_in_a_new_tree_is_flagged(tmp_path: Path) -> None:
    """The reverse-control cell: a silence with no reason must be *found*.

    This is the assertion that went red for nothing before M8-T239, because the
    file walked with its own detector. Feed the shared census a tree whose only
    handler never says why and the gate's condition must fire.
    """
    unstated = _unstated(_tree(tmp_path, BARE))
    expected = _bare_handler_line(BARE)
    assert unstated == [f"probe_mod.py:{expected}"], (
        "the census must report exactly the bare handler as unstated; got "
        f"{unstated} - either the handler moved or the detector stopped noticing "
        "a silence with no reason"
    )


def test_noqa_stops_the_same_tree_from_being_flagged(tmp_path: Path) -> None:
    """Control for the cell above: adding the documented spelling clears it."""
    assert _unstated(_tree(tmp_path, NOQA)) == [], (
        "a noqa marker on the handler line must count as a stated reason"
    )


def test_a_comment_above_the_body_stops_the_same_tree_from_being_flagged(
    tmp_path: Path,
) -> None:
    """The other spelling the tree already uses must clear it too."""
    assert _unstated(_tree(tmp_path, COMMENT)) == [], (
        "a comment between the handler line and the body must count as a stated reason"
    )


def test_a_narrow_handler_is_never_counted(tmp_path: Path) -> None:
    """``except OSError: pass`` is out of scope; counting it would fake a floor."""
    found = census_silent(_is_silent_broad, _tree(tmp_path, NARROW))
    assert found == [], f"a narrow handler was counted as a broad silence: {found}"


def test_an_empty_tree_reports_nothing_and_says_so(tmp_path: Path) -> None:
    """A census over an empty tree finds nothing - which is why cells assert content, not emptiness."""
    empty = tmp_path / "empty_tree"
    empty.mkdir()
    assert census_silent(_is_silent_broad, empty) == []


# --- the detector is imported, not copied ----------------------------------


def test_this_file_carries_no_private_copy_of_the_detector() -> None:
    """The defect M8-T200 shipped: a second implementation hiding beside the first.

    A private copy keeps passing after the shared one is blinded, which is exactly
    what the reverse control measured. Read by AST, not by substring: this file's
    own docstring names the borrowed functions, and a substring check trips over
    itself on the first run.
    """
    import tests.test_silence_must_state_its_reason_mutation as self_module

    tree = ast.parse(Path(self_module.__file__).read_text(encoding="utf-8"))
    defined = {node.name for node in ast.walk(tree)
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    for borrowed in ("stated_reason", "census_silent", "_is_silent_broad"):
        assert borrowed not in defined, (
            f"{borrowed} is defined here instead of being imported - this file would "
            "keep passing while the shared detector is broken"
        )
    assert stated_reason is not None and _is_silent_broad is not None


def test_the_reason_detector_here_is_the_shared_object() -> None:
    """Same identity check the main gate runs, applied to this file's import."""
    from _silence_reason_shared import stated_reason as shared

    assert stated_reason is shared, "this file reached a different stated_reason"
