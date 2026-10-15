"""The mutation cells must still react to the code they name (M8-T246).

This gate exists because of a reading from M8-T245 that the repository then dropped.

That batch measured how many of the M8-T200 mutation cells survive a source mutation
that makes their gate blind. The answer was **3 of 19**: blind the reason detector to
always claim a reason and *nothing* went red; blind the layout audits to report every
site under ``tests/`` and *nothing* went red. The cells asserted on lists they had
built inside their own bodies, so the code they named was never consulted.

The rewrites made it 11 of 27. Then the measurement was recorded in the roadmap and
deleted, because the three mutations only ever lived in a scratch script. That is the
defect this file closes: **"do the mutation cells still react" had no gate**, so a
future edit could quietly re-blunt any cell and nothing in CI would notice.

So each entry below is a blind mutation - a real source edit that makes the named code
wrong - plus the red cells it must produce. The mutation is applied, the cells are
probed in a subprocess, the expectation is checked, and the file is restored from a
sha256 snapshot with byte-exactness verified. A blind mutation that turns nothing red
is a failure: that is the whole assertion.

Scope: the three mutations M8-T245's rewrite covered, plus every silence gate's own
predicates. Three gates decide whether a broad handler may swallow silently; two share
``_silence_reason_shared``, the third reimplemented all three predicates and walks
``scripts/`` too. It agreed with the shared ones only by coincidence - measured 17 of 17
on the shipped tree and 0 of 7 synthetic divergences, which is a reading, not a
guarantee. M8-T260 added agreement cells that pin the copy to the original, and this
table blinds all three of its predicates so the copy cannot drift without CI noticing.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
TESTS = REPO / "tests"

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


@dataclass(frozen=True)
class BlindMutation:
    """A source edit that makes one named piece of code wrong, and the red it must cause."""

    label: str
    target: str
    anchor: str
    replacement: str
    probe: str
    must_go_red: tuple[str, ...]


GATE_BLIND_MUTATIONS: tuple[BlindMutation, ...] = (
    BlindMutation(
        label="the reason detector stops noticing a missing reason",
        target="tests/_silence_reason_shared.py",
        anchor=(
            "def stated_reason(lines: list[str], node: ast.ExceptHandler) -> str:\n"
            '    """Why is this handler allowed to swallow? Empty string means it never said."""\n'
        ),
        replacement=(
            "def stated_reason(lines: list[str], node: ast.ExceptHandler) -> str:\n"
            '    """Why is this handler allowed to swallow? Empty string means it never said."""\n'
            '    return "stated"  # M8-T246 gate-blind mutation\n'
        ),
        probe="tests/test_silence_must_state_its_reason_mutation.py",
        must_go_red=("test_a_bare_silence_in_a_new_tree_is_flagged",),
    ),
    BlindMutation(
        label="the oracle passes everything",
        target="minicc/benchmarks.py",
        anchor='    oracle = row.get("objective_oracle")\n',
        replacement=(
            "    return True  # M8-T246 gate-blind mutation\n"
            '    oracle = row.get("objective_oracle")\n'
        ),
        probe="tests/test_oracle_vacuous_policy_mutation.py",
        must_go_red=(
            "test_mutation_C1_oracle_always_true",
            "test_mutation_C2_oracle_no_case_count",
            "test_case_count_zero_is_not_a_case_count",
            "test_an_unknown_grader_type_cannot_borrow_the_allow_policy",
            "test_vacuous_with_unknown_policy",
            "test_mutation_C3_policy_deny",
            "test_mutation_C4_policy_require_case_count",
            "test_every_mutation_arm_is_observable",
        ),
    ),
    BlindMutation(
        label="the audits report every site under tests/",
        target="tests/test_two_fixture_keys_must_share_one_workspace.py",
        anchor=(
            '                where = f"{root.name}/{path.relative_to(root).as_posix()}'
            '::{name}"\n'
        ),
        replacement=(
            '                where = f"tests/{path.relative_to(root).as_posix()}'
            '::{name}"\n'
        ),
        probe="tests/test_layout_gate_plane_composition_mutation.py",
        must_go_red=(
            "test_a_census_outside_tests_makes_the_gate_predicate_fail",
            "test_a_nested_path_still_reports_its_own_plane",
        ),
    ),
    BlindMutation(
        # M8-T248: the return-swallow parent's own reverse-control cell. This is the
        # red the parent gate cannot produce for itself - its load-bearing cell
        # asserts `unstated == []`, which an over-permissive detector satisfies
        # trivially.
        label="the reason detector also stops the return-swallow gate noticing one",
        target="tests/_silence_reason_shared.py",
        anchor=(
            "def stated_reason(lines: list[str], node: ast.ExceptHandler) -> str:\n"
            '    """Why is this handler allowed to swallow? Empty string means it never said."""\n'
        ),
        replacement=(
            "def stated_reason(lines: list[str], node: ast.ExceptHandler) -> str:\n"
            '    """Why is this handler allowed to swallow? Empty string means it never said."""\n'
            '    return "stated"  # M8-T248 gate-blind mutation\n'
        ),
        probe="tests/test_broad_except_return_swallows_state_reason_mutation.py",
        must_go_red=("test_a_bare_return_swallow_in_a_new_tree_is_flagged",),
    ),
    BlindMutation(
        # Measured: an over-broad predicate counts every handler as a swallow, so the
        # scope cells and the shipped-tree condition all notice.
        label="the return-swallow predicate accepts every handler",
        target="tests/test_broad_except_return_swallows_state_reason.py",
        anchor=(
            "def _is_return_swallow(node: ast.ExceptHandler) -> bool:\n"
            '    """Broad handler whose only body statement is a bare ``return`` '
            "(or ``return None``).\"\"\"\n"
        ),
        replacement=(
            "def _is_return_swallow(node: ast.ExceptHandler) -> bool:\n"
            '    """Broad handler whose only body statement is a bare ``return`` '
            "(or ``return None``).\"\"\"\n"
            "    return True  # M8-T248 gate-blind mutation\n"
        ),
        probe="tests/test_broad_except_return_swallows_state_reason_mutation.py",
        must_go_red=(
            "test_a_narrow_handler_is_never_counted",
            "test_a_return_with_a_value_is_not_counted",
            "test_the_shipped_tree_has_no_unstated_return_swallow",
        ),
    ),
    BlindMutation(
        label="the return-swallow predicate rejects every handler",
        target="tests/test_broad_except_return_swallows_state_reason.py",
        anchor=(
            "def _is_return_swallow(node: ast.ExceptHandler) -> bool:\n"
            '    """Broad handler whose only body statement is a bare ``return`` '
            "(or ``return None``).\"\"\"\n"
        ),
        replacement=(
            "def _is_return_swallow(node: ast.ExceptHandler) -> bool:\n"
            '    """Broad handler whose only body statement is a bare ``return`` '
            "(or ``return None``).\"\"\"\n"
            "    return False  # M8-T248 gate-blind mutation\n"
        ),
        probe="tests/test_broad_except_return_swallows_state_reason_mutation.py",
        must_go_red=(
            "test_the_shipped_tree_still_reports_a_return_swallow",
            "test_a_bare_return_swallow_in_a_new_tree_is_flagged",
        ),
    ),
    BlindMutation(
        # M8-T258: the pass-family predicate. Its mutation file already reacted when
        # measured, but no table entry blinded it, so nothing stopped a future edit
        # from blunting those cells. An over-broad predicate counts every handler.
        label="the silent-broad predicate accepts every handler",
        target="tests/test_silence_must_state_its_reason.py",
        anchor=(
            "def _is_silent_broad(node: ast.ExceptHandler) -> bool:\n"
            '    kind = ast.unparse(node.type) if node.type else "BARE"\n'
        ),
        replacement=(
            "def _is_silent_broad(node: ast.ExceptHandler) -> bool:\n"
            '    kind = ast.unparse(node.type) if node.type else "BARE"\n'
            "    return True  # M8-T258 gate-blind mutation\n"
        ),
        probe="tests/test_silence_must_state_its_reason_mutation.py",
        must_go_red=(
            "test_a_narrow_handler_is_never_counted",
            "test_the_shipped_tree_has_no_unstated_silence",
        ),
    ),
    BlindMutation(
        label="the silent-broad predicate rejects every handler",
        target="tests/test_silence_must_state_its_reason.py",
        anchor=(
            "def _is_silent_broad(node: ast.ExceptHandler) -> bool:\n"
            '    kind = ast.unparse(node.type) if node.type else "BARE"\n'
        ),
        replacement=(
            "def _is_silent_broad(node: ast.ExceptHandler) -> bool:\n"
            '    kind = ast.unparse(node.type) if node.type else "BARE"\n'
            "    return False  # M8-T258 gate-blind mutation\n"
        ),
        probe="tests/test_silence_must_state_its_reason_mutation.py",
        must_go_red=(
            "test_the_shipped_tree_still_reports_every_silent_handler",
            "test_a_bare_silence_in_a_new_tree_is_flagged",
        ),
    ),
    # M8-T260: the third silence gate copies all three predicates instead of importing
    # _silence_reason_shared, and it agreed with the shared ones only by coincidence.
    # Each arm below blinds one private predicate.
    BlindMutation(
        label="the third gate calls every handler broad",
        target="tests/test_broad_silent_handlers_state_a_reason.py",
        anchor=(
            "def _is_broad(handler: ast.ExceptHandler) -> bool:\n"
            "    if handler.type is None:\n"
            "        return True\n"
        ),
        replacement=(
            "def _is_broad(handler: ast.ExceptHandler) -> bool:\n"
            "    if handler.type is None:\n"
            "        return True\n"
            "    return True  # M8-T260 gate-blind mutation\n"
        ),
        probe="tests/test_broad_silent_handlers_state_a_reason_mutation.py",
        must_go_red=(
            "test_a_narrow_handler_is_out_of_scope",
            "test_the_third_gate_covers_exactly_the_two_shared_families",
        ),
    ),
    BlindMutation(
        label="the third gate calls no handler broad",
        target="tests/test_broad_silent_handlers_state_a_reason.py",
        anchor=(
            "def _is_broad(handler: ast.ExceptHandler) -> bool:\n"
            "    if handler.type is None:\n"
            "        return True\n"
        ),
        replacement=(
            "def _is_broad(handler: ast.ExceptHandler) -> bool:\n"
            "    if handler.type is None:\n"
            "        return True\n"
            "    return False  # M8-T260 gate-blind mutation\n"
        ),
        probe="tests/test_broad_silent_handlers_state_a_reason_mutation.py",
        must_go_red=(
            "test_the_shipped_tree_still_meets_its_floor",
            "test_the_third_gate_covers_exactly_the_two_shared_families",
        ),
    ),
    BlindMutation(
        label="the third gate calls every body silent",
        target="tests/test_broad_silent_handlers_state_a_reason.py",
        anchor=(
            "def _is_silent(handler: ast.ExceptHandler) -> bool:\n"
            "    return len(handler.body) == 1 and isinstance(handler.body[0], SILENT_BODIES)\n"
        ),
        replacement=(
            "def _is_silent(handler: ast.ExceptHandler) -> bool:\n"
            "    return True  # M8-T260 gate-blind mutation\n"
            "    return len(handler.body) == 1 and isinstance(handler.body[0], SILENT_BODIES)\n"
        ),
        probe="tests/test_broad_silent_handlers_state_a_reason_mutation.py",
        must_go_red=(
            "test_a_multi_statement_silent_body_is_out_of_scope",
            "test_the_third_gate_covers_exactly_the_two_shared_families",
        ),
    ),
    BlindMutation(
        label="the third gate calls no body silent",
        target="tests/test_broad_silent_handlers_state_a_reason.py",
        anchor=(
            "def _is_silent(handler: ast.ExceptHandler) -> bool:\n"
            "    return len(handler.body) == 1 and isinstance(handler.body[0], SILENT_BODIES)\n"
        ),
        replacement=(
            "def _is_silent(handler: ast.ExceptHandler) -> bool:\n"
            "    return False  # M8-T260 gate-blind mutation\n"
            "    return len(handler.body) == 1 and isinstance(handler.body[0], SILENT_BODIES)\n"
        ),
        probe="tests/test_broad_silent_handlers_state_a_reason_mutation.py",
        must_go_red=(
            "test_the_shipped_tree_still_meets_its_floor",
            "test_the_third_gate_covers_exactly_the_two_shared_families",
        ),
    ),
    BlindMutation(
        # The load-bearing one: this is the arm that pins the private detector to the
        # shared one. Blinding it reddens the agreement cell, so the agreement is no
        # longer a coincidence of the current tree.
        label="the third gate's private reason detector stops matching the shared one",
        target="tests/test_broad_silent_handlers_state_a_reason.py",
        anchor=(
            "def _states_a_reason(handler: ast.ExceptHandler, lines: list[str]) -> bool:\n"
            '    """A reason is a ``# noqa: BLE001 - <why>`` on the handler line, '
            "or a comment inside it.\n"
            "\n"
            "    Comments do not survive parsing, so this reads the source lines the "
            "handler spans -\n"
            "    from the ``except`` line through the end of its body. A trailing comment "
            "on the\n"
            "    silent statement counts too.\n"
            '    """\n'
        ),
        replacement=(
            "def _states_a_reason(handler: ast.ExceptHandler, lines: list[str]) -> bool:\n"
            '    """A reason is a ``# noqa: BLE001 - <why>`` on the handler line, '
            "or a comment inside it.\n"
            "\n"
            "    Comments do not survive parsing, so this reads the source lines the "
            "handler spans -\n"
            "    from the ``except`` line through the end of its body. A trailing comment "
            "on the\n"
            "    silent statement counts too.\n"
            '    """\n'
            '    return True  # M8-T260 gate-blind mutation\n'
        ),
        probe="tests/test_broad_silent_handlers_state_a_reason_mutation.py",
        must_go_red=(
            "test_a_bare_silence_is_flagged_by_the_private_reason_detector",
            "test_the_private_and_shared_reason_detectors_agree_on_every_fixture",
        ),
    ),
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cell_name(line: str) -> str:
    """The test name out of one ``FAILED`` line, whatever else pytest appended.

    pytest's short summary is ``FAILED <nodeid>`` on one host and
    ``FAILED <nodeid> - <exception message>`` on another - measured: the same probe
    run printed the bare nodeid locally and the message on both CI platforms. Taking
    everything after ``::`` kept the message, so a cell that had gone red was
    reported as one that never reacted, and the gate failed on the wrong thing.
    """
    body = line[len("FAILED "):]
    nodeid = body.split(" - ")[0].strip()
    return nodeid.split("::")[-1].strip()


