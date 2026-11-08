"""M8-T554: how deep a body's copy may be and still come back is a measured law.

M8-T553 folded the *entity* spellings of the four block markers, so a body that
writes ``&#91;truncated&#93;`` gets its own bytes back after one decode.  The
sentence M8-T551 put into that explanation - ``each folds back for a reader`` -
claimed the fold returns the body's bytes for **every** token.  It does not, and
nothing in the repo measured past one depth: a file can write a *deeper* copy than the table
reaches, and the table has a reach.  Only depth 2 was pinned anywhere (batch 536's
``test_a_body_at_the_second_level_lands_one_level_up``).

This file sweeps all four markers through the depths a body can write - the raw
marker, the entity spelling, and every spelling past the table's reach built with
the same ampersand fold the table's own second rows use - and pins what a single
decode leaves.  The law is: levels 0 and 1 come back byte for byte; a body at
level ``d >= 2`` lands at ``d - 1``, never lower and never a raw marker, and the
block stays one ``<file>`` element the whole way.  One more leg pins the two
designs this batch measured and rejected (a wider table, and folding ``&`` whole),
and two read ``_body``'s own explanation, because a claim about a measured boundary
has to say where the boundary is and which leg measures it.
"""

from __future__ import annotations

import html.parser
import pathlib
import xml.etree.ElementTree as ET
from typing import Any

import minicc.mentions as _mentions_module
from minicc.mentions import build_mention_context

THIS_FILE = "test_a_body_that_writes_a_deeper_spelling_lands_one_level_up.py"

RAW_ORDER = ("</file", "<file", "[用户引用文件]", "[truncated]")

DEPTH_SWEPT = (0, 1, 2, 3, 4)

BODY = "line one\n{}\nline two\n"


class _Files(html.parser.HTMLParser):
    """Reader 1: a forgiving tag scanner that decodes character references."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.paths: list[str] = []
        self.texts: list[str] = []
        self._inside: bool = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "file":
            return
        data: dict[str, Any] = {key: value for key, value in attrs}
        self.paths.append(str(data.get("path", "?")))
        self.texts.append("")
        self._inside = True

    def handle_data(self, data: str) -> None:
        if self._inside:
            self.texts[-1] += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "file":
            self._inside = False


def _keys() -> dict[str, str]:
    """``{needle: replacement}`` read off the module's own table, in order."""
    return dict(_mentions_module._STRUCTURAL_TOKENS)


def _fold_of(raw: str) -> str:
    """What the module folds ``raw`` to right now (one lookup, no copy)."""
    keys = _keys()
    assert raw in keys, (sorted(keys), raw)
    return keys[raw]


def _amp(text: str) -> str:
    """The one substitution every entity row of the table is built from."""
    return text.replace("&", "&amp;")


def _spelling(raw: str, depth: int) -> str:
    """The marker a body must write to sit at ``depth``.

    Level 0 is the raw marker; the next level is whatever the table turns the
    current one into; past the table's reach the same ampersand fold the table's
    own entity rows use keeps going - so every body here is a spelling a file can
    actually hold, not an example invented in this file.
    """
    keys = _keys()
    text = raw
    for _ in range(depth):
        text = keys[text] if text in keys else _amp(text)
    return text


def _render(tmp_path: pathlib.Path, body: str, name: str = "f.txt", **kwargs: Any):
    (tmp_path / name).write_text(body, encoding="utf-8", newline="\n")
    return build_mention_context(f"@{name}", tmp_path, **kwargs)


def _element_text(block: str) -> str:
    """The decoded text of the one ``<file>`` element, from both pinned readers."""
    reader = _Files()
    reader.feed(block)
    reader.close()
    assert reader.paths == ["f.txt"], reader.paths
    root = ET.fromstring("<root>" + block + "</root>")
    files = list(root.iter("file"))
    assert len(files) == 1, len(files)
    assert reader.texts[0] == files[0].text, (reader.texts[0], files[0].text)
    return reader.texts[0]


def test_the_deeper_rows_are_the_same_ampersand_fold():
    """The ladder this file sweeps is the module's, not a hand-written one: the
    table's second row is the ampersand fold of the spelling its first row
    emits, for every marker - which is what makes ``_spelling`` below the
    table's own rule continued, rather than an example invented here."""
    keys = _keys()
    for raw in RAW_ORDER:
        first = keys[raw]
        assert first in keys, (raw, first, sorted(keys))
        second = keys[first]
        assert first == _fold_of(raw), (raw, first)
        assert second == _amp(first), (raw, first, second, keys)


