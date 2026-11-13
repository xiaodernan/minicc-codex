"""M8-T898 — the task-dock toolstream chip answers its own keys and its backend.

The chip renders provider progress events that arrive as trace records from
``minicc/llm/openai_provider.py`` (M8-T897). Two silent-failure shapes are
worth a gate:

* the chip asks i18n for ``stream.charsUnit`` / ``stream.toolForming`` /
  ``stream.reasoningForming`` by *construction* — a key declared in one
  locale only would render raw key text in the other;
* the event codes the chip reacts to are a cross-language contract — the UI
  regex and the Python ``code=`` strings must name the same three codes, or
  the chip sits hidden forever (a regression nobody sees because the dock
  simply looks calm).

Also pins the CRLF endings of the two files the chip touched — both are
CRLF-native in this repo, and a stray LF rewrite shows up as a hundred-line
diff the next time anyone edits them.
"""

from __future__ import annotations
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
I18N = REPO / "web" / "src" / "core" / "i18n.js"
PANELS = REPO / "web" / "src" / "panels" / "index.js"
INDEX = REPO / "web" / "index.html"
STYLES = REPO / "web" / "styles.css"
PROVIDER = REPO / "minicc" / "llm" / "openai_provider.py"

CHIP_KEYS = {"stream.charsUnit", "stream.toolForming", "stream.reasoningForming"}
CHIP_CODES = {
    "provider_tool_call_start",
    "provider_tool_call_progress",
    "provider_reasoning_progress",
}


def _columns() -> tuple[set[str], set[str]]:
    source = I18N.read_text(encoding="utf-8")
    zh_match = re.search(r"zh: \{(.*?)\n  \},\n  en: \{", source, re.S)
    en_match = re.search(r"  en: \{(.*?)\n  \},\n\}", source, re.S)
    assert zh_match and en_match, "i18n.js no longer parses as a zh/en pair"
    zh = set(re.findall(r'"([a-zA-Z0-9.-]+)":', zh_match.group(1)))
    en = set(re.findall(r'"([a-zA-Z0-9.-]+)":', en_match.group(1)))
    return zh, en


def test_the_chip_keys_exist_in_both_locales() -> None:
    zh, en = _columns()
    missing_zh = sorted(CHIP_KEYS - zh)
    missing_en = sorted(CHIP_KEYS - en)
    assert not missing_zh and not missing_en, (
        f"half-translated chip: missing in zh={missing_zh}, missing in en={missing_en}"
    )


def test_the_chip_asks_exactly_its_declared_keys() -> None:
    panels = PANELS.read_text(encoding="utf-8")
    chip_block = re.search(r"const TOOL_STREAM_CODES = .*?export function updateTaskDock", panels, re.S)
    assert chip_block, "updateToolStreamChip block disappeared from panels/index.js"
    asked = set(re.findall(r't\("([a-zA-Z0-9.-]+)"\)', chip_block.group(0)))
    assert asked == CHIP_KEYS, f"chip asks {sorted(asked)}, declared gate is {sorted(CHIP_KEYS)}"


def test_the_ui_codes_and_the_emitter_codes_name_the_same_three() -> None:
    panels = PANELS.read_text(encoding="utf-8")
    ui_codes = set(re.findall(r"\b(provider_[a-z_]+)\b", panels))
    missing_in_ui = CHIP_CODES - ui_codes
    assert not missing_in_ui, f"chip would never fire: UI lacks {sorted(missing_in_ui)}"
    provider = PROVIDER.read_text(encoding="utf-8")
    emitted = set(re.findall(r'_emit_provider_progress\(\s*"([a-z_]+)"', provider))
    missing_in_backend = CHIP_CODES - emitted
    assert not missing_in_backend, f"backend stopped emitting {sorted(missing_in_backend)}"
    assert ui_codes & CHIP_CODES <= emitted | CHIP_CODES


def test_the_chip_element_is_wired_once_into_the_dock() -> None:
    index = INDEX.read_text(encoding="utf-8")
    assert index.count('id="taskDockToolStream"') == 1, "chip element missing or duplicated in index.html"
    panels = PANELS.read_text(encoding="utf-8")
    assert panels.count('$("#taskDockToolStream")') == 1, "chip queried from more than one home"
    assert len(re.findall(r"updateToolStreamChip\(", panels)) == 2, (
        "expected exactly one definition + one call site in updateTaskDock"
    )


def test_the_chip_styles_ship_with_reduced_motion_and_done_states() -> None:
    styles = STYLES.read_text(encoding="utf-8")
    assert ".toolstream-chip" in styles
    assert ".toolstream-chip[data-done]" in styles, "done state has no quiet styling"
    assert "prefers-reduced-motion" in styles, "sweep/spin must respect reduced motion"


def test_the_two_crlf_files_keep_their_endings() -> None:
    for path in (I18N, INDEX):
        data = path.read_bytes()
        crlf = data.count(b"\r\n")
        lf_only = data.count(b"\n") - crlf
        assert crlf > 0 and lf_only == 0, (
            f"{path.name} lost its CRLF endings (crlf={crlf}, stray lf={lf_only}) - "
            "an editor rewrote the file and every future diff will be huge"
        )