def _probe(probe: str) -> tuple[bool, set[str]]:
    """``(collected cleanly, failed cell names)`` for one probe file.

    ``PYTHONIOENCODING`` is not decoration: pinning ``encoding="utf-8"`` on the
    parent alone leaves the child writing in the machine code page, which is how a
    non-ASCII assertion message becomes mojibake. ``tests/test_subprocess_decoding.py``
    scans every capture in the repo and rejected this file until the child declared
    its encoding too - the gate doing its job on new code.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", probe, "-q", "--no-header",
         "-p", "no:cacheprovider"],
        cwd=str(REPO), capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=600,
        env=dict(os.environ, PYTHONIOENCODING="utf-8"),
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    failed = {_cell_name(line)
              for line in output.splitlines()
              if line.startswith("FAILED")}
    # A collection error also exits nonzero but names no cell, which would look
    # exactly like "nothing reacted" if left unchecked.
    collected_clean = "errors during collection" not in output.lower()
    if proc.returncode != 0 and not failed and not collected_clean:
        raise AssertionError(f"{probe} did not run: {output[-2000:]}")
    return collected_clean, failed


def _apply(mutation: BlindMutation, path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(mutation.anchor) != 1:
        raise AssertionError(
            f"{mutation.label}: the anchor in {mutation.target} occurs "
            f"{text.count(mutation.anchor)} times, expected exactly 1 - the source "
            "it names moved, so this blind mutation no longer says what it claims"
        )
    path.write_text(text.replace(mutation.anchor, mutation.replacement, 1),
                    encoding="utf-8", newline="")


# --- the control: the unmutated tree is green, so a red means the mutation ---


def test_the_unmutated_tree_has_no_red_cells() -> None:
    """Without this, a red could be pre-existing and prove nothing about the mutation."""
    probes = sorted({m.probe for m in GATE_BLIND_MUTATIONS})
    for probe in probes:
        clean, failed = _probe(probe)
        assert clean and not failed, (
            f"{probe} is red before any mutation ({sorted(failed)}) - a blind "
            "mutation result would then be uninterpretable"
        )


# --- one blind mutation per named piece of code --------------------------


@pytest.mark.parametrize(
    "mutation",
    list(GATE_BLIND_MUTATIONS),
    ids=[m.label for m in GATE_BLIND_MUTATIONS],
)
def test_the_cells_go_red_when_the_code_they_name_is_broken(
    mutation: BlindMutation,
) -> None:
    """Make one named thing wrong; the cells that name it must notice.

    The load-bearing half of the assertion is the *zero* case. A cell that stays
    green under a blind mutation is decoration, which is the 16-of-19 reading this
    whole file was written to stop recurring.

    Restore is from an in-memory byte snapshot, not from ``git checkout``: the tree
    can hold another lane's uncommitted work, and clobbering it to prove a point
    would be a worse bug than the one being watched.
    """
    path = REPO / mutation.target
    pristine = path.read_bytes()
    before = _sha(path)
    try:
        _apply(mutation, path)
        clean, failed = _probe(mutation.probe)
    finally:
        path.write_bytes(pristine)

    assert _sha(path) == before, (
        f"{mutation.target} was not restored byte-exactly after blinding it "
        f"(sha {before[:12]} -> {_sha(path)[:12]})"
    )
    assert clean, f"{mutation.probe} failed to collect while blinded"
    missing = sorted(set(mutation.must_go_red) - failed)
    assert missing == [], (
        f"blinding {mutation.label} produced no red from {missing} - those cells no "
        f"longer react to the code they name, which is the defect this gate watches "
        f"for. Cells that did go red: {sorted(failed)}"
    )
    assert failed, (
        f"blinding {mutation.label} turned nothing red anywhere in {mutation.probe}. "
        "Every cell in a file like that is decoration"
    )


def test_the_failed_line_parser_survives_both_pytest_formats() -> None:
    """Pin the parser against the exact difference that broke this gate in CI.

    The same probe printed the bare nodeid locally and the nodeid plus its
    exception message on both CI platforms. A cell that went red was therefore
    read as a cell that never reacted, and this gate failed for the wrong reason.
    Both spellings must reduce to the same name.
    """
    bare = ("FAILED tests/test_silence_must_state_its_reason_mutation.py::"
            "test_a_bare_silence_in_a_new_tree_is_flagged")
    with_message = (
        bare + " - AssertionError: the census must report exactly the bare handler "
               "as unstated; got [] - either the handler moved or the detector "
               "stopped noticing a silence with no reason"
    )
    expected = "test_a_bare_silence_in_a_new_tree_is_flagged"
    assert _cell_name(bare) == expected
    assert _cell_name(with_message) == expected, (
        "a FAILED line carrying its exception message was not reduced to the cell "
        "name, so a red cell would be reported as a non-reacting one"
    )
    # A parametrized id must keep its bracket, not lose it to the message split.
    assert _cell_name("FAILED tests/x.py::test_cell[param id] - AssertionError: boom") == (
        "test_cell[param id]"
    )


def test_the_gate_blind_table_claims_a_real_red_for_every_entry() -> None:
    """A table entry with no expected red cells would make the gate above vacuous."""
    assert len(GATE_BLIND_MUTATIONS) >= 13, (
        f"the table holds only {len(GATE_BLIND_MUTATIONS)} blind mutations; the "
        "rewrites of M8-T245, M8-T248, M8-T258 and M8-T260 covered thirteen"
    )
    # One entry per probe file is not the invariant - the same file can be probed by
    # more than one blind arm - but every silence parent must be watched by one, and
    # each parent's own predicates must be blinded too, not just the shared detector.
    probed = {m.probe for m in GATE_BLIND_MUTATIONS}
    assert "tests/test_silence_must_state_its_reason_mutation.py" in probed
    assert "tests/test_broad_except_return_swallows_state_reason_mutation.py" in probed, (
        "the return-swallow parent's reverse-control file is no longer watched - "
        "M8-T248 closed that gap and this is the assertion that keeps it closed"
    )
    assert "tests/test_broad_silent_handlers_state_a_reason_mutation.py" in probed, (
        "the third silence gate's reverse-control file is no longer watched - M8-T260 "
        "closed that gap"
    )
    targets = {m.target for m in GATE_BLIND_MUTATIONS}
    assert "tests/test_silence_must_state_its_reason.py" in targets
    assert "tests/test_broad_except_return_swallows_state_reason.py" in targets
    assert "tests/test_broad_silent_handlers_state_a_reason.py" in targets, (
        "the third silence gate's private predicates are no longer blinded - M8-T260 "
        "locked them in, and blinding only the shared detector would let a copied "
        "detector drift without CI noticing"
    )
    blind = [m.label for m in GATE_BLIND_MUTATIONS if not m.must_go_red]
    assert blind == [], f"these entries demand no red cell at all: {blind}"
    for mutation in GATE_BLIND_MUTATIONS:
        target = REPO / mutation.target
        assert target.exists(), f"{mutation.target} does not exist"
        assert target.read_text(encoding="utf-8").count(mutation.anchor) == 1, (
            f"{mutation.label}: its anchor is not a unique string in "
            f"{mutation.target} any more - the mutation would either fail to apply "
            "or edit somewhere it did not name"
        )
