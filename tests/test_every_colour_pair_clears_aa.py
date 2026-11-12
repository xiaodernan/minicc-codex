"""Every colour pair the stylesheet declares must clear WCAG AA (M8-T846).

The light theme used Tailwind's 500/600 ramp for accents — ``--mint: #10b981``,
``--amber: #d97706``, ``--coral: #ea580c``. Those work as decoration and fail as
text: mint landed at **2.32:1** on a surface and 2.41:1 on its own tint, amber at
2.86:1, coral at 3.35:1. A third of the light theme's coloured text was below AA,
including every status badge, every file-type label, and the connection indicator.

Two harder-to-see defects came out of the same measurement:

* ``.approval-card-body code`` painted ``--ink`` — the page backdrop — as its text
  colour. In dark mode that is #0f172a on #243447: **1.41:1**, i.e. invisible. A
  light-theme-only override pinned it to ``#1b1b1d``, the retired palette's ink,
  which hid the bug from anyone reviewing light mode.
* ``#292c32`` (the abandoned palette's ``--surface-raised``) was hardcoded as the
  row-hover background in four rules. In the light theme, hovering a task row turned
  it near-black. ``#6a3a31`` and ``#ffb39a`` were hardcoded the same way, so error
  text rendered as pale salmon on cream.

So the gates below measure colour *pairs*, not colours in isolation: a token is only
accessible relative to something. Pairs are taken from the rules that actually set
both a text colour and a background, plus the full text×surface matrix, because a
rule that sets only ``color`` inherits whichever surface its container happens to be.
"""

from __future__ import annotations

import re

import pytest

from tests._css_rules import (
    ENHANCEMENTS,
    SHEETS,
    STYLES,
    contrast,
    effective_palette,
    resolve,
    rules_as_dicts,
    strip_comments,
)

AA = 4.5

# Role assignment, stated once so the gates read as prose: these tokens carry text,
# these carry surfaces, these carry chrome. `--ink` is a surface used *as* text only
# on saturated accents (primary buttons, ::selection), where the pair gate checks it.
TEXT_TOKENS = ("--text", "--muted", "--quiet", "--coral", "--mint", "--amber", "--blue", "--rose", "--purple")
SURFACE_TOKENS = ("--surface", "--surface-raised", "--surface-soft", "--sidebar", "--ink")
CHROME_ONLY = ("--line", "--line-bright")


def _palette(theme: str) -> dict[str, str]:
    base = effective_palette(STYLES, ":root")
    if theme == "light":
        return {**base, **effective_palette(STYLES, ':root[data-theme="light"]')}
    return base


def _token(value: str | None) -> str | None:
    match = re.search(r"var\(\s*(--[\w-]+)\s*\)", value or "")
    return match.group(1) if match else None


def _declared_pairs() -> set[tuple[str, str, str]]:
    """(foreground, background, selector) for every rule that sets both."""
    pairs = set()
    for sheet in SHEETS:
        for selector, decls in rules_as_dicts(sheet):
            foreground = _token(decls.get("color"))
            background = _token(decls.get("background") or decls.get("background-color"))
            if foreground and background:
                pairs.add((foreground, background, selector))
    return pairs


