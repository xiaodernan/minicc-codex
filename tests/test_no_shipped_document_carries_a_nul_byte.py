"""M8-T843: shipped documents must be readable text, not binary with a .md suffix.

A NUL byte is not cosmetic. ``grep`` classifies the whole file as binary and stops
printing matches, so `grep '^## 批次' docs/ROADMAP_TO_PRODUCT.md` silently stopped
listing the newest batches - the ledger was still there, the tool just refused to
show it. That happened for real: an escape sequence written through a shell layer
arrived as a genuine NUL in two lines of batch 841.

U+FFFD is different: it is legitimate when the prose is *about* replacement
characters. One batch quotes the character it discusses, so this gate allows a
budget of two and fails on any growth. Everything else must be clean.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REPLACEMENT = chr(0xFFFD)

#: The batch that quotes U+FFFD while explaining how GBK stdout breaks a UTF-8
#: reader. Both occurrences sit inside that paragraph, next to this marker.
QUOTED_REPLACEMENT_BUDGET = 2
QUOTED_REPLACEMENT_ANCHOR = "UnicodeEncodeError"


def _documents() -> list[Path]:
    docs = sorted((REPO_ROOT / "docs").glob("**/*.md"))
    readme = REPO_ROOT / "README.md"
    return ([readme] if readme.exists() else []) + docs


def test_no_shipped_document_carries_a_nul_byte() -> None:
    offenders: list[str] = []
    for path in _documents():
        raw = path.read_bytes()
        nul = raw.count(b"\x00")
        if nul:
            first = raw.index(b"\x00")
            offenders.append(f"{path.relative_to(REPO_ROOT).as_posix()} ({nul} NUL, first at byte {first})")
    assert offenders == [], "documents grep would refuse to print: " + "; ".join(offenders)


def test_every_shipped_document_is_utf8() -> None:
    broken: list[str] = []
    for path in _documents():
        try:
            path.read_bytes().decode("utf-8")
        except UnicodeDecodeError as exc:
            broken.append(f"{path.relative_to(REPO_ROOT).as_posix()}: {exc}")
    assert broken == [], broken


def test_replacement_characters_stay_inside_the_batch_that_discusses_them() -> None:
    unexpected: list[str] = []
    for path in _documents():
        text = path.read_bytes().decode("utf-8")
        count = text.count(REPLACEMENT)
        if not count:
            continue
        label = path.relative_to(REPO_ROOT).as_posix()
        if label != "docs/ROADMAP_TO_PRODUCT.md":
            unexpected.append(f"{label}: {count} U+FFFD")
            continue
        if count > QUOTED_REPLACEMENT_BUDGET:
            unexpected.append(
                f"{label}: {count} U+FFFD, budget is {QUOTED_REPLACEMENT_BUDGET} "
                "(mojibake came back; fix the text instead of raising the budget)"
            )
            continue
        # Budgeted characters must still be the quoted ones, not new damage that
        # happens to keep the count under the budget.
        for index, char in enumerate(text):
            if char != REPLACEMENT:
                continue
            window = text[max(0, index - 400):index + 400]
            if QUOTED_REPLACEMENT_ANCHOR not in window:
                unexpected.append(
                    f"{label}: U+FFFD at {index} is not inside the encoding discussion"
                )
                break
    assert unexpected == [], unexpected
