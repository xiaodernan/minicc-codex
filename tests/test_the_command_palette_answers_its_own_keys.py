"""M8-T893/T894 — the command palette and desktop notifications answer their own keys.

The palette builds i18n keys by *construction* — ``palette.cmd.${id}`` and
``palette.group.${segment}`` — so a renamed group segment or a key added to
one locale but not the other fails silently: ``t()`` falls back to the key
itself, and users read raw ``palette.group.group`` instead of a label. That
exact bug shipped in the first build of the palette (``split(".")[1]`` took
the wrong segment) and no gate noticed.

This gate pins:

* every key the palette/notify faces *request* exists in BOTH the zh and en
  columns of ``web/src/core/i18n.js`` — no half-translated surface;
* the constructed key families (``palette.cmd.*``, ``palette.group.*``) are
  exactly the declared ones, so a segment rename cannot drift;
* the combobox/listbox contract stays in ``index.html`` — input controls the
  list, the list is a listbox, and the modal ships closed;
* ``notifyTaskFinished`` is hooked exactly once, inside the one terminal
  home (``completeTask``), and nowhere else.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
I18N = REPO / "web" / "src" / "core" / "i18n.js"
PALETTE = REPO / "web" / "src" / "core" / "command-palette.js"
NOTIFY = REPO / "web" / "src" / "core" / "notify.js"
API = REPO / "web" / "src" / "core" / "api.js"
STREAM = REPO / "web" / "src" / "chat" / "stream.js"
INDEX = REPO / "web" / "index.html"


def _columns() -> tuple[set[str], set[str]]:
    source = I18N.read_text(encoding="utf-8")
    zh_match = re.search(r"zh: \{(.*?)\n  \},\n  en: \{", source, re.S)
    en_match = re.search(r"  en: \{(.*?)\n  \},\n\}", source, re.S)
    assert zh_match and en_match, "i18n.js no longer parses as a zh/en pair"
    zh = set(re.findall(r'"([a-zA-Z0-9.-]+)":', zh_match.group(1)))
    en = set(re.findall(r'"([a-zA-Z0-9.-]+)":', en_match.group(1)))
    return zh, en


def test_every_requested_palette_and_notify_key_exists_in_both_locales() -> None:
    zh, en = _columns()
    requested: set[str] = set()
    for path in (PALETTE, NOTIFY, STREAM):
        text = path.read_text(encoding="utf-8")
        requested |= set(re.findall(r'[tT]\("([a-zA-Z0-9.-]+)"\)', text))
    index = INDEX.read_text(encoding="utf-8")
    requested |= set(re.findall(r'data-i18n(?:-aria|-placeholder)?="([a-zA-Z0-9.-]+)"', index))
    requested = {key for key in requested if key.startswith(("palette.", "notify."))}
    assert requested, "no palette/notify keys requested anywhere — the faces went dark"
    missing_zh = sorted(requested - zh)
    missing_en = sorted(requested - en)
    assert not missing_zh and not missing_en, (
        f"half-translated surface: missing in zh={missing_zh}, missing in en={missing_en}; "
        "t() falls back to the raw key and users read it verbatim"
    )


def test_the_constructed_key_families_are_exactly_the_declared_ones() -> None:
    zh, en = _columns()
    palette = PALETTE.read_text(encoding="utf-8")
    # Commands whose label is built at runtime (theme/locale flip with state)
    # never ask for palette.cmd.<id>; everything else must.
    overridden = set(re.findall(r'labelOverride[^}]*\bid: "([a-z]+)"', palette))
    overridden |= {item_id for item_id in re.findall(r'\{ id: "([a-z]+)"[^}]*labelOverride', palette)}
    ids = set(re.findall(r'\{ id: "([a-z]+)"', palette))
    assert ids, "palette command registry disappeared"
    # The segment must come from the LAST dot piece — the first build took
    # split(".")[1] and asked i18n for palette.group.group.
    assert '.split(".").pop()' in palette, (
        "group keys are no longer built from the trailing segment; the "
        "palette.group.group bug came back"
    )
    cmd_keys = {f"palette.cmd.{item_id}" for item_id in ids - overridden}
    group_keys = {"palette.group.task", "palette.group.surface"}
    for key in cmd_keys | group_keys:
        assert key in zh and key in en, f"{key} is constructed by the palette but declared in zh={key in zh} en={key in en}"


def test_the_combobox_listbox_contract_stays_in_index() -> None:
    index = INDEX.read_text(encoding="utf-8")
    modal = re.search(r'<div class="palette-modal panel-modal" id="paletteModal"[^>]*>', index)
    assert modal, "the palette modal shell left index.html"
    assert 'aria-hidden="true"' in modal.group(0), "the palette must ship closed"
    input_match = re.search(r'<input id="paletteInput"[^>]*>', index)
    assert input_match and 'role="combobox"' in input_match.group(0), "the palette input must be a combobox"
    assert 'aria-controls="paletteList"' in input_match.group(0), "the combobox must own its listbox"
    list_match = re.search(r'<ul class="palette-list" id="paletteList" role="listbox"', index)
    assert list_match, "the palette options container must be a listbox"


def test_notify_is_hooked_exactly_once_inside_the_terminal_home() -> None:
    api = API.read_text(encoding="utf-8")
    assert api.count("notifyTaskFinished(") == 1, "notifyTaskFinished must be called exactly once"
    assert api.count('from "./notify.js"') == 1, "notify.js must be imported exactly once"
    complete = re.search(r"export async function completeTask\(.*?\n\}", api, re.S)
    assert complete and "notifyTaskFinished(" in complete.group(0), (
        "the notify hook must live inside completeTask — the one terminal home — "
        "not in a side path that some terminal events skip"
    )
