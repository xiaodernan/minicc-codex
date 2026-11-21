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
MANUAL = ROOT / "web" / "src" / "panels" / "manual.js"
ONBOARDING = ROOT / "web" / "src" / "panels" / "onboarding.js"

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


def test_manual_newest_volume_title_matches_rail() -> None:
    """The manual's 'newest volume' blurb must name LXXIX's real title.

    Both the zh and en blurbs had LXXIX's title copied from LXXVII
    (``等 CI 的那一夜`` / ``The Night the CI Answered``), so a reader who
    followed the manual into the almanac saw a title that did not exist.
    """
    manual = MANUAL.read_text(encoding="utf-8")
    rail = _rail_entries()
    newest_roman, newest_title = rail[-1]
    assert newest_roman == "卷七十九", f"unexpected newest roman: {newest_roman}"
    assert f"最新卷：{newest_roman}《{newest_title}》" in manual, (
        "the zh manual blurb must name the newest volume's real title"
    )
    assert "The Night the CI Answered" not in manual.split("seventy-nine chapters", 1)[-1][:400], (
        "the en manual blurb must not copy LXXVII's title onto LXXIX"
    )
    assert 'Chapter LXXIX “The Night the Route Was Chosen”' in manual, (
        "the en manual blurb must name LXXIX's real title"
    )


def test_manual_atlas_counts_match_source() -> None:
    """The en Atlas blurb had 116/78/twelve while zh + atlas.js say 117/79/13."""
    manual = MANUAL.read_text(encoding="utf-8")
    assert "one hundred sixteen real coordinates" not in manual
    assert "78 almanac satellites" not in manual
    assert "Islands, twelve" not in manual
    assert "one hundred seventeen real coordinates — 18 panes + 79 almanac satellites + 20 manual satellites" in manual
    assert "the “Islands, thirteen” drawer" in manual


def test_onboarding_zh_almanac_step_matches_rail_count() -> None:
    """The zh onboarding step said 卷七十八 while its own en twin said 79."""
    onboarding = ONBOARDING.read_text(encoding="utf-8")
    n = len(_rail_entries())
    assert "卷一到卷七十八" not in onboarding
    assert "卷一到卷七十九" in onboarding, (
        f"the zh onboarding almanac step must reach 卷{n} (Rail has {n})"
    )
