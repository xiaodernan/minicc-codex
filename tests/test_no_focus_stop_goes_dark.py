"""A keyboard user must be able to see where they are (M8-T844).

The stylesheet used to answer "what does focus look like" in three places and to
suppress the answer in nine others:

* ``styles.css`` declared the universal ring twice, with different offsets;
* ``styles-enhancements.css`` — which loads *after* ``styles.css`` — declared it a
  third time in blue, so the shipped ring colour was whichever file loaded last;
* ``outline: 0`` / ``outline: none`` rules outranked the universal ``*:focus-visible``
  rule on specificity, so tabbing onto a task row, a workspace row, a search result,
  an auth field, the sidebar search box, a batch field, a workspace/worktree name
  field, or either settings dropdown painted nothing at all.

The invariant these gates hold: **no rule may silence a focus stop unless it (or a
declared ancestor) paints the shared ring**. "Silence" is any ``outline: 0`` /
``outline: none`` landing on something that can take focus; "the shared ring" is
``var(--focus-ring)`` / ``var(--focus-ring-inset)``, whose colour, width and offset
have exactly one home.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests._css_rules import (
    SHEETS,
    STYLES,
    all_rules,
    contrast,
    palette_homes,
    resolve,
    rules_as_dicts,
)

UNIVERSAL_FOCUS_SELECTOR = "*:focus-visible"
RING_TOKENS = ("var(--focus-ring)", "var(--focus-ring-inset)")
RING_DECLARATIONS = ("--focus-ring-color", "--focus-ring-width", "--focus-ring-offset")

# The only controls allowed to hand their ring to a container. In each case the
# control has no chrome of its own (transparent background, no border), so a ring
# drawn on the bare control would float inside the box that already looks focused.
# The value must be a real rule in the sheet that paints the shared ring.
DELEGATED_RINGS = {
    ".sidebar-search input": ".sidebar-search:focus-within",
    ".composer-shell textarea": ".composer-shell:focus-within",
    ".global-search-box input": ".global-search-box:focus-within",
}

FOCUSABLE_TYPES = frozenset(
    {"input", "textarea", "select", "button", "a", "summary", "details", "iframe", "audio", "video"}
)


def _rightmost_compound(selector: str) -> str:
    last = selector.split(",")[-1].strip()
    parts = [part for part in re.split(r"[\s>+~]+", last) if part]
    return parts[-1] if parts else ""


def _is_focus_stop(selector: str) -> bool:
    """A compound that can take focus: a focusable tag, or an explicit focus state."""
    compound = _rightmost_compound(selector)
    if ":focus" in compound:
        return True
    tag = re.match(r"[a-z]+", compound.lower())
    return bool(tag) and tag.group(0) in FOCUSABLE_TYPES


def _silences(decls: dict[str, str]) -> bool:
    return decls.get("outline", "").replace(" ", "") in {"0", "none"}


def _paints_ring(decls: dict[str, str]) -> bool:
    shadow = decls.get("box-shadow", "")
    return any(token in shadow for token in RING_TOKENS)


def _specificity(selector: str) -> tuple[int, int, int]:
    compound = _rightmost_compound(selector)
    ids = len(re.findall(r"#[\w-]+", compound))
    classes = len(re.findall(r"\.[\w-]+|\[[^\]]*\]|:(?!:)[\w-]+", compound))
    stripped = re.sub(r"#[\w-]+|\.[\w-]+|\[[^\]]*\]|::?[\w-]+(?:\([^)]*\))?", " ", compound)
    elements = len(re.findall(r"[a-zA-Z][\w-]*", stripped))
    return ids, classes, elements


def _normalised(selector: str) -> str:
    """The suppression target, with any trailing focus state folded away."""
    return re.sub(r":focus(-visible|-within)?\s*$", "", selector.split(",")[-1].strip())


# --------------------------------------------------------------------------- #
# Gates
# --------------------------------------------------------------------------- #


def test_the_ring_has_exactly_one_home() -> None:
    """Every other sheet may *use* the ring; only ``styles.css`` may define it."""
    declarations = [
        (path, selector, prop)
        for path, selector, decls in all_rules()
        for prop in RING_DECLARATIONS
        if prop in decls
    ]
    homes = {selector for _, selector, _ in declarations}
    assert homes == {":root"}, (
        "the focus ring must be declared once, in the :root palette; found "
        f"{sorted(homes)} — a second palette silently re-answers the same question"
    )
    assert {path for path, _, _ in declarations} == {STYLES}
    assert {prop for _, _, prop in declarations} == set(RING_DECLARATIONS)


def test_the_universal_rule_appears_once_and_uses_the_ring() -> None:
    """Two ``*:focus-visible`` rules are not belt and braces — they are a conflict."""
    universal = [
        (path, decls)
        for path, selector, decls in all_rules()
        if selector == UNIVERSAL_FOCUS_SELECTOR
    ]
    assert len(universal) == 1, (
        f"{UNIVERSAL_FOCUS_SELECTOR} is declared {len(universal)} times in "
        f"{[path.name for path, _ in universal]}; the later sheet silently wins"
    )
    path, decls = universal[0]
    assert path == STYLES
    assert decls.get("outline") == "var(--focus-ring-width) solid var(--focus-ring-color)"
    assert decls.get("outline-offset") == "var(--focus-ring-offset)"


@pytest.mark.parametrize("path", SHEETS, ids=lambda p: Path(p).name)
def test_no_rule_silences_a_focus_stop(path: Path) -> None:
    """Silencing anything focusable is legal only where a ring replaces it.

    One invariant with two entrances, deliberately not two assertions:
    ``:focus-visible``-carrying rules that repaint nothing, and base rules whose
    ``outline: 0`` simply outranks the universal rule on specificity. Both end the
    same way — a keyboard user tabbing onto that control sees nothing move.
    """
    silent = []
    for selector, decls in rules_as_dicts(path):
        if not _silences(decls) or _paints_ring(decls):
            continue
        for part in selector.split(","):
            part = part.strip()
            if not _is_focus_stop(part) or _normalised(part) in DELEGATED_RINGS:
                continue
            silent.append((part, _specificity(part)))
    assert not silent, (
        f"{path.name} zeroes the outline on focusable controls that nothing repaints: "
        f"{silent} (ids, classes, elements) — the universal *:focus-visible rule has "
        "specificity (0,1,0) and cannot win against any of them"
    )


def test_every_delegated_ring_names_a_rule_that_actually_paints() -> None:
    """The delegation table is a promise; an unpainted container breaks it silently."""
    paints = {selector for _, selector, decls in all_rules() if _paints_ring(decls)}
    for control, container in DELEGATED_RINGS.items():
        assert container in paints, (
            f"{control} hands its ring to {container}, but no such rule paints "
            "var(--focus-ring) — the control would be unreachable by keyboard"
        )


def test_the_delegation_table_has_no_stale_entries() -> None:
    """A delegation for a control that no longer exists hides the next real defect."""
    silencers = {
        _normalised(selector)
        for path in SHEETS
        for selector, decls in rules_as_dicts(path)
        if _silences(decls)
    }
    stale = sorted(set(DELEGATED_RINGS) - silencers)
    assert not stale, f"DELEGATED_RINGS lists controls that no longer silence anything: {stale}"


# --------------------------------------------------------------------------- #
# The ring has to be visible, not merely present (WCAG 2.1 SC 1.4.11: 3:1).
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_the_ring_is_visible_against_the_surface_it_sits_on(theme: str) -> None:
    """A ring in the right place but a shade off the background is still invisible."""
    palette = palette_homes(STYLES, ":root")[0]
    if theme == "light":
        palette = {**palette, **palette_homes(STYLES, ':root[data-theme="light"]')[0]}
    ring = resolve("--focus-ring-color", palette)
    surfaces = {name: resolve(name, palette) for name in ("--surface", "--surface-raised", "--sidebar")}
    for name, value in surfaces.items():
        assert contrast(ring, value) >= 3.0, (
            f"{theme}: the focus ring {ring} sits on {name} {value} at "
            f"{contrast(ring, value):.2f}:1 — WCAG 1.4.11 wants at least 3:1"
        )
