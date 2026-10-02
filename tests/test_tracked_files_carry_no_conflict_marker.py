"""No tracked file may carry a git conflict marker.

Why this gate exists: an increment of this project committed a ledger record whose last
line was a leftover ``>>>>>>>`` marker (a rebase continuation that kept both sides of a
conflict and deleted only the other two markers). The whole suite - 1671 cases - stayed
green with that marker committed in ``docs/ROADMAP_TO_PRODUCT.md``, because nothing in
this repository judges markers. The only defence that ever fired was a machine-wide hook
under ``~/.codex/git-hooks``, and ``git rebase --continue`` does not run pre-commit hooks
at all, so the defence that caught it was bypassable by the very operation that produced
it. That is an unarmed control, not a fixed one.

Design decisions this file pins down, each with a case:
- The predicate keys on the two chevron spellings at line start. A whole-line run of
  seven ``=`` is legal markdown (a setext heading underline), so treating it as a marker
  would forbid a shape the repository is allowed to write - and a documentation file is
  exactly where such a line belongs.
- The population is ``git ls-files``, so the claim is about the tracked tree rather than
  whatever happens to sit on one disk, and ``build/lib`` copies are covered by the same
  walk. The floor below is a guard against the scan narrowing itself to nothing: an
  absence claim over an empty list passes on a plane that read no files.
- The walk must reach the document formats, not just Python: the defect being gated was
  in a ``.md`` file.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# git writes ``<<<<<<< `` / ``>>>>>>> `` with a trailing space before the ref name; the
# space is part of the marker, and matching without it would also fire on prose that
# merely starts a sentence with chevrons.
LEFT_MARKER = b"<<<<<<< "
RIGHT_MARKER = b">>>>>>> "
MARKERS = ("left", "right")

# Floor, not an expectation: if someone narrows the walk the gate has to go red instead
# of passing over a list that stopped containing files. The real population is several
# hundred files (the whole tracked tree), so a scan that silently lost a directory, a
# file type or the walk itself drops under this.
_MIN_TRACKED = 200


def _tracked_files() -> list[str]:
    raw = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "-z"],
        capture_output=True,
        check=True,
    ).stdout
    return sorted(entry.decode("utf-8", "surrogateescape") for entry in raw.split(b"\0") if entry)


def _marker_lines(blob: bytes) -> list[tuple[str, int]]:
    """Return (kind, line number) for every conflict-marker line in raw bytes.

    Bytes on purpose: a tracked document here is CRLF, and a text-mode read with
    universal newlines would let the same content pass or fail depending on how the
    file was checked out.
    """
    found: list[tuple[str, int]] = []
    for number, line in enumerate(blob.split(b"\n"), 1):
        if line.startswith(LEFT_MARKER):
            found.append(("left", number))
        elif line.startswith(RIGHT_MARKER):
            found.append(("right", number))
    return found


def _scan(files: list[str]) -> list[str]:
    offenders: list[str] = []
    for relative in files:
        path = REPO_ROOT / relative
        if not path.is_file():
            continue
        for kind, number in _marker_lines(path.read_bytes()):
            offenders.append(f"{relative}:{number} ({kind} marker)")
    return offenders


def test_the_tracked_population_is_real_and_reaches_the_formats_that_matter() -> None:
    files = _tracked_files()
    assert len(files) >= _MIN_TRACKED, files[:5]
    by_extension = {Path(name).suffix.lower() for name in files}
    assert ".md" in by_extension, sorted(by_extension)
    assert "docs/ROADMAP_TO_PRODUCT.md" in files, (
        "the document that actually shipped a marker must be inside the walk"
    )
    assert ".py" in by_extension, sorted(by_extension)


def test_no_tracked_file_carries_a_conflict_marker() -> None:
    offenders = _scan(_tracked_files())
    assert not offenders, (
        "these tracked files contain git conflict markers, so a merge was committed "
        "half-resolved: " + "; ".join(offenders)
    )


def test_the_scan_fires_on_each_marker_spelling_and_only_on_them() -> None:
    left = ("<<<<<<< HEAD\r\nours\r\n").encode("utf-8")
    right = ("theirs\r\n>>>>>>> 0000000 (subject)\r\n").encode("utf-8")
    assert _marker_lines(left) == [("left", 1)], _marker_lines(left)
    assert _marker_lines(right) == [("right", 2)], _marker_lines(right)
    # Each spelling has to carry weight on its own: a walk that keeps only one of them
    # still reads the other file's marker as clean.
    assert {kind for kind, _ in _marker_lines(left) + _marker_lines(right)} == set(MARKERS)
    # What the walk must NOT catch: a run of seven equals (legal markdown - a setext
    # heading underline, which this repository's documents are allowed to write), a
    # marker spelled inside a sentence rather than at line start, and a marker without
    # the space git always writes.
    not_markers = (
        "Title\r\n"
        "=======\r\n"
        "This file talks about <<<<<<< and >>>>>>> inside a sentence.\r\n"
        "<<<<<<<nospace\r\n"
    ).encode("utf-8")
    assert _marker_lines(not_markers) == [], _marker_lines(not_markers)
    # The same line with the space git writes is the marker: that space is what keeps
    # the rule distinguishable from a document discussing the rule.
    assert _marker_lines("<<<<<<< HEAD\r\n".encode("utf-8")) == [("left", 1)]


def test_the_marker_rule_is_the_one_the_walk_applies() -> None:
    """Convergence: the constants and the matcher must agree, in both directions.

    Without this, widening ``LEFT_MARKER`` to something unmatchable (or to the bare
    chevron run) leaves the walk and the declared predicate describing two different
    rules, and the gate passes while enforcing nothing.
    """
    for spelling in (LEFT_MARKER, RIGHT_MARKER):
        assert spelling.endswith(b" "), spelling
        assert len(spelling.rstrip(b" ")) == 7, spelling
        assert _marker_lines(spelling + b"branch-name\r\n"), (
            f"{spelling!r} is declared but the walk does not detect it"
        )
