"""Every silent broad handler must say why it is silent (M8-T190).

Measured on the shipped tree: 14 ``except Exception/BaseException`` handlers in ``minicc/``
whose body is only ``pass``/``continue``/``break``. All 14 state a reason - 11 carry
``# noqa: BLE001 - <why>`` on the handler line, 3 carry a comment between the handler line
and its body. The gap was never that a silent handler exists; it is that nothing stopped
the 15th one from arriving with no reason at all, so a reader of the file cannot tell a
deliberate silence from a leftover.

Two spellings of a reason count, and this gate accepts either:
  * a ``noqa`` marker on the ``except`` line, or
  * a comment between the ``except`` line and the first statement of its body.

AST keeps no comment nodes, so the comment form has to be read off the source lines - which
is why ``stated_reason`` (in ``_silence_reason_shared``) takes the lines alongside the node,
and why the two spellings get their own cells fed through the same detector the census uses.
"""
import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _silence_reason_shared import BROAD_TYPES, census_silent, stated_reason

REPO = Path(__file__).resolve().parents[1]
SOURCE_DIR = REPO / "minicc"
SILENT_STATEMENTS = frozenset({"pass", "continue", "break"})


def _is_silent_broad(node: ast.ExceptHandler) -> bool:
    kind = ast.unparse(node.type) if node.type else "BARE"
    return (kind in BROAD_TYPES
            and bool(node.body)
            and all(ast.unparse(stmt).split(" ")[0] in SILENT_STATEMENTS for stmt in node.body))


def _census() -> list[tuple[str, str]]:
    """(site, reason) for every broad handler whose body only passes/continues/breaks."""
    return census_silent(_is_silent_broad)


def test_the_walk_finds_the_silent_handlers_it_claims_to() -> None:
    """A gate that finds nothing has stopped measuring - the census is the evidence."""
    census = _census()
    assert len(census) >= 10, (
        f"the census only found {len(census)} silent broad handlers; measured 14 at M8-T190, "
        "so either the product changed or this walk went blind"
    )
    assert len({site for site, _ in census}) == len(census), "duplicate sites in the census"


def test_every_silent_broad_handler_states_why_it_is_silent() -> None:
    """The load-bearing cell: a silence with no stated reason is what this gate exists for."""
    unstated = [site for site, reason in _census() if not reason]
    assert unstated == [], (
        "these broad handlers swallow the exception without saying why - add "
        "`# noqa: BLE001 - <reason>` on the handler line, or a comment above the body: "
        f"{unstated}"
    )


NOQA_SOURCE = (
    "try:\n"
    "    run()\n"
    "except Exception:  # noqa: BLE001 - telemetry must not break the run\n"
    "    pass\n"
)
COMMENT_SOURCE = (
    "try:\n"
    "    run()\n"
    "except Exception:\n"
    "    # A poisoned pool must never block task-level recovery from replacing it.\n"
    "    pass\n"
)
BARE_SOURCE = "try:\n    run()\nexcept Exception:\n    pass\n"


def _reason_of(source: str) -> str:
    lines = source.splitlines()
    handler = ast.parse(source).body[0].handlers[0]
    return stated_reason(lines, handler)


@pytest.mark.parametrize(
    "source, expected_present",
    [(NOQA_SOURCE, True), (COMMENT_SOURCE, True), (BARE_SOURCE, False)],
    ids=["noqa", "comment", "bare"],
)
def test_both_spellings_of_a_reason_are_accepted(source: str, expected_present: bool) -> None:
    """The gate must accept the two forms the tree already uses, and reject a bare silence."""
    reason = _reason_of(source)
    assert bool(reason) is expected_present, (
        f"expected a stated reason: {expected_present}, got {reason!r}"
    )


def test_a_narrow_handler_is_out_of_scope() -> None:
    """Only broad handlers are in scope: `except OSError: pass` is already a named decision."""
    node = ast.parse("try:\n    run()\nexcept OSError:\n    pass\n").body[0].handlers[0]
    assert not _is_silent_broad(node)


def test_reason_detector_is_the_shared_one_not_a_private_copy() -> None:
    """Guards against re-copying ``stated_reason`` into this file (the M8-T200 drift risk)."""
    from _silence_reason_shared import stated_reason as _shared

    assert stated_reason is _shared