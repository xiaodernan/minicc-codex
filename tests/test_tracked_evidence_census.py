"""M8-T90: a gate git cannot see is not evidence.

The backup-line merge brought two test modules that existed only in the
working tree (``tests/test_git_write_boundary.py`` and a suite for a retired
i18n framework) which were absent from ``git ls-files``, so CI never ran
them and ``scripts/doc_pointers.py`` refused to see them twice over
- ``_resolve_path`` answers ``None`` for a file that exists here but is not
tracked, and ``_all_test_names`` skips an untracked module by construction
("citing a test that only exists on this machine is a citation that resolves
in neither a fresh clone nor CI"). Its index held 1108 names; 17 names on
this disk were not among them. M8-T836 retired the i18n suite; the boundary
suite was merged for real.

The caliber: **every module on this disk is tracked, and the evidence reader
resolves every test module**. The project already treats "exists only on this
machine" as a defect for files a document cites; a gate deserves the same rule,
because a gate nobody runs is a claim nobody checks.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

import doc_pointers  # noqa: E402  (the reader under test)

# Directories whose modules are the project's own machinery. A module here that
# git does not hold is a gate, a checker or a shipped source that no clone has.
# A repo-root ``*.py`` is deliberately out of scope: the root is where local
# scratch scripts live, and these three areas are the ones a clone needs.
AREAS = ("tests", "scripts", "minicc")

#: A census over an empty area passes forever, so each area declares the floor
#: it is read at. Deliberately below today's counts: this pins "the reader is
#: looking at a directory", not the exact size of the tree.
MINIMUM_MODULES = {"tests": 90, "scripts": 3, "minicc": 60}

#: Two modules of the promotion the gate landed on (M8-T811) that this
#: lineage still keeps pinned by name, so a regression that un-tracks one of
#: them specifically is still reported as itself. `tests/test_cli_i18n.py`
#: was retired in M8-T836 (the i18n framework it pinned no longer exists in
#: the main line), and the pin was moved onto two current modules from the
#: same promotion instead of silently dropping it.
FORMERLY_INVISIBLE = ("tests/test_git_write_boundary.py", "tests/test_rubric_shape.py")


def tracked_files() -> set[str]:
    """What ``git ls-files`` says this checkout holds (utf-8: git always emits it)."""
    result = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=True,
    )
    return set(result.stdout.split())


def modules_on_disk(area: str) -> list[str]:
    return sorted(path.relative_to(REPO_ROOT).as_posix()
                  for path in (REPO_ROOT / area).rglob("*.py")
                  if "__pycache__" not in path.parts)


def untracked(on_disk: list[str], tracked: set[str]) -> list[str]:
    """Sources present here that a fresh clone would not have."""
    return sorted(path for path in on_disk if path not in tracked)


# --- the rule ---------------------------------------------------------------


def test_every_module_this_repo_keeps_is_tracked() -> None:
    tracked = tracked_files()
    for area in AREAS:
        on_disk = modules_on_disk(area)
        assert len(on_disk) >= MINIMUM_MODULES[area], (
            f"{area} went empty, the census is not reading it: {len(on_disk)}")
        missing = untracked(on_disk, tracked)
        assert missing == [], (
            f"{area}: modules on this disk that git does not hold (no clone and no CI "
            f"ever runs them): {missing}"
        )


def test_the_evidence_reader_resolves_every_test_module() -> None:
    """The consequence: a citation of one of them is DANGLING EVIDENCE.

    A test name may be defined by many modules (the ``*_have_one_home.py``
    family deliberately reuses names). What makes a module citable is that it
    owns at least one name the reader indexed -- *not* that a name belongs to
    it alone. An untracked module owns no indexed name (``_holds`` filtered it
    out), so it is still reported here and by the tracked-files census above.
    """
    owners = doc_pointers._test_owner_index()
    assert len(owners) >= 1000, f"the reader index went blind: {len(owners)}"
    unseen: list[str] = []
    for module in sorted((REPO_ROOT / "tests").glob("test_*.py")):
        label = f"tests/{module.name}"
        if doc_pointers._resolve_path(label) is None:
            unseen.append(f"{label} (path does not resolve)")
            continue
        own = doc_pointers._test_definitions(module)
        if own and not any(module.name in owners.get(name, set()) for name in own):
            unseen.append(f"{label} (owns no test name the reader indexed)")
    assert unseen == [], f"modules the evidence reader cannot cite: {unseen}"


def test_the_two_modules_this_batch_promoted_stay_visible() -> None:
    """Named offender pin: the rule above must keep reporting *these* files."""
    owners = doc_pointers._test_owner_index()
    for label in FORMERLY_INVISIBLE:
        module = REPO_ROOT / label
        assert module.exists(), f"{label} disappeared; the pin cannot be re-derived"
        assert doc_pointers._resolve_path(label) is not None, label
        own = doc_pointers._test_definitions(module)
        assert own, f"{label} defines no tests any more"
        assert any(module.name in owners.get(name, set()) for name in own), label


# --- reverse controls -------------------------------------------------------


def test_the_untracked_census_notices_a_planted_module() -> None:
    """Reverse control: the rule must be able to say "untracked"."""
    on_disk = ["tests/test_a.py", "tests/test_b.py", "minicc/mod.py"]
    assert untracked(on_disk, {"tests/test_a.py", "minicc/mod.py"}) == ["tests/test_b.py"]
    assert untracked(on_disk, set(on_disk)) == []
    assert untracked([], set()) == []


def test_the_reader_arm_is_not_vacuous() -> None:
    """Reverse control: the reader must really answer "no" for an untracked path."""
    absent = "tests/test_a_module_that_is_not_in_this_repo.py"
    assert doc_pointers._resolve_path(absent) is None, absent
    real = "tests/test_tracked_evidence_census.py"
    assert doc_pointers._resolve_path(real) is not None, real
