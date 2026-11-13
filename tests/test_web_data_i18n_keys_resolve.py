"""M8-T906: every data-i18n key declared in the shipped HTML must exist in the dict.

``web/index.html`` declares 182 ``data-i18n``/``data-i18n-aria``/``data-i18n-placeholder``/
``data-i18n-title`` keys. Five of them (``recentTasks`` / ``workspace`` / ``agentSession``
/ ``live`` / plus the dot-less bare ``workspace`` reuse) were never in the dictionary, so
flipping the UI to English silently left those elements in Chinese — the apply-skip path
keeps the hardcoded zh text. This gate closes the class: every declared key must resolve
in both locales, mirroring what the ``t()`` literal gate already does for script-side
keys.
"""

from pathlib import Path
import re

WEB = Path(__file__).resolve().parent.parent / "web"

DECLARED = re.compile(r'data-i18n(?:-aria|-placeholder|-title)?="([\w.]+)"')

# same shape the node one-home gate uses: an entry starts after a line break,
# comma, or brace, then a quoted or bare key followed by a colon. Quoted-only
# scans miss the bare-key entries (recentTasks / workspace / live / ...) and
# would manufacture ghosts that do not exist.
KEY_DEF = re.compile(r'(?:^|[,\n{])\s*(?:"([^"]+)"|([A-Za-z_$][\w.-]*))\s*:')


def _i18n_columns():
    raw = (WEB / "src" / "core" / "i18n.js").read_text(encoding="utf8")
    zh = re.search(r"zh: \{(.*?)\n  \},\n  en: \{", raw, re.S)
    en = re.search(r"  en: \{(.*?)\n  \},\n\}", raw, re.S)
    assert zh and en, "i18n.js must parse as a zh/en pair"

    def keys_of(block: str) -> set:
        out = set()
        for match in KEY_DEF.finditer(block):
            key = match.group(1) or match.group(2)
            if key not in ("zh", "en"):
                out.add(key)
        return out

    return keys_of(zh.group(1)), keys_of(en.group(1))


def _declared_keys():
    html = (WEB / "index.html").read_text(encoding="utf8")
    declared = set(DECLARED.findall(html))
    for path in (WEB / "src").rglob("*.js"):
        declared |= set(DECLARED.findall(path.read_text(encoding="utf8", errors="replace")))
    return declared


def test_every_declared_data_i18n_key_exists_in_both_locales():
    zh_keys, en_keys = _i18n_columns()
    declared = _declared_keys()
    assert len(declared) >= 180, f"suspiciously few declared keys: {len(declared)}"
    missing_zh = sorted(declared - zh_keys)
    missing_en = sorted(declared - en_keys)
    assert not missing_zh, f"declared keys missing from zh: {missing_zh}"
    assert not missing_en, f"declared keys missing from en: {missing_en}"


def test_the_gate_sees_the_ghost_key_shape():
    html = 'data-i18n="workspace">工作区</span>'
    match = DECLARED.search(html)
    assert match and match.group(1) == "workspace"
    zh_keys, en_keys = _i18n_columns()
    # the key ships as a bare entry (recentTasks: "最近任务") near the top of
    # the dict — the quoted-only scan missed it and manufactured a ghost
    for name in ("workspace", "recentTasks", "agentSession", "live", "language"):
        assert name in zh_keys, f"{name} missing from zh scan"
        assert name in en_keys, f"{name} missing from en scan"
