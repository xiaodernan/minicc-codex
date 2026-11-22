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
TOOLTIPS = ROOT / "web" / "src" / "core" / "tooltips.js"
I18N = ROOT / "web" / "src" / "core" / "i18n.js"

CATALOG_END = "每卷的 en 侧"


def _zh_num(n: int) -> str:
    """Chinese numeral for 1..99, enough for any almanac volume count."""
    digits = "零一二三四五六七八九"
    if n < 10:
        return digits[n]
    tens, ones = divmod(n, 10)
    return (digits[tens] + "十" + (digits[ones] if ones else ""))


def _rail_entries() -> list[tuple[str, str]]:
    """The source of truth: (roman.zh, title.zh) for every Rail chapter."""
    src = ALMANAC.read_text(encoding="utf-8")
    return re.findall(
        r'roman: \{ zh: "([^"]+)", en: "[^"]+" \}, title: \{ zh: "([^"]+)", en:',
        src,
    )


def _en_num(n: int) -> str:
    """English words for 100..119 (the Atlas coordinate band)."""
    ones = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
    teens = ["ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
             "sixteen", "seventeen", "eighteen", "nineteen"]
    if 100 <= n <= 119:
        tail = n - 100
        if tail == 0:
            return "one hundred"
        word = teens[tail - 10] if tail >= 10 else ones[tail]
        return f"one hundred {word}"
    return str(n)


def _newest_en_title() -> str:
    """The en title of the newest Rail chapter (for the manual's en blurb)."""
    src = ALMANAC.read_text(encoding="utf-8")
    entries = re.findall(
        r'roman: \{ zh: "[^"]+", en: "[^"]+" \}, title: \{ zh: "[^"]+", en: "([^"]+)"',
        src,
    )
    return entries[-1]


def _prompt_catalog() -> list[tuple[str, str]]:
    """The hand-written catalogue inside the system prompt's world map.

    The header count is derived from the Rail so this latch follows the next
    volume automatically: a forge that adds a chapter in almanac.js but forgets
    to bump the prompt's 目录 header/entries makes this test fail, which is the
    whole point — never the other way round.
    """
    text = PROMPT.read_text(encoding="utf-8")
    header = re.search(r"年鉴[一二三四五六七八九十]+卷目录（Almanac[^\n]*:", text)
    assert header, "catalogue header missing from the system prompt"
    block = text.split(header.group(0), 1)[1].split(CATALOG_END, 1)[0]
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
    assert len(rail) >= 18, f"Rail unexpectedly short: {len(rail)} chapters"
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
    count_line = f"- 年鉴 {n} 卷（全部双语并存，en 零 CJK 是实测）"
    header = f"年鉴{_zh_num(n)}卷目录（Almanac"
    assert count_line in text, (
        f"the 卷数 line must read {count_line!r} (Rail has {n})"
    )
    assert header in text, (
        f"the catalogue header must still say {header!r}… "
        f"(Rail has {n} chapters)"
    )


def test_manual_newest_volume_title_matches_rail() -> None:
    """The manual's 'newest volume' blurb must name the Rail's real newest title.

    Both blurbs once copied LXXIX's title from LXXVII
    (``等 CI 的那一夜`` / ``The Night the CI Answered``), so a reader who
    followed the manual into the almanac saw a title that did not exist.
    Expectations derive from the newest Rail entry, so the next volume's forge
    is checked automatically.
    """
    manual = MANUAL.read_text(encoding="utf-8")
    rail = _rail_entries()
    newest_roman, newest_title = rail[-1]
    # LXXIX's historical wrong title must never come back in either blurb.
    assert "等 CI 的那一夜" not in manual, "the zh manual copied LXXVII's title again"
    assert "The Night the CI Answered" not in manual, "the en manual copied LXXVII's title again"
    assert f"最新卷：{newest_roman}《{newest_title}》" in manual, (
        f"the zh manual blurb must name the newest Rail title {newest_roman}《{newest_title}》"
    )
    newest_en = _newest_en_title()
    assert f'Chapter {len(rail)} “{newest_en}”' in manual or f'“{newest_en}”' in manual, (
        f"the en manual blurb must name the newest Rail title '{newest_en}'"
    )


def test_manual_atlas_counts_match_source() -> None:
    """The en Atlas blurb must carry the current coordinate/volume counts.

    It once said 116/78/twelve while zh + atlas.js said 117/79/13. Derive the
    expected numbers from the Rail so the next volume is checked automatically.
    """
    manual = MANUAL.read_text(encoding="utf-8")
    n = len(_rail_entries())
    current_atlas = n + 38  # 18 panes + n almanac + 20 manual
    assert str(current_atlas - 1) + " real coordinates" not in manual
    assert f"{n - 1} almanac satellites" not in manual
    assert "Islands, twelve" not in manual
    assert f"{_en_num(current_atlas)} real coordinates — 18 panes + {n} almanac satellites + 20 manual satellites" in manual
    assert "the “Islands, thirteen” drawer" in manual


def test_onboarding_zh_almanac_step_matches_rail_count() -> None:
    """The zh onboarding step must reach the Rail's current volume count.

    It once said 卷七十八 while its own en twin said 79. Derived from the Rail
    so the next volume is checked automatically.
    """
    onboarding = ONBOARDING.read_text(encoding="utf-8")
    n = len(_rail_entries())
    assert "卷一到卷七十八" not in onboarding
    assert f"卷一到卷{_zh_num(n)}" in onboarding, (
        f"the zh onboarding almanac step must reach 卷{n} (Rail has {n})"
    )


