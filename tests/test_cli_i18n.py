"""M12 — the CLI's two locale tables must answer for each other.

``minicc/cli_io.py`` carries a zh_cn and an en_us table behind ``tr``. The
fallback (unknown key -> zh_cn -> the raw key) means a key added to one locale
and forgotten in the other degrades silently; a half-translated CLI would be
invisible without a gate that asks the tables about each other and that reads
the repository's own sources to see which keys are actually reached.

These gates make the tables answer for each other and pin the formatter
``tr`` relies on. Every key is wired; the ratchet stands at zero. A commit
that adds a key nobody wires fails this gate — the baseline is not a place to
park unfinished copy.
"""

from __future__ import annotations

import re
from pathlib import Path

import minicc.cli_io as cli_io

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Every key in the tables is wired in production code. The ratchet has no
#: headroom left: adding a key nobody wires is the failure this gate exists to
#: prevent, not a shape to tolerate (M8-T1132 — the last 32 unwired keys were
#: either wired to their live call sites or removed from both tables).
UNREAD_KEYS_BASELINE = frozenset()


def _source_text() -> str:
    chunks = []
    for path in sorted((REPO_ROOT / "minicc").rglob("*.py")):
        chunks.append(path.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def test_the_two_tables_carry_the_same_keys() -> None:
    zh = set(cli_io._MESSAGES["zh_cn"])
    en = set(cli_io._MESSAGES["en_us"])
    assert zh == en, {"only_in_zh_cn": sorted(zh - en), "only_in_en_us": sorted(en - zh)}


def test_every_message_is_non_empty_in_both_locales() -> None:
    for locale, table in sorted(cli_io._MESSAGES.items()):
        for key, message in sorted(table.items()):
            assert isinstance(message, str) and message.strip(), (locale, key)


def test_the_default_locale_is_zh_cn() -> None:
    assert cli_io.get_locale() == "zh_cn"


def test_set_locale_accepts_only_known_values() -> None:
    previous = cli_io.get_locale()
    try:
        cli_io.set_locale("EN_US")
        assert cli_io.get_locale() == "en_us"
        cli_io.set_locale("klingon")
        assert cli_io.get_locale() == "en_us", "unknown locale must not flip the table"
        cli_io.set_locale("zh-CN")
        assert cli_io.get_locale() == "en_us", "a near-miss spelling must not flip either"
        cli_io.set_locale("zh_cn")
        assert cli_io.get_locale() == "zh_cn"
    finally:
        cli_io.set_locale(previous)


def test_tr_falls_back_to_the_raw_key_for_unknown_keys() -> None:
    previous = cli_io.get_locale()
    try:
        cli_io.set_locale("en_us")
        assert cli_io.tr("this_key_does_not_exist") == "this_key_does_not_exist"
    finally:
        cli_io.set_locale(previous)


def test_tr_formats_kwargs_and_survives_mismatches() -> None:
    previous = cli_io.get_locale()
    try:
        cli_io.set_locale("zh_cn")
        assert cli_io.tr("tool_not_found", index=7) == "未找到工具 #7；输入 /view 查看最近记录。"
        # missing kwargs must not raise — the message degrades to its shape
        assert "{index}" in cli_io.tr("tool_not_found")
        assert "{tool" not in cli_io.tr("tool_not_found", tool="x")  # wrong key for kwargs is fine: no raise
    finally:
        cli_io.set_locale(previous)


def test_no_message_is_an_unformatted_brace_without_a_key() -> None:
    for locale, table in sorted(cli_io._MESSAGES.items()):
        for key, message in sorted(table.items()):
            if "{" in message:
                assert re.search(r"\{[a-z_]+(\.[a-z_]+)?(!r)?(:[^{}]*)?\}", message), (locale, key, message)


def test_no_unread_key_lands_outside_the_ratchet() -> None:
    """The ratchet only shrinks: today's unread set must not grow past the baseline."""
    keys = set(cli_io._MESSAGES["zh_cn"])
    src = _source_text()
    used = set(re.findall(r'tr\("([a-z0-9_]+)"', src)) | set(re.findall(r"tr\('([a-z0-9_]+)'", src))
    unread = keys - used
    grew = unread - UNREAD_KEYS_BASELINE
    assert not grew, f"new unread keys (wire them or shrink the baseline): {sorted(grew)}"
    # And the baseline must not carry keys that no longer exist.
    stale = UNREAD_KEYS_BASELINE - keys
    assert not stale, f"baseline names keys the tables no longer have: {sorted(stale)}"


def test_the_baseline_does_not_secretly_hold_wired_keys() -> None:
    src = _source_text()
    used = set(re.findall(r'tr\("([a-z0-9_]+)"', src)) | set(re.findall(r"tr\('([a-z0-9_]+)'", src))
    wired = used & UNREAD_KEYS_BASELINE
    assert not wired, f"these keys are wired in the source — shrink the baseline: {sorted(wired)}"


if __name__ == "__main__":
    raise SystemExit(__import__("pytest").main([__file__, "-q", "-W", "error"]))
