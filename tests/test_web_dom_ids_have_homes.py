"""M8-T905: every DOM id the frontend scripts reference must have a home.

``#pulseMemory`` was referenced by ``openPulseStage`` since M8-T895 but never
existed in ``web/index.html`` — every ``fetchAll`` call threw on it, landed in
the catch, and the pulse card's three rings plus the task archive were
silently dead for ten batches (the SSE sparkline rode another path and looked
alive). One ghost id, ten batches of a broken screen.

This gate makes that whole class impossible: every literal ``$("#id")`` and
``getElementById("id")`` reference across ``web/src/**`` must resolve to an id
defined either in ``index.html`` or created by the scripts themselves
(``id="..."`` inside markup templates, or ``.id = "..."`` lazy creation).
Dynamic selectors (``$("#" + name)``) are out of scope by construction — the
regex only sees literals.
"""

from pathlib import Path
import re

WEB = Path(__file__).resolve().parent.parent / "web"

ID_DEF_IN_HTML = re.compile(r'id="([a-zA-Z][\w-]*)"')
ID_REF = re.compile(r'\$\("#([a-zA-Z][\w-]*)"\)|getElementById\("([a-zA-Z][\w-]*)"\)')
ID_DEF_IN_JS = re.compile(r'\bid="([a-zA-Z][\w-]*)"|\.id\s*=\s*"([a-zA-Z][\w-]*)"')


def _defined_and_referenced():
    html = (WEB / "index.html").read_text(encoding="utf8")
    defined = set(ID_DEF_IN_HTML.findall(html))

    referenced = set()
    for path in (WEB / "src").rglob("*.js"):
        src = path.read_text(encoding="utf8", errors="replace")
        for match in ID_REF.finditer(src):
            referenced.add(match.group(1) or match.group(2))
        for a, b in ID_DEF_IN_JS.findall(src):
            defined.add(a or b)
    # the built bundles carry the same definitions; scanning them keeps the
    # gate honest about what actually ships, not just what sources say
    for name in ("app.js", "game.js"):
        bundle = WEB / name
        if bundle.exists():
            for a, b in ID_DEF_IN_JS.findall(bundle.read_text(encoding="utf8", errors="replace")):
                defined.add(a or b)
    return defined, referenced


def test_every_referenced_dom_id_has_a_home():
    defined, referenced = _defined_and_referenced()
    assert referenced, "the scan should see the frontend's id references"
    assert len(referenced) >= 100, f"suspiciously few id references: {len(referenced)}"
    ghosts = sorted(referenced - defined)
    assert not ghosts, (
        "ids referenced by scripts but defined nowhere (null-deref like #pulseMemory): "
        + ", ".join(f"#{g}" for g in ghosts)
    )


def test_the_scan_catches_the_pulse_memory_class_of_bug():
    # the gate's own regexes must see the shape that hurt us: a literal
    # $("#pulseMemory") reference with no definition anywhere
    ref_match = ID_REF.search('$("#pulseMemory").textContent = "x";')
    assert ref_match and ref_match.group(1) == "pulseMemory"
    # lazy creation counts as a definition — approvals.js builds its layer at runtime
    lazy = '.id = "approvalLayer";'
    a, b = ID_DEF_IN_JS.search(lazy).groups()
    assert (a or b) == "approvalLayer"
    defined, referenced = _defined_and_referenced()
    assert "approvalLayer" in defined, "lazy .id creation must count as a home"
    assert "approvalLayer" not in referenced - defined
