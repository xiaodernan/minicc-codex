"""M8-T700 — the wide face keeps every document reader in its frozen set (main's own re-derivation of M8-T562).

Ported from the sibling lane (t544-plane's batch 542 record, M8-T562), whose
479-name roster froze *that* tree's wide baseline.  This tree is a different
integration lineage with a different reader population, so the roster and the
floors were **re-derived here**, not copied: this gate freezes the nine
tracked test modules that today structurally read the document population
(plus one mention-only pin that belongs in the wide face but not in the
reader census).  The promise and the predicate are unchanged; only the
measured baseline and its provenance are local.

Two promises, standing:

* every name in the frozen set is still a tracked test module — a file leaves
  the wide face only through a conscious edit of the roster, which the batch
  record then has to name;
* every test module that *structurally* reads the document population (a
  ``glob``/``rglob`` of a ``*.md`` literal, or a read of ``DEFAULT_DOCS``) is
  inside the frozen set — a new document-reading gate has to widen the wide
  face in the same batch that lands it.

Admission is structural, not lexical: the predicate pins the ``DEFAULT_DOCS``
assignment and ``glob("*.md")`` as text inside string constants, and a byte
needle would charge it as a reader.  It reads no document, and the last leg
keeps that distinction alive on synthetic sources.

Boundary: the predicate hears a constant pattern only.  ``glob(pattern)`` with
a variable is not guessed at; a reader that builds its pattern at runtime is
outside the census, and the roster is where it gets admitted by hand.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROSTER = REPO / "tests" / "fence_rosters" / "wide.txt"

#: The roster as landed, re-derived for this tree: the document-reader census
#: plus one mention-only pin.  It may only grow by a conscious edit; the
#: floor keeps a truncated file from passing as complete.
WIDE_FLOOR = 9

#: Readers found on the tree this gate landed on.  A floor, not a ledger:
#: the walk below names any reader missing from the roster.
READER_FLOOR = 8

#: One witness per admission reason, so a predicate that goes blind reds here
#: before the census quietly empties.
WITNESSES = {
    "tests/test_doc_pointers.py": ["DEFAULT_DOCS"],
    "tests/test_no_document_quotes_a_content_addressed_bundle.py": ['rglob("*.md")'],
}

#: A gate whose pin only *mentions* a reader shape as a string (a
#: ``monkeypatch.setattr(dp, "DEFAULT_DOCS", ...)`` call's second argument),
#: reading no document.  It belongs to the roster but must stay out of the
#: reader census.
MENTION_ONLY = "tests/test_one_document_is_one_fence_ruler_build.py"


def _tracked() -> list[str]:
    proc = subprocess.run(
        ["git", "-C", str(REPO), "ls-files"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.stdout.splitlines()


def _is_test_module(name: str) -> bool:
    return name.startswith("tests/") and name.endswith(".py")


def _tracked_tests() -> list[str]:
    return [name for name in _tracked() if _is_test_module(name)]


def doc_reader_reasons(source: str) -> list[str]:
    """The shapes by which this source reads the document population."""
    reasons: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Attribute) and node.attr == "DEFAULT_DOCS":
            reasons.add("DEFAULT_DOCS")
        elif isinstance(node, ast.Name) and node.id == "DEFAULT_DOCS":
            reasons.add("DEFAULT_DOCS")
        elif isinstance(node, ast.Call) and node.args:
            func = node.func
            name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
            first = node.args[0]
            if (
                name in {"glob", "rglob"}
                and isinstance(first, ast.Constant)
                and isinstance(first.value, str)
                and "*" in first.value
                and first.value.endswith(".md")
            ):
                reasons.add(f'{name}("{first.value}")')
    return sorted(reasons)


def _read(name: str) -> str:
    return (REPO / name).read_text(encoding="utf-8", errors="replace")


def test_every_file_of_the_wide_baseline_is_still_a_tracked_test() -> None:
    baseline = ROSTER.read_text(encoding="utf-8").splitlines()
    tracked = _tracked()
    assert ROSTER.relative_to(REPO).as_posix() in tracked, (
        "the roster itself is untracked: it is a deliverable, not a local note"
    )
    assert baseline == sorted(baseline), "roster must be sorted; only then can the census be audited"
    assert len(baseline) == len(set(baseline)), "duplicate lines in roster"
    bad = [name for name in baseline if not _is_test_module(name)]
    assert bad == [], f"roster names are not all test modules: {bad[:10]}"
    assert len(baseline) >= WIDE_FLOOR, (
        f"roster has only {len(baseline)} lines, below the {WIDE_FLOOR} it landed with"
    )
    dropped = sorted(set(baseline) - set(tracked))
    assert dropped == [], (
        f"these members of the wide face are no longer tracked test modules: {dropped}. "
        f"the wide face only widens; to drop one, edit the roster and say so in the record"
    )


def test_every_document_reader_is_inside_the_wide_baseline() -> None:
    baseline = set(ROSTER.read_text(encoding="utf-8").splitlines())
    tracked = _tracked_tests()
    reasons: dict[str, list[str]] = {}
    for name in tracked:
        got = doc_reader_reasons(_read(name))
        if got:
            reasons[name] = got

    for name, expected in WITNESSES.items():
        assert name in tracked, f"witness file {name} is not a tracked test"
        assert reasons.get(name) == expected, (
            f"witness {name} reads by {expected}, now by {reasons.get(name)}: "
            f"predicate went blind, or the file no longer reads documents?"
        )
    assert len(reasons) >= READER_FLOOR, (
        f"only {len(reasons)} document readers found, below the {READER_FLOOR} this gate landed with"
    )

    missing = sorted(set(reasons) - baseline)
    assert missing == [], (
        "these tests read docs but are not in the roster (a new reader widens the face in its own batch):\n"
        + "\n".join(f"  {name} -> {reasons[name]}" for name in missing)
    )


def test_a_mention_of_a_reader_is_not_a_reader() -> None:
    samples = (
        ('PIN = \'DEFAULT_DOCS = tuple(sorted((REPO / "docs").glob("*.md")))\'\n', [],
         "a mention inside a string constant is not a read"),
        ("for path in dp.DEFAULT_DOCS:\n    pass\n", ["DEFAULT_DOCS"], "attribute read"),
        ("for path in DEFAULT_DOCS:\n    pass\n", ["DEFAULT_DOCS"], "imported name read"),
        ('for path in DOCS.rglob("*.md"):\n    pass\n', ['rglob("*.md")'], "rglob read"),
        ('for path in ROOT.glob("*.py"):\n    pass\n', [], "glob of non-docs"),
        ("for path in ROOT.glob(pattern):\n    pass\n", [], "non-constant pattern not guessed"),
        ('for path in ROOT.glob("*.md.txt"):\n    pass\n', [], "suffix is not .md"),
    )
    for source, expected, why in samples:
        assert doc_reader_reasons(source) == expected, (
            f"{why}: {source!r} -> {doc_reader_reasons(source)}, expected {expected}"
        )

    shipped = _read(MENTION_ONLY)
    assert "DEFAULT_DOCS" in shipped, (
        f"{MENTION_ONLY} no longer mentions the shape; the pin this test relies on is gone"
    )
    assert doc_reader_reasons(shipped) == [], (
        f"{MENTION_ONLY} only mentions the shape, but the census read it as a reader: {doc_reader_reasons(shipped)}"
    )
    assert MENTION_ONLY in ROSTER.read_text(encoding="utf-8").splitlines(), (
        "the mention-only pin belongs in the wide face: exclusion is about reader identity, not membership"
    )
