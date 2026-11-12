"""The palette is one fact per theme (M8-T845).

``web/styles.css`` opened with a warm editorial palette — ``--coral: #f28d6d``,
``--text: #f0eee9`` — and then, 1900 lines later, opened again under the banner
"modern palette" and redefined 20 of those 26 dark tokens and 18 light ones. The
second block was not an extension; it was a replacement that nothing announced. A
browser probe settled the argument: ``--coral`` computed to rgb(251, 146, 60), the
value of the palette the reader never reached.

Two consequences worth guarding, and both are cheaper to check here than to notice
in production:

* a token answered twice means a designer editing the first block edits nothing;
* a *colour* answered only in ``:root`` means light mode silently inherits a dark
  colour — the kind of defect that looks like a rendering glitch, not a bug.
"""

from __future__ import annotations

import re

import pytest

from tests._css_rules import (
    PALETTE_SELECTORS,
    STYLES,
    effective_palette,
    palette_homes,
    rules_as_dicts,
)


def _colours(decls: dict[str, str]) -> dict[str, str]:
    return {
        token: value
        for token, value in decls.items()
        if re.match(r"^(#[0-9a-fA-F]{3,8}|rgba?\(|hsla?\(|color-mix\()", value)
    }


@pytest.mark.parametrize("selector", PALETTE_SELECTORS, ids=["dark", "light"])
def test_each_theme_declares_its_palette_once(selector: str) -> None:
    homes = palette_homes(STYLES, selector)
    assert len(homes) == 1, (
        f"`{selector}` is declared {len(homes)} times in styles.css; the later block "
        "replaces the earlier one token by token, so the first is documentation "
        "describing colours the product does not paint"
    )


def test_light_mode_never_inherits_a_dark_colour() -> None:
    """A colour only in ``:root`` is a dark colour that light mode will happily use."""
    dark = _colours(effective_palette(STYLES, ":root"))
    light = _colours(effective_palette(STYLES, ':root[data-theme="light"]'))
    only_dark = sorted(set(dark) - set(light))
    only_light = sorted(set(light) - set(dark))
    assert not only_dark, (
        f"{only_dark} are colours declared only for the dark theme; the light theme "
        "inherits them verbatim because the palette is inherited, not re-derived"
    )
    assert not only_light, (
        f"{only_light} are colours declared only for the light theme; they have no "
        "dark counterpart, so the dark theme renders them as unset"
    )


def test_no_component_re_answers_a_palette_token() -> None:
    """``.card { --coral: red }`` is a third home for a theme question, invisibly."""
    palette_tokens = set(effective_palette(STYLES, ":root")) | set(
        effective_palette(STYLES, ':root[data-theme="light"]')
    )
    stray = [
        (selector, token)
        for selector, decls in rules_as_dicts(STYLES)
        if selector not in PALETTE_SELECTORS
        for token in decls
        if token in palette_tokens
    ]
    assert not stray, (
        f"{stray} re-declare palette tokens inside component rules; the value only "
        "applies to that subtree, so the same token means two things at once"
    )


RUNTIME_TOKENS = {"--seed-cooldown", "--app-height", "--viewport-top"}


def test_the_palette_covers_the_roles_components_ask_for() -> None:
    """Every ``var(--token)`` in either sheet must be answered somewhere."""
    from tests._css_rules import REPO_ROOT, SHEETS, blocks, strip_comments

    defined = set()
    referenced = set()
    for path in SHEETS:
        text = path.read_text(encoding="utf-8")
        for _selector, body in blocks(strip_comments(text)):
            defined.update(re.findall(r"(--[\w-]+)\s*:", body))
            referenced.update(re.findall(r"var\(\s*(--[\w-]+)", body))
    missing = sorted(referenced - defined - RUNTIME_TOKENS)
    assert not missing, (
        f"{missing} are read with var() but declared nowhere in css or js; the "
        "declaration using them is invalid at computed-value time and silently falls "
        "back to the property's initial value"
    )

    # The exemption list is a claim about JavaScript, so hold it to one. Match on a
    # token boundary: `--seed-cooldown` is a prefix of `--seed-cooldown-unused`, and a
    # substring test would keep the exemption alive after its writer was renamed.
    scripts = list((REPO_ROOT / "web" / "src").rglob("*.js")) + [REPO_ROOT / "web" / "index.html"]
    written_from_js = {
        token
        for token in RUNTIME_TOKENS
        if any(re.search(re.escape(token) + r"(?![\w-])", source.read_text(encoding="utf-8")) for source in scripts)
    }
    assert written_from_js == RUNTIME_TOKENS, (
        f"{sorted(RUNTIME_TOKENS - written_from_js)} are exempted from "
        "declaration but nothing writes them; the exemption hides a dead var()"
    )
