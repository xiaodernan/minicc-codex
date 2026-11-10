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

#: The signature we match is the *whole contiguous run* of a helper's
#: own preamble (the echo chain).  A line by itself is normal prose —
#: the ledger legitimately talks about `p = Path(...)`; only the whole
#: run of five lines in sequence is pollution.
_HELPER_PREAMBLE = (
    "import sys\n"
    "from pathlib import Path\n"
    "sys.stdout.reconfigure(encoding='utf-8', errors='replace')\n"
    "p = Path('docs/ROADMAP_TO_PRODUCT.md')\n"
    "entry = '''\n"
)


def test_roadmap_ends_with_readable_markdown_not_script_code() -> None:
    """The ledger must end with the last batch entry, not helper source."""
    tail = _ROADMAP.read_text(encoding="utf-8", errors="replace")[-6000:]
    assert _HELPER_PREAMBLE not in tail, (
        "docs/ROADMAP_TO_PRODUCT.md's tail contains the exact "
        "preamble of a ledger-append helper script — that is the "
        "helper's own source code quoted into the doc, not the "
        "batch's prose about it."
    )
