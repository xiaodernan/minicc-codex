"""The CLI has two locale tables and nothing else keeps them in step.

``minicc/cli_io.py`` carries a zh_cn and an en_us table behind ``tr``, which
falls back to zh_cn and then to the raw key. That fallback means a key added to
one locale and forgotten in the other degrades silently into Chinese text under
``MINICC_LOCALE=en_us`` -- a half-translated CLI no test could see. These gates
make the tables answer for each other and pin the formatter ``tr`` relies on.
"""

from __future__ import annotations

import re
from pathlib import Path

from minicc import cli_io

REPO_ROOT = Path(__file__).resolve().parents[1]

# Measured on 2026-09-28 (working tree on top of 669eae5): the two tables define
# 64 keys and only 12 are ever read with tr(), so 52 translations are dead weight
# promising a localized CLI the code does not deliver yet. This is a ratchet, not
# an approval: wiring an existing key up shrinks the set (fine), deleting a key
# shrinks it (fine), and adding a new translation nobody reads fails here.
UNREAD_KEYS_BASELINE = frozenset({
    "absolute_path", "allow_prompt", "allowlist_failed", "allowlist_written",
    "assistant_prefix", "branch_invalid", "compact_mode", "config_error",
    "denied_exec", "denied_write", "expand_usage", "expanded_mode",
    "fork_created", "fork_invalid_point", "fork_max_keep", "fork_min_keep",
    "fork_resume", "git_failed", "high_risk_tool", "invalid_args",
    "mcp_config_error", "mcp_no_provider", "mcp_sampling_denied",
    "mcp_sampling_failed", "mcp_server_failed", "memory_list_empty",
    "memory_not_found", "memory_written", "need_network", "no_tool_history",
    "no_tool_to_expand", "path_outside", "prompt_not_run", "resume_instruction",
    "rewind_min", "rewind_no_session", "rewind_no_user", "session_error",
    "session_format_error", "session_not_found", "system_io_error",
    "tool_denied", "tool_error", "tool_exception", "tool_not_found",
    "tool_output_collapsed", "tool_output_expanded", "unknown_tool", "usage",
    "user_index_min", "view_restored", "workspace_not_dir",
})

TR_CALL = re.compile(r"""\btr\(\s*["']([A-Za-z0-9_]+)["']""")


def _tr_call_sites() -> dict[str, list[str]]:
    sites: dict[str, list[str]] = {}
    for path in sorted((REPO_ROOT / "minicc").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for match in TR_CALL.finditer(text):
            sites.setdefault(match.group(1), []).append(path.relative_to(REPO_ROOT).as_posix())
    return sites

def test_the_two_locale_tables_define_the_same_keys() -> None:
    zh = cli_io._MESSAGES["zh_cn"]
    en = cli_io._MESSAGES["en_us"]
    only_zh = sorted(set(zh) - set(en))
    only_en = sorted(set(en) - set(zh))
    assert set(zh) == set(en), f"locale tables drifted: only-zh={only_zh} only-en={only_en}"


def test_every_message_formats_with_its_own_placeholders() -> None:
    # ``tr`` returns the raw template when a placeholder is missing, so a typo
    # such as {coun} would ship as literal braces instead of raising.
    for locale, table in cli_io._MESSAGES.items():
        for key, template in table.items():
            names = set(re.findall(r"{(\w+)", template))
            if not names:
                continue
            rendered = template.format(**{name: 1 for name in names})
            assert "{" not in rendered, f"{locale}:{key} left a placeholder: {rendered}"


def test_locale_switch_changes_the_rendering_and_restores() -> None:
    original = cli_io.get_locale()
    try:
        cli_io.set_locale("en_us")
        assert cli_io.get_locale() == "en_us"
        assert cli_io.tr("starting") != cli_io._MESSAGES["zh_cn"]["starting"]
    finally:
        cli_io.set_locale(original)


def test_the_no_session_cost_line_is_not_the_unpriced_line() -> None:
    # /cost outside a session means "there is no cumulative cost here", which is
    # not the same statement as "the model has no price data".
    assert cli_io.tr("session_cost_unavailable") != cli_io.tr("session_cost_none")


def test_every_tr_call_site_names_a_key_both_tables_define() -> None:
    # tr() falls back to the raw key when a lookup misses, so a typo would ship
    # the literal key text to the user instead of raising.
    keys = set(cli_io._MESSAGES["zh_cn"])
    unknown = {name: where for name, where in _tr_call_sites().items() if name not in keys}
    assert not unknown, f"tr() called with keys no table defines: {unknown}"


def test_unread_translation_keys_only_shrink() -> None:
    unread = set(cli_io._MESSAGES["zh_cn"]) - set(_tr_call_sites())
    added = sorted(unread - UNREAD_KEYS_BASELINE)
    assert not added, (
        "new translations nothing reads were added: "
        f"{added}. Wire them into a tr(...) call site, or drop them; the recorded "
        "baseline only lists keys that were already dead when it was measured."
    )
