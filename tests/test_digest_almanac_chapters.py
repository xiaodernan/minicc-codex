"""M8-T1007: the fact pack must be honest — the almanac chapter counter the
dockyard/git/self-describes reads is not allowed to drift.

`scripts/update-latest-json.mjs` counts `roman: { zh:` occurrences in
`web/src/panels/almanac.js` to build `almanac_chapters` for `/api/digest`.
Two separate pieces of code could disagree: the Rail (where the chapters
live) and the counter (in ``minicc/digest.py``).  This test is the latch.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from minicc.digest import build_digest


ALMANAC = Path(__file__).resolve().parents[1] / "web" / "src" / "panels" / "almanac.js"


def _count_rail_entries(source: str) -> int:
    return source.count("roman: { zh:")


def test_rail_count_in_source_file_is_seventeen_plus_prologue() -> None:
    assert ALMANAC.exists(), f"almanac not found at {ALMANAC}"
    mem = ALMANAC.read_text(encoding="utf-8")
    count = _count_rail_entries(mem)
    print(f"almanac.js entries: {count}")
    assert count >= 18, f"expected >=18 chapter entries, got {count}"


def test_digest_reports_almanac_chapters_aligned_with_source() -> None:
    digest = build_digest(Path(__file__).resolve().parents[1])
    source = ALMANAC.read_text(encoding="utf-8")
    expected = _count_rail_entries(source)
    reported = digest.get("almanac_chapters")
    print(f"digest almanac_chapters: {reported}  source count: {expected}")
    assert reported == expected, f"digest says {reported}, source has {expected}"


@pytest.mark.parametrize("sub", ["src/panels/almanac.js"])
def test_digest_survives_a_missing_almanac_file(tmp_path: Path, sub: str) -> None:
    (tmp_path / sub).parent.mkdir(parents=True)
    # no almanac.js inside a temp repo — counter must be 0, not crash
    (tmp_path / "README.md").write_text("# temp fake repo\n", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    import subprocess
    subprocess.run(["git", "init"], cwd=tmp_path, check=False, capture_output=True)
    d = build_digest(tmp_path)
    print("missing almanac digest:", d.get("almanac_chapters"))
    assert d.get("almanac_chapters") == 0
