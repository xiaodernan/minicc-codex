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

Scope: three mutations, because those are the three the rewrite of M8-T245 covered.
The silence *parent* gates still have no mutation file of their own - their census
logic is probed here only through the shared detector, which is recorded as a real
gap in the batch record, not hidden by a wide table.
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
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    failed = {line.split("::")[-1].strip()
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


def test_the_gate_blind_table_claims_a_real_red_for_every_entry() -> None:
    """A table entry with no expected red cells would make the gate above vacuous."""
    assert len(GATE_BLIND_MUTATIONS) >= 3, (
        f"the table holds only {len(GATE_BLIND_MUTATIONS)} blind mutations; the "
        "rewrite of M8-T245 covered three"
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
