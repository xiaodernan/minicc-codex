"""M8-T1273: the system prompt's hand-written almanac catalogue must not drift
from the Rail.

``minicc/prompt.py`` carries a byte-stable world map that includes a manually
transcribed 年鉴 catalogue (roman numeral + Chinese title, one per line). The
Rail itself lives in ``web/src/panels/almanac.js``. Nothing kept the two in
agreement, so across volumes LXXI..LXXIX three facts went stale at once:

* ``年鉴 70 卷``  (count frozen back at volume LXX)
* ``年鉴七十八卷目录`` (header count one behind the source)
* ``卷七十九 等 CI 的那一夜`` (LXXIX's title copied from LXXVII)

The model reads this catalogue every session, so a wrong number or a duplicated
title is a fact the system states about itself that is not true. This test is
the latch: it derives the truth from the Rail and refuses to let the transcript
in ``prompt.py`` disagree.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALMANAC = ROOT / "web" / "src" / "panels" / "almanac.js"
PROMPT = ROOT / "minicc" / "prompt.py"

CATALOG_HEADER = "年鉴七十九卷目录（Almanac · 双语 · 每卷一行）:"
CATALOG_END = "每卷的 en 侧"
COUNT_LINE = "- 年鉴 79 卷（全部双语并存，en 零 CJK 是实测）"


def _rail_entries() -> list[tuple[str, str]]:
    """The source of truth: (roman.zh, title.zh) for every Rail chapter."""
    src = ALMANAC.read_text(encoding="utf-8")
    return re.findall(
        r'roman: \{ zh: "([^"]+)", en: "[^"]+" \}, title: \{ zh: "([^"]+)", en:',
        src,
    )


def _prompt_catalog() -> list[tuple[str, str]]:
    """The hand-written catalogue inside the system prompt's world map."""
    text = PROMPT.read_text(encoding="utf-8")
    assert CATALOG_HEADER in text, "catalogue header drifted — update this test"
    block = text.split(CATALOG_HEADER, 1)[1].split(CATALOG_END, 1)[0]
    entries: list[tuple[str, str]] = []
    for line in block.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) == 2:
            entries.append((parts[0], parts[1]))
    return entries


def test_prompt_catalogue_matches_rail_exactly() -> None:
    rail = _rail_entries()
    catalog = _prompt_catalog()
    assert len(rail) == 79, f"Rail has {len(rail)} chapters, expected 79"
    assert catalog == rail, (
        "system prompt's 年鉴 catalogue drifted from almanac.js — "
        f"first mismatch: "
        + next(
            (f"rail={r!r} prompt={c!r}" for r, c in zip(rail, catalog) if r != c),
            f"length rail={len(rail)} prompt={len(catalog)}",
        )
    )


def test_prompt_count_lines_match_the_rail_count() -> None:
    text = PROMPT.read_text(encoding="utf-8")
    n = len(_rail_entries())
    assert COUNT_LINE in text, (
        f"the 卷数 line must read {COUNT_LINE!r} (Rail has {n})"
    )
    assert CATALOG_HEADER in text, (
        f"the catalogue header must still say {CATALOG_HEADER!r} "
        f"(Rail has {n} chapters)"
    )
