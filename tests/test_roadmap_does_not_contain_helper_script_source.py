import sys
from pathlib import Path

#: This is not a general markdown lint; it is a tripwire for one concrete
#: blunder pattern we actually hit: a batch's ledger-append helper
#: ``_ledger*.py`` mistakenly included its own source code as the
#: ``entry`` value, so the helper expression landed verbatim in the
#: ledger.  Any future occurrence is silent doc pollution, so it reds
#: here long before it reaches a user.
_REPO_ROOT = Path(__file__).resolve().parents[1]
_ROADMAP = _REPO_ROOT / "docs" / "ROADMAP_TO_PRODUCT.md"

#: The signature is not "any of these tokens" — the ledger legitimately
#: quotes tokens by name (e.g., "entry = '''").  The tripwire only fires
#: on the *assembly signature*, the sequence that exists only in a
#: helper script and cannot be authored deliberately: the double-quoted
#: literal that is the raw body of a ``Path("ROADMAP...").read_text()``
#: call, followed immediately by a literal ``entry = '''`` that is the
#: helper's own assignment syntax, with no doc-talk in between.
_ASSEMBLY_SIGNATURES = (
    "p = Path('docs/ROADMAP_TO_PRODUCT.md')",
    'p = Path("docs/ROADMAP_TO_PRODUCT.md")',
    "entry = '''\n",
)

def test_roadmap_ends_with_readable_markdown_not_script_code() -> None:
    """The ledger must end with the last batch entry, not helper source."""
    tail = _ROADMAP.read_text(encoding="utf-8", errors="replace")[-4000:]
    found = [signature for signature in _ASSEMBLY_SIGNATURES if signature in tail]
    assert found == [], (
        "docs/ROADMAP_TO_PRODUCT.md's tail contains the assembly "
        "signatures of a ledger-append helper script (an `_append*.py` "
        "whose `p = Path('ROADMAP...')` and `entry = '''...` lines were "
        "quoted into the doc): " + ", ".join(found)
    )
