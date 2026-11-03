"""M8-T565: a ``U+FFFD`` git wrote is a rendering, not an address.

``_git`` decodes git's stdout with ``errors="replace"``, so a file whose name
git could not put into UTF-8 arrives in the listing with ``U+FFFD`` in it.  The
listing then treats that string as the path it stands for: ``_resolve`` joins it
to the workspace, ``_text`` finds nothing there, and ``len("".splitlines())``
answers **0 lines** for a file that has three.  Measured on HEAD through
``summary()`` / ``diff()`` (``bad\\udcff.md`` is three lines on disk):

| 形状 | HEAD 的结果 |
| --- | --- |
| A `bad\udcff.md`（3 行），仓库里只有它 | 1 格 `bad\ufffd.md`，add=0；`diff(替换名)` added/0；`diff(真名)` clean/0 |
| B `a\udcff.md`（2 行）与 `a\ufffd.md`（1 行）同一目录 | git 只出门 1 条 `?? a\ufffd.md`，那一格 add=1 —— 那是字面上叫这个名字的文件的行数 |
| C 只有 `bad\ufffd.md`（3 行，名字本来就是 U+FFFD） | add=3 —— 读对了，本批不许改坏 |
| D `sub/bad\udcff.md`（2 行，父目录名字正常） | add=0 |
| E `hi\ud800.md`（3 行，段外孤立代理项） | add=0，且没有任何算法能把这个名字渲染回去 |
| F 正常名字 `notes.md`（3 行） | add=3，且没有判定 |

A/B/D/E are the defect: the panel prints a name that opens nothing and answers
"this file is empty" for bytes it never went and looked at - the same collapse
this campaign keeps meeting, one step further along: the read that failed is
the *decode*, and the answer written for it is a number.

The fix reads git's own step backwards.  ``name.encode("utf-8",
"surrogateescape").decode("utf-8", "replace")`` reproduces, from the disk name,
exactly the string git's record was decoded into - so the listing can ask which
disk entries render into the name it is holding: one (A, D) counts and diffs
that file; none is a faithful name and nothing changes (C, F); two (B) is not
attributable, so the row carries no number and says why.  E is the "none" of
names the ruler cannot reproduce at all: it says so instead of answering 0.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from minicc.changes import ChangeInspector

GIT = ["-c", "user.email=t@example.test", "-c", "user.name=t"]

#: git's own rendering of A - what ``_git`` hands the listing to decode.
LOSSY = "bad\ufffd.md"
LOSSY_SUB = "sub/bad\ufffd.md"
LOSSY_AMBIGUOUS = "a\ufffd.md"
LOSSY_UNREACHABLE = "hi\ufffd.md"


def _git(workspace: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *GIT, *args],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _repo(workspace: Path) -> Path:
    _git(workspace, "init", "-q")
    return workspace


def _row(inspector: ChangeInspector, name: str) -> dict:
    for item in inspector.summary()["files"]:
        if item["path"] == name:
            return item
    raise AssertionError(f"{name!r} is not in {[i['path'] for i in inspector.summary()['files']]}")


def test_a_listed_name_that_is_a_rendering_is_counted_from_the_file_it_came_from(
    tmp_path: Path,
) -> None:
    """A: three lines on disk are three lines in the row, whatever the name looks like."""
    (tmp_path / "bad\udcff.md").write_text("one\ntwo\nthree\n", encoding="utf-8")
    _repo(tmp_path)
    inspector = ChangeInspector(tmp_path)
    row = _row(inspector, LOSSY)
    assert row["status"] == "added", row
    assert row["additions"] == 3, row
    assert row["name_resolution"] == "substituted", row


def test_the_detail_page_reads_the_file_the_list_named(tmp_path: Path) -> None:
    """A, again, from the route the panel follows when the row is clicked.

    The lossy spelling is the only one that can travel in a URL, so it is the
    one that has to work: the patch it shows is the disk file's content.
    """

    (tmp_path / "bad\udcff.md").write_text("one\ntwo\nthree\n", encoding="utf-8")
    _repo(tmp_path)
    diff = ChangeInspector(tmp_path).diff(LOSSY)
    assert diff["status"] == "added", diff
    assert diff["additions"] == 3, diff
    assert "+one" in diff["patch"] and "+three" in diff["patch"], diff
    assert diff["name_resolution"] == "substituted", diff


def test_the_two_spellings_of_one_file_answer_with_one_number(tmp_path: Path) -> None:
    """A, asked both ways: the disk's spelling and git's rendering of it.

    HEAD answers ``clean``/0 for the real name - the status table is keyed by
    the rendered string, so the real spelling misses it and the detail page
    invents a baseline - and ``added``/0 for the rendered one.  Neither answer
    is the file's.
    """

    (tmp_path / "bad\udcff.md").write_text("one\ntwo\nthree\n", encoding="utf-8")
    _repo(tmp_path)
    inspector = ChangeInspector(tmp_path)
    real = inspector.diff("bad\udcff.md")
    rendered = inspector.diff(LOSSY)
    for key in ("status", "additions", "deletions", "name_resolution"):
        assert real[key] == rendered[key], (key, real[key], rendered[key])
    assert rendered["additions"] == 3, rendered


def test_a_normal_parent_reaches_a_bad_leaf(tmp_path: Path) -> None:
    """D: the rendering can sit in the last segment while the path walks through dirs."""
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "bad\udcff.md").write_text("one\ntwo\n", encoding="utf-8")
    _repo(tmp_path)
    row = _row(ChangeInspector(tmp_path), LOSSY_SUB)
    assert row["additions"] == 2, row
    assert row["name_resolution"] == "substituted", row


def test_two_disk_names_that_render_alike_are_not_answered_with_one_number(
    tmp_path: Path,
) -> None:
    """B: one record, two files that make it - so no row number is *this* file's.

    git reports a single ``?? a\ufffd.md`` for both files (measured: 1 record, not
    2 - the half it dropped is a separate loss and this batch does not claim
    it).  The row HEAD shows carries the line count of whichever file the
    rendered path happens to open, which is a number for one file published as
    the record for both.
    """

    (tmp_path / "a\udcff.md").write_text("one\ntwo\n", encoding="utf-8")
    (tmp_path / "a\ufffd.md").write_text("three\n", encoding="utf-8")
    _repo(tmp_path)
    inspector = ChangeInspector(tmp_path)
    assert len(inspector._listed_sources(LOSSY_AMBIGUOUS)) == 2, inspector._listed_sources(LOSSY_AMBIGUOUS)
    row = _row(inspector, LOSSY_AMBIGUOUS)
    assert row["name_resolution"] == "ambiguous", row
    assert row["additions"] is None, row
    assert row["deletions"] is None, row


def test_two_bad_names_that_render_apart_each_keep_their_own_number(
    tmp_path: Path,
) -> None:
    """The ruler is not a one-hit shortcut: two suspect rows resolve separately.

    ``a\udcff.md`` (1 line) and ``b\udcff.md`` (2 lines) are two records, two
    renderings and two files.  HEAD answers 0 for both - and a fix that found
    "some bad-named file" and used it for every row would answer 1 twice.
    """

    (tmp_path / "a\udcff.md").write_text("one\n", encoding="utf-8")
    (tmp_path / "b\udcff.md").write_text("two\nthree\n", encoding="utf-8")
    _repo(tmp_path)
    inspector = ChangeInspector(tmp_path)
    a = _row(inspector, "a\ufffd.md")
    b = _row(inspector, "b\ufffd.md")
    assert (a["additions"], b["additions"]) == (1, 2), (a, b)
    assert a["name_resolution"] == b["name_resolution"] == "substituted", (a, b)
    assert "+one" in inspector.diff("a\ufffd.md")["patch"], a
    assert "+three" in inspector.diff("b\ufffd.md")["patch"], b


def test_the_ambiguous_row_does_not_borrow_a_number_from_the_detail_page(
    tmp_path: Path,
) -> None:
    """B, and the route that used to answer it: no number, no patch, and it says so."""

    (tmp_path / "a\udcff.md").write_text("one\ntwo\n", encoding="utf-8")
    (tmp_path / "a\ufffd.md").write_text("three\n", encoding="utf-8")
    _repo(tmp_path)
    diff = ChangeInspector(tmp_path).diff(LOSSY_AMBIGUOUS)
    assert diff["name_resolution"] == "ambiguous", diff
    assert diff["additions"] is None and diff["deletions"] is None, diff
    assert diff["patch"] == "", diff


def test_the_ruler_that_reads_git_s_step_backwards_names_every_source(
    tmp_path: Path,
) -> None:
    """The matching is a ruler of its own, and it is what the verdicts are made of.

    ``bad\udcff`` and ``bad\ufffd`` are two directories whose contents git renders
    into the same record.  Windows cannot show that pair through ``git status``
    (a directory whose name git cannot encode is not reported at all), so the
    ruler is asked directly - and a two-segment name has to walk segment by
    segment to find either half.
    """

    (tmp_path / "bad\udcff").mkdir()
    (tmp_path / "bad\udcff" / "inner.md").write_text("one\ntwo\n", encoding="utf-8")
    (tmp_path / "bad\ufffd").mkdir()
    (tmp_path / "bad\ufffd" / "inner.md").write_text("three\n", encoding="utf-8")
    _repo(tmp_path)
    inspector = ChangeInspector(tmp_path)
    sources = sorted(inspector._listed_sources("bad\ufffd/inner.md"))
    assert len(sources) == 2, sources
    assert "inner.md" in {Path(name).name for name in sources}, sources
    assert sorted(inspector._listed_sources("bad\ufffd/nope.md")) == [], "a missing leaf is not a source"


def test_the_control_a_name_that_is_its_own_rendering_keeps_its_number(
    tmp_path: Path,
) -> None:
    """C: a file genuinely named with ``U+FFFD`` is faithful - one source, its own name."""

    (tmp_path / "bad\ufffd.md").write_text("one\ntwo\nthree\n", encoding="utf-8")
    _repo(tmp_path)
    inspector = ChangeInspector(tmp_path)
    row = _row(inspector, LOSSY)
    assert row["additions"] == 3, row
    assert row["name_resolution"] == "", row
    assert inspector.diff(LOSSY)["additions"] == 3, row


def test_the_control_a_ordinary_name_carries_no_verdict(tmp_path: Path) -> None:
    """F: nothing about a readable name changes - the ruler is not even consulted."""

    (tmp_path / "notes.md").write_text("one\ntwo\nthree\n", encoding="utf-8")
    _repo(tmp_path)
    row = _row(ChangeInspector(tmp_path), "notes.md")
    assert row["additions"] == 3, row
    assert row["name_resolution"] == "", row


@pytest.mark.skipif(
    sys.platform != "win32",
    reason=(
        "a name no re-rendering can reproduce needs a surrogate outside the "
        "surrogateescape range; POSIX names go through it and back, so there "
        "the ruler always finds the entry it came from"
    ),
)
def test_a_name_the_ruler_cannot_reproduce_says_so_instead_of_answering_zero(
    tmp_path: Path,
) -> None:
    """E: ``encode("utf-8", "surrogateescape")`` raises on U+D800, so no source is found.

    git still renders the name (it substitutes on its side), so the row exists
    and HEAD counts it at 0 lines.  The honest answer is "I could not tie this
    name to a file", not a number.
    """

    (tmp_path / "hi\ud800.md").write_text("one\ntwo\nthree\n", encoding="utf-8")
    _repo(tmp_path)
    row = _row(ChangeInspector(tmp_path), LOSSY_UNREACHABLE)
    assert row["name_resolution"] == "unmatched", row
    assert row["additions"] is None, row
    assert ChangeInspector(tmp_path).diff(LOSSY_UNREACHABLE)["name_resolution"] == "unmatched"


def test_editing_the_file_behind_a_rendering_invalidates_the_listed_number(
    tmp_path: Path,
) -> None:
    """The memo watches the file the name stands for, not the name that opens nothing.

    The list is cached on a fingerprint of each row's stat.  Statted through the
    rendered name the lookup misses, every suspect row enters the fingerprint as
    ``(raw, None, None)``, and an edit leaves that tuple where it was - so the
    panel keeps serving the number the disk no longer holds (M8-T563's stale
    memo, one level up).
    """

    (tmp_path / "bad\udcff.md").write_text("one\n", encoding="utf-8")
    _repo(tmp_path)
    inspector = ChangeInspector(tmp_path)
    assert _row(inspector, LOSSY)["additions"] == 1, inspector.summary()
    (tmp_path / "bad\udcff.md").write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")
    assert _row(inspector, LOSSY)["additions"] == 4, inspector.summary()


def test_the_summary_counts_the_rows_whose_names_are_renderings(tmp_path: Path) -> None:
    """The panel needs one number for "these names are not the disk's spelling"."""

    (tmp_path / "bad\udcff.md").write_text("one\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("two\n", encoding="utf-8")
    _repo(tmp_path)
    summary = ChangeInspector(tmp_path).summary()
    assert summary["substituted_names"] == 1, summary
