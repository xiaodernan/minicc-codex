import re
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

#: the tell-tale fragments that only come from a Python helper script.
_FRAGMENTS = (
    "import sys",
    "from pathlib import Path",
    "def main(",
    "print(",
    "entry = ",
    "_ledger",
    "p = Path(",
)

def test_roadmap_ends_with_readable_markdown_not_script_code() -> None:
    """The ledger must end with the last batch entry, not helper source."""
    tail = _ROADMAP.read_text(encoding="utf-8", errors="replace")[-4000:]
    found = [fragment for fragment in _FRAGMENTS if fragment in tail]
    assert found == [], (
        "docs/ROADMAP_TO_PRODUCT.md's tail contains the tell-tale "
        "fragments of a helper script (likely an `_append*.py` whose "
        "`entry = ...` AST was accidentally quoted into the doc): "
        + ", ".join(found)
    )
