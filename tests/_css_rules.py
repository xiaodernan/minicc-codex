"""A small CSS reader shared by the stylesheet gates.

It answers exactly one question — "which selector declared what" — because that is
all the gates need. There is no cascade simulation, no shorthand expansion and no
at-rule semantics: a ``@media`` body is walked as if it were top level, which is
correct for counting declarations and wrong for deciding which one wins. Gates that
care about precedence say so explicitly and resolve it themselves.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
STYLES = REPO_ROOT / "web" / "styles.css"
ENHANCEMENTS = REPO_ROOT / "web" / "styles-enhancements.css"
SHEETS = (STYLES, ENHANCEMENTS)

PALETTE_SELECTORS = (":root", ':root[data-theme="light"]')


def strip_comments(css: str) -> str:
    out = []
    index = 0
    while index < len(css):
        if css.startswith("/*", index):
            close = css.find("*/", index + 2)
            index = len(css) if close < 0 else close + 2
            out.append("\n")
            continue
        out.append(css[index])
        index += 1
    return "".join(out)


def blocks(text: str) -> list[tuple[str, str]]:
    """Every (prelude, body) pair, descending into at-rules."""
    found: list[tuple[str, str]] = []
    position = 0
    cursor = 0
    while True:
        brace = text.find("{", position)
        if brace < 0:
            break
        prelude = text[cursor:brace].strip()
        depth = 0
        scan = brace
        while scan < len(text):
            if text[scan] == "{":
                depth += 1
            elif text[scan] == "}":
                depth -= 1
                if depth == 0:
                    break
            scan += 1
        body = text[brace + 1 : scan]
        if "{" in body:
            found.extend(blocks(body))
        elif prelude and not prelude.startswith("@"):
            found.append((prelude, body))
        position = scan + 1
        cursor = position
    return found


def declarations(body: str) -> dict[str, str]:
    declared: dict[str, str] = {}
    for chunk in body.split(";"):
        if ":" not in chunk:
            continue
        prop, _, value = chunk.partition(":")
        declared.setdefault(prop.strip().lower(), " ".join(value.split()))
    return declared


@lru_cache(maxsize=None)
def rules(path: Path) -> tuple[tuple[str, tuple[tuple[str, str], ...]], ...]:
    """Every rule in ``path``, in source order, as (selector, declarations) pairs."""
    return tuple(
        (prelude, tuple(declarations(body).items()))
        for prelude, body in blocks(strip_comments(Path(path).read_text(encoding="utf-8")))
    )


def rules_as_dicts(path: Path) -> list[tuple[str, dict[str, str]]]:
    return [(selector, dict(decls)) for selector, decls in rules(path)]


def all_rules() -> list[tuple[Path, str, dict[str, str]]]:
    return [(path, selector, decls) for path in SHEETS for selector, decls in rules_as_dicts(path)]


def palette_declarations(path: Path) -> dict[str, str]:
    """The effective palette of ``path``: every palette block in source order, last wins."""
    resolved: dict[str, str] = {}
    for selector, body in blocks(strip_comments(Path(path).read_text(encoding="utf-8"))):
        if selector not in PALETTE_SELECTORS:
            continue
        for match in re.finditer(r"(--[\w-]+)\s*:\s*([^;]+);", body):
            resolved[match.group(1)] = " ".join(match.group(2).split())
    return resolved


def palette_homes(path: Path, selector: str) -> list[dict[str, str]]:
    """One dict per block that declares ``selector``, in source order."""
    homes: list[dict[str, str]] = []
    for name, body in blocks(strip_comments(Path(path).read_text(encoding="utf-8"))):
        if name == selector:
            homes.append(declarations(body))
    return homes


def effective_palette(path: Path, selector: str) -> dict[str, str]:
    """The palette ``selector`` actually paints: every home folded in source order.

    Deliberately tolerant of duplicates — ``test_each_theme_declares_its_palette_once``
    is the gate that forbids them, so the gates that *read* a palette must keep
    working when one appears, or a single structural break would redden every gate
    at once and hide which one found it.
    """
    resolved: dict[str, str] = {}
    for home in palette_homes(path, selector):
        resolved.update(home)
    return resolved


def resolve(token: str, palette: dict[str, str]) -> str:
    """Follow ``var(--a)`` chains so a gate judges the value that is painted."""
    seen: set[str] = set()
    current = token
    while current in palette and current.startswith("--"):
        assert current not in seen, f"{token} resolves in a cycle through {current}"
        seen.add(current)
        match = re.fullmatch(r"var\(\s*(--[\w-]+)\s*\)", palette[current])
        current = match.group(1) if match else palette[current]
    return current


def linear(channel: int) -> float:
    value = channel / 255
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def luminance(colour: str) -> float:
    digits = colour.lstrip("#")
    assert len(digits) == 6, f"{colour} is not a six-digit hex colour"
    red, green, blue = (int(digits[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * linear(red) + 0.7152 * linear(green) + 0.0722 * linear(blue)


def contrast(one: str, other: str) -> float:
    bright, dark = sorted((luminance(one), luminance(other)), reverse=True)
    return (bright + 0.05) / (dark + 0.05)