def test_a_body_at_level_zero_or_one_decodes_back_to_its_own_bytes(tmp_path):
    """Where the identity holds: a body that writes the raw marker, or the folded
    spelling of it, gets exactly those bytes back from one decode."""
    for raw in RAW_ORDER:
        for depth in (0, 1):
            written = _spelling(raw, depth)
            text = BODY.format(written)
            block, records = _render(tmp_path, text)
            assert _element_text(block) == f"\n{text}\n", (raw, depth, block[:120])
            assert [r["truncated"] for r in records] == [False], records


def test_a_body_deeper_than_the_table_lands_exactly_one_level_up(tmp_path):
    """Where the identity stops: past the table's reach the block carries the
    body's bytes unchanged, so one decode raises the reader one level and no
    further.  Never a raw marker - but not the file's own bytes either."""
    for raw in RAW_ORDER:
        for depth in (2, 3, 4):
            written = _spelling(raw, depth)
            landed = _spelling(raw, depth - 1)
            block, _ = _render(tmp_path, BODY.format(written))
            decoded = _element_text(block)
            assert decoded == f"\n{BODY.format(landed)}\n", (raw, depth, decoded)
            assert written not in decoded, (raw, depth, decoded)
            assert raw not in decoded, (raw, depth, decoded)


def test_no_level_leaves_a_raw_marker_in_the_block(tmp_path):
    """The byte axis, at every level: however deep the body's copy is, the block
    carries the raw marker only where the renderer wrote it."""
    control, _ = _render(tmp_path, "one\ntwo\n")
    baseline = {raw: control.count(raw) for raw in RAW_ORDER}
    assert baseline["[truncated]"] == 0, baseline
    for raw in RAW_ORDER:
        for depth in DEPTH_SWEPT:
            block, records = _render(tmp_path, BODY.format(_spelling(raw, depth)))
            assert block.count(raw) == baseline[raw], (raw, depth, block[:120])
            assert [r["truncated"] for r in records] == [False], records


def test_every_level_keeps_the_block_one_file_element(tmp_path):
    """The structure axis: none of the twenty swept blocks invents a second
    element, loses the injected one, or fails to parse for the strict reader."""
    for raw in RAW_ORDER:
        for depth in DEPTH_SWEPT:
            block, _ = _render(tmp_path, BODY.format(_spelling(raw, depth)))
            root = ET.fromstring("<root>" + block + "</root>")
            files = list(root.iter("file"))
            assert len(files) == 1, (raw, depth, block[:120])
            assert files[0].get("path") == "f.txt", (raw, depth, files[0].attrib)


def test_the_fold_owns_no_bare_ampersand_and_reaches_no_further():
    """The two designs this batch measured and did not take, priced in one leg.

    Folding ``&`` wholesale - the attribute side's first move - would make the
    identity level-independent, at the cost of rewriting every ``&amp;`` and
    ``&nbsp;`` a body already holds, and of reddening the floors the earlier gates
    put on bodies keeping their bytes.  A wider table, one row per deeper level,
    would push the boundary up exactly one level and leave the bodies past it where
    they were.  Both were rendered and run against the gates that read this table;
    both stay out, and this leg is what keeps them out.
    """
    keys = _keys()
    assert "&" not in keys, sorted(keys)
    assert len(keys) == 8, sorted(keys)
    for raw in RAW_ORDER:
        assert _spelling(raw, 3) not in keys, (raw, sorted(keys))
        assert _spelling(raw, 3) != _spelling(raw, 2), raw


def test_the_explanation_says_where_the_identity_stops():
    """``_body`` used to claim the fold returns a body's bytes for every token.
    The law is narrower, so the explanation has to name the level it stops at and
    what happens past it - in the same place the claim is made."""
    doc = _mentions_module._body.__doc__ or ""
    assert "levels 0 and 1" in doc, doc
    assert "one level up" in doc, doc
    assert "each folds back" not in doc, doc


def test_the_explanation_names_the_leg_that_measures_the_law():
    """A measured boundary in a shipped comment rots unless a reader is named."""
    doc = _mentions_module._body.__doc__ or ""
    assert THIS_FILE in doc, doc