def _hexes(palette: dict[str, str], one: str, other: str) -> tuple[str, str] | None:
    foreground, background = resolve(one, palette), resolve(other, palette)
    if foreground.startswith("#") and background.startswith("#"):
        return foreground, background
    return None


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_declared_foreground_and_background_pairs_clear_aa(theme: str) -> None:
    """Text drawn on a *tinted* block — the pair the matrix gate cannot see.

    Page surfaces are deliberately out of scope here: ``--surface`` and friends are
    covered exhaustively by the matrix gate below, and checking them twice would
    mean a single bad token reddens two gates with no way to tell which one found
    it. What is left is the harder half — accent text on its own tint, and the
    ``--ink``-on-``--coral`` inversion primary buttons rely on.
    """
    palette = _palette(theme)
    failures = []
    for foreground, background, selector in _declared_pairs():
        if background in SURFACE_TOKENS:
            continue
        resolved = _hexes(palette, foreground, background)
        if resolved is None:
            continue
        ratio = contrast(*resolved)
        if ratio < AA:
            failures.append((round(ratio, 2), foreground, background, selector))
    failures.sort()
    assert not failures, (
        f"{theme} theme has {len(failures)} text-on-tint pair(s) below {AA}:1 —\n"
        + "\n".join(f"  {r}:1  {fg} on {bg}  ({sel[:70]})" for r, fg, bg, sel in failures)
    )


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_every_text_token_clears_aa_on_every_page_surface(theme: str) -> None:
    """A rule that sets only ``color`` lands on whichever surface contains it."""
    palette = _palette(theme)
    failures = []
    for foreground in TEXT_TOKENS:
        for background in SURFACE_TOKENS:
            resolved = _hexes(palette, foreground, background)
            if resolved is None:
                continue
            ratio = contrast(*resolved)
            if ratio < AA:
                failures.append((round(ratio, 2), foreground, background))
    failures.sort()
    assert not failures, (
        f"{theme} theme: {len(failures)} text token / surface pair(s) below {AA}:1 —\n"
        + "\n".join(f"  {r}:1  {fg} on {bg}" for r, fg, bg in failures)
    )


def test_a_chrome_token_is_never_used_as_text() -> None:
    """``--line`` is a hairline; painting a glyph in it makes the glyph a hairline."""
    offenders = [
        (selector, decls["color"])
        for sheet in SHEETS
        for selector, decls in rules_as_dicts(sheet)
        if _token(decls.get("color")) in CHROME_ONLY
    ]
    assert not offenders, f"{offenders} paint text in a chrome token"


def test_no_colour_falls_back_to_a_literal() -> None:
    """``var(--mint, #8cd7bd)`` re-states the palette in a second place.

    The fallback is never read while the token exists — which is exactly why it rots
    unnoticed. Both sheets carried four of these, holding the *pre-merge* palette
    values, so the day a token name changed the UI would have silently reverted to a
    palette nobody had looked at in months.
    """
    offenders = []
    for sheet in SHEETS:
        text = strip_comments(sheet.read_text(encoding="utf-8"))
        for match in re.finditer(r"var\(\s*--[\w-]+\s*,\s*([^)]+)\)", text):
            fallback = match.group(1).strip()
            if re.match(r"^(#|rgba?\(|hsla?\()", fallback):
                offenders.append((sheet.name, fallback))
    assert not offenders, f"colour fallbacks re-state the palette: {offenders}"


def test_the_retired_palette_survives_nowhere() -> None:
    """Hardcoded hexes from the abandoned palette are invisible in one theme by design."""
    retired = {
        "#1b1b1d": "--ink",
        "#f0eee9": "--text",
        "#f28d6d": "--coral",
        "#8cd7bd": "--mint",
        "#9cb7f0": "--blue",
        "#e6c279": "--amber",
        "#202023": "--surface",
        "#232326": "--sidebar",
        "#2a2a2f": "--surface-raised",
        "#26262b": "--surface-soft",
        "#292c32": "--surface-raised hover",
        "#2d3037": "--line",
        "#3b3f49": "--line-bright",
        "#6a3a31": "--coral-soft border",
        "#9c9da5": "--muted",
        "#a2a6b0": "--quiet",
        "#412a26": "--coral-soft",
        "#203b35": "--mint-soft",
        "#273246": "--blue-soft",
        "#3b3321": "--amber-soft",
        "#ffb39a": "coral text (dark-only)",
    }
    offenders = []
    for sheet in SHEETS:
        text = strip_comments(sheet.read_text(encoding="utf-8")).lower()
        for hex_value, role in retired.items():
            if hex_value in text:
                offenders.append((sheet.name, hex_value, role))
    assert not offenders, (
        "these literals were correct under the palette retired in M8-T845 and are now "
        f"wrong in one theme: {offenders}"
    )
