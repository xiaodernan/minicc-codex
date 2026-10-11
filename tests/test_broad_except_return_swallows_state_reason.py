"""A broad handler that swallows via a bare ``return`` is also silent (M8-T230).

The existing silence gate (``test_silence_must_state_its_reason.py``) only treats a
handler whose body is ``pass`` / ``continue`` / ``break`` as silent. A broad
``except Exception: return`` discards the exception and yields ``None`` just as surely
as ``except Exception: pass`` does, but the older gate's ``_is_silent_broad`` never
classifies it as silent - so a ``return``-swallow with no stated reason slips past it.

Measured on the shipped tree there are exactly three such handlers, and all three
already carry a reason (``# noqa: BLE001 - ...`` or a comment above the body). This
gate locks that shape in: every broad handler whose only body statement is a bare
``return`` (or ``return None``) must say why, exactly like the ``pass``-family ones.

Two spellings of a reason count, mirroring the sibling gate:
  * a ``noqa`` marker on the ``except`` line, or
  * a comment between the ``except`` line and the first (only) statement of its body.

AST keeps no comment nodes, so the comment form is read off the source lines.
"""
import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _silence_reason_shared import BROAD_TYPES, census_silent, stated_reason

REPO = Path(__file__).resolve().parents[1]
SOURCE_DIR = REPO / "minicc"


def _is_return_swallow(node: ast.ExceptHandler) -> bool:
    """Broad handler whose only body statement is a bare ``return`` (or ``return None``)."""
    if node.type is None:
        return False
    if not (isinstance(node.type, ast.Name) and node.type.id in BROAD_TYPES):
        return False
    if len(node.body) != 1:
        return False
    stmt = node.body[0]
    if not isinstance(stmt, ast.Return):
        return False
    # Bare `return` (value is None) or `return None` (Constant None) - both yield None.
    if stmt.value is None:
        return True
    return isinstance(stmt.value, ast.Constant) and stmt.value.value is None


def _census() -> list[tuple[str, str]]:
    """(site, reason) for every broad handler that swallows via a bare return."""
    return census_silent(_is_return_swallow)


def test_the_walk_finds_the_return_swallows_it_claims_to() -> None:
    """A gate that finds nothing has stopped measuring - the census is the evidence."""
    census = _census()
    assert len(census) >= 1, (
        "the census found no broad return-only swallows; measured 3 at M8-T230, so "
        "either the product changed or this walk went blind"
    )
    assert len({site for site, _ in census}) == len(census), "duplicate sites in the census"


def test_every_return_swallow_states_why_it_is_silent() -> None:
    """The load-bearing cell: a return-swallow with no stated reason is the bug we exist for."""
    unstated = [site for site, reason in _census() if not reason]
    assert unstated == [], (
        "these broad handlers swallow the exception via a bare return without saying why "
        "- add `# noqa: BLE001 - <reason>` on the handler line, or a comment above the "
        f"body: {unstated}"
    )


NOQA_SOURCE = (
    "try:\n"
    "    run()\n"
    "except Exception:  # noqa: BLE001 - tracing must never fail a run\n"
    "    return\n"
)
COMMENT_SOURCE = (
    "try:\n"
    "    run()\n"
    "except Exception:\n"
    "    # Status reporting must never turn a failure into a task failure.\n"
    "    return\n"
)
BARE_SOURCE = "try:\n    run()\nexcept Exception:\n    return\n"
NARROW_SOURCE = "try:\n    run()\nexcept OSError:\n    return\n"
RETURN_VALUE_SOURCE = "try:\n    run()\nexcept Exception:\n    return self.fallback\n"


def _reason_of(source: str) -> str:
    lines = source.splitlines()
    handler = ast.parse(source).body[0].handlers[0]
    return stated_reason(lines, handler)


def _is_swallow(source: str) -> bool:
    handler = ast.parse(source).body[0].handlers[0]
    return _is_return_swallow(handler)


@pytest.mark.parametrize(
    ("source", "expected_present"),
    [(NOQA_SOURCE, True), (COMMENT_SOURCE, True), (BARE_SOURCE, False)],
    ids=["noqa", "comment", "bare"],
)
def test_both_spellings_of_a_reason_are_accepted(source: str, expected_present: bool) -> None:
    """The gate must accept the two forms the tree already uses, and reject a bare silence."""
    reason = _reason_of(source)
    assert bool(reason) is expected_present, (
        f"expected a stated reason present={expected_present}, got {reason!r}"
    )


def test_a_narrow_handler_is_out_of_scope() -> None:
    """Only broad handlers are in scope: `except OSError: return` names its exception."""
    assert not _is_swallow(NARROW_SOURCE)


def test_a_return_with_a_value_is_not_a_swallow() -> None:
    """`return self.fallback` hands back a real value; it is not a silent discard."""
    assert not _is_swallow(RETURN_VALUE_SOURCE)


def test_reason_detector_is_the_shared_one_not_a_private_copy() -> None:
    """Guards against re-copying ``stated_reason`` into this file (the M8-T200 drift risk)."""
    from _silence_reason_shared import stated_reason as _shared

    assert stated_reason is _shared
