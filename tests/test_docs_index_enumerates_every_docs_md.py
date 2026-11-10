import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
INDEX = _ROOT / "docs" / "INDEX.md"
DOCS_DIR = _ROOT / "docs"


def test_every_docs_md_is_reachable_from_docs_index() -> None:
    """Index vs filesystem agreement, one take.

    The README points readers to docs/INDEX.md as the hand-held map. Any
    new docs/*.md dropped in but not registered is unreachable there —
    which loses the doc from the whole catalog. One entry in INDEX per
    tracked doc, enforced here instead of resting on operator discipline.
    """
    index_text = INDEX.read_text(encoding="utf-8", errors="replace")
    #: Docs *.md files the gate expects to be enumerated.
    local_docs = sorted(DOCS_DIR.glob("*.md"))
    assert local_docs, "docs/ should not be empty in this repo"
    missing: list[str] = []
    for doc in local_docs:
        if doc.name == "INDEX.md":
            continue  # the index itself is not required to link to itself
        #: INDEX.md uses [path](path) style links; the target basename is
        #: enough. Some docs go by their plainstem rather than path.
        if doc.name not in index_text and doc.stem not in index_text:
            missing.append(doc.name)
    assert missing == [], (
        "docs/INDEX.md does not name every docs/*.md it ships:"
        + "\n".join(f"  - {name}" for name in missing)
        + "\nAdd an entry in INDEX.md."
    )