def test_synced_chapter_instruments_bumped_to_current_coordinate() -> None:
    """The recent synced window must carry the current Atlas/volume reading.

    Discipline (CHANGELOG: 前十四卷仪表同步 116/78, etc.): on each volume the
    recent window of chapters is bumped to the current coordinate, while older
    chapters keep their intentional historical snapshot (Atlas 54..101,
    volumes 23..63). LXXIX landed at Atlas 117 / 79 volumes but left 15
    synced-window chapters baking the just-superseded 116 / 78, so the same
    almanac showed two different 'current' readings.

    This latch forbids only the immediately-stale values (116 / 78) and pins
    that the current ones (117 / 79) appear across the synced window; it leaves
    the older historical snapshots alone.
    """
    src = ALMANAC.read_text(encoding="utf-8")
    n = len(_rail_entries())
    current_atlas = n + 38          # 18 panes + n almanac + 20 manual
    prev_atlas = current_atlas - 1  # the just-superseded coordinate (116)
    atlas_values = re.findall(
        r'"Atlas coordinates"\}</div><div class="almanac-instrument-value">(\d+)</div>',
        src,
    )
    assert atlas_values, "no Atlas coordinate instruments found"
    assert str(prev_atlas) not in atlas_values, (
        f"stale Atlas coordinate {prev_atlas} still baked in some chapters"
    )
    assert atlas_values.count(str(current_atlas)) >= 15, (
        f"expected the synced window (>=15 chapters) to read Atlas {current_atlas}"
    )
    volume_values = re.findall(
        r'"Volumes, both sides"\}</div><div class="almanac-instrument-value">(\d+) / (\d+)</div>',
        src,
    )
    assert volume_values, "no volume instruments found"
    assert not any(str(n - 1) in pair for pair in volume_values), (
        f"stale volume count {n - 1} still baked in some chapters"
    )
    assert sum(1 for pair in volume_values if pair == (str(n), str(n))) >= 15, (
        f"expected the synced window (>=15 chapters) to read {n} / {n}"
    )


def test_teaching_tooltips_carry_current_volume_and_coordinate_counts() -> None:
    """The sidebar teaching tooltips must not freeze an old world count.

    They once read ``年鉴 70 卷`` / ``117 real coordinates`` while the Rail was
    at 79 and Atlas at 117. Both are the numbers a first-time visitor reads
    on hover, so a stale one is a false fact stated by the UI itself. Derived
    from the Rail so the next forge is checked automatically.
    """
    tips = TOOLTIPS.read_text(encoding="utf-8")
    n = len(_rail_entries())
    atlas = n + 38  # 18 panes + n almanac + 20 manual
    assert f"年鉴：{n} 卷双语世界叙事" in tips
    assert f"Almanac: {n} bilingual volumes of the world" in tips
    assert f"{atlas} 个真实坐标" in tips
    assert f"{atlas} real coordinates" in tips
    # the just-superseded readings must never come back
    assert "70 卷" not in tips and "70 bilingual" not in tips
    assert "117 个真实坐标" not in tips and "117 real coordinates" not in tips


def test_session_empty_chip_carries_current_coordinate_count() -> None:
    """The empty-session hint's coordinate count must follow the Atlas."""
    i18n = I18N.read_text(encoding="utf-8")
    n = len(_rail_entries())
    atlas = n + 38
    assert f"打开世界地图——{atlas} 个真实坐标随便点" in i18n
    assert f"Open the world map — {atlas} real coordinates to tap" in i18n
    assert "117 个真实坐标" not in i18n
    assert "117 real coordinates" not in i18n


def test_onboarding_zh_atlas_step_matches_its_en_twin_counts() -> None:
    """The zh onboarding Atlas step once said 117/79 while en said 119/81.

    Both languages must state the Rail's current volume count and the Atlas'
    current coordinate total; a mixed pair is exactly the '中英文夹杂 + 数字
   不准' the manual promises never to ship.
    """
    onboarding = ONBOARDING.read_text(encoding="utf-8")
    n = len(_rail_entries())
    atlas = n + 38
    assert f"{atlas} 个坐标" in onboarding
    assert f"{n} 卷年鉴卫星" in onboarding
    assert f"{_en_num(atlas)} real coordinates" in onboarding
    assert "117 个坐标" not in onboarding
    assert "79 卷年鉴卫星" not in onboarding


def test_prompt_atlas_feature_line_matches_current_coordinate() -> None:
    """The prompt's feature inventory must state the Atlas' current total.

    It read ``116 个 Canvas 坐标`` long after the Rail reached 81 volumes /
    119 coordinates. The model reads this inventory every session, so a stale
    coordinate there is a fact the system asserts about itself that is false.
    Derived from the Rail so the next forge is checked automatically.
    """
    text = PROMPT.read_text(encoding="utf-8")
    n = len(_rail_entries())
    atlas = n + 38
    assert f"13 座岛屿、{atlas} 个 Canvas 坐标" in text
    assert f"Atlas {atlas} / {n} 卷" in text
    assert "116 个 Canvas 坐标" not in text
    assert "Atlas 116 / 78 卷" not in text
