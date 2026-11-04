"""M8-T569（第五百五十一批）：总数把「这一行说不出行数」加成 0 行。

第五百四十七批让一行说不出数的时候答 `None`（`minicc/changes.py:682`～`:683`：
`NAME_AMBIGUOUS` / `NAME_UNMATCHED`），可清单的总数把每一行
`int(item.get("additions") or 0)` 加起来（`minicc/changes.py:1077`～`:1078`）——
`None` 与 `0` 在求和这一步又被压回同一个数。探针 `scratch/probe569.py`：

  P1  一行说不出数（磁盘上两行）        -> total_files=1、additions=0、deletions=0
  P2  一行说不出、一行 +3               -> additions=3（只数看得见的那一半）
  P3  两行都数得出来（对照）            -> additions=5
  P4  git 数得出来的删除（对照）        -> additions=0、deletions=3

本批让总数与行用同一把尺：有一行数不出来，总数就答 `None`，另有一个键说得出
「几行数不出来」（`files_without_counts`）——它比 `files` 那一截名单大，
被 `_MAX_FILES` 切掉的那几行也只有这一个家。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from minicc import changes as changes_module
from minicc.changes import ChangeInspector

GIT = ["-c", "user.email=t@example.test", "-c", "user.name=t"]
MAX_FILES = changes_module._MAX_FILES


def _git(workspace: Path, *args: str) -> None:
    subprocess.run(["git", *GIT, *args], cwd=workspace, check=True,
                   capture_output=True, text=True, encoding="utf-8", errors="replace")


def _repo(workspace: Path) -> Path:
    _git(workspace, "init", "-q")
    return workspace


def _summary(workspace: Path) -> dict:
    return ChangeInspector(workspace).summary()


def _row(summary: dict, name: str) -> dict:
    for item in summary["files"]:
        if item["path"] == name:
            return item
    raise AssertionError(f"{name!r} not in {[i['path'] for i in summary['files']]}")


# --------------------------------------------------------------------------
# 说不出数的那一行把总数拖成 0
# --------------------------------------------------------------------------

def test_a_row_that_cannot_be_counted_blanks_the_total(tmp_path: Path) -> None:
    """P1：唯一的这一行数不出来，总数不许报 0 行。"""
    workspace = tmp_path / "p1"
    workspace.mkdir()
    (workspace / "a\udcff.md").write_text("one\ntwo\n", encoding="utf-8")
    (workspace / "a\ufffd.md").write_text("x\n", encoding="utf-8")
    _repo(workspace)
    summary = _summary(workspace)
    assert summary["total_files"] == 1, summary
    row = _row(summary, "a\ufffd.md")
    assert (row["additions"], row["deletions"]) == (None, None), row
    assert summary["additions"] is None, summary
    assert summary["deletions"] is None, summary


def test_the_countable_half_is_not_reported_as_the_whole(tmp_path: Path) -> None:
    """P2：另一行 +3 是真的，可「一共加了几行」仍然没有答案。"""
    workspace = tmp_path / "p2"
    workspace.mkdir()
    (workspace / "a\udcff.md").write_text("one\ntwo\n", encoding="utf-8")
    (workspace / "a\ufffd.md").write_text("x\n", encoding="utf-8")
    (workspace / "notes.md").write_text("1\n2\n3\n", encoding="utf-8")
    _repo(workspace)
    summary = _summary(workspace)
    assert summary["total_files"] == 2, summary
    assert _row(summary, "notes.md")["additions"] == 3, summary
    assert summary["additions"] is None, summary


def test_the_uncounted_rows_have_a_number_of_their_own(tmp_path: Path) -> None:
    """总数答不出之后得有话说：几行数不出来，是一个数，不是一句道歉。"""
    workspace = tmp_path / "p2b"
    workspace.mkdir()
    (workspace / "a\udcff.md").write_text("one\ntwo\n", encoding="utf-8")
    (workspace / "a\ufffd.md").write_text("x\n", encoding="utf-8")
    (workspace / "notes.md").write_text("1\n2\n3\n", encoding="utf-8")
    _repo(workspace)
    summary = _summary(workspace)
    assert summary["files_without_counts"] == 1, summary


def test_an_uncounted_row_cut_out_of_the_list_is_still_reported(tmp_path: Path) -> None:
    """`files` 是一截名单，`files_without_counts` 数的是全部——这才容得下窗外那些行。"""
    workspace = tmp_path / "cap"
    workspace.mkdir()
    for index in range(MAX_FILES + 1):
        (workspace / f"f{index:04d}.py").write_text("x = 1\n", encoding="utf-8")
    (workspace / "z\udcff.md").write_text("one\ntwo\n", encoding="utf-8")
    (workspace / "z\ufffd.md").write_text("x\n", encoding="utf-8")
    _repo(workspace)
    summary = _summary(workspace)
    assert summary["truncated"] is True, summary
    assert "z\ufffd.md" not in [item["path"] for item in summary["files"]], summary
    assert summary["total_files"] == MAX_FILES + 2, summary
    assert summary["additions"] is None, summary
    assert summary["files_without_counts"] == 1, summary


# --------------------------------------------------------------------------
# 数得出来的那些格：不许被本批改口
# --------------------------------------------------------------------------

def test_the_control_counted_rows_still_add_up(tmp_path: Path) -> None:
    """P3：两行都数得出来，总数还是那个和（本批不许动它）。"""
    workspace = tmp_path / "p3"
    workspace.mkdir()
    (workspace / "one.md").write_text("1\n2\n", encoding="utf-8")
    (workspace / "two.md").write_text("1\n2\n3\n", encoding="utf-8")
    _repo(workspace)
    summary = _summary(workspace)
    assert summary["total_files"] == 2, summary
    assert summary["additions"] == 5, summary
    assert summary["deletions"] == 0, summary


def test_the_control_an_unchanged_workspace_still_answers_zero(tmp_path: Path) -> None:
    """没有一行就没有「说不出」的一行：0 是答得出的 0。"""
    workspace = tmp_path / "empty"
    workspace.mkdir()
    (workspace / "kept.md").write_text("a\n", encoding="utf-8")
    _repo(workspace)
    _git(workspace, "add", "-A")
    _git(workspace, "commit", "-q", "-m", "init")
    summary = _summary(workspace)
    assert summary["files"] == [], summary
    assert (summary["additions"], summary["deletions"]) == (0, 0), summary


def test_the_control_a_git_counted_deletion_keeps_its_number(tmp_path: Path) -> None:
    """P4：删除由 git 数得出来，总数不许因为本批变成 `None`。"""
    workspace = tmp_path / "p4"
    workspace.mkdir()
    _repo(workspace)
    target = workspace / "gone.md"
    target.write_text("a\nb\nc\n", encoding="utf-8")
    _git(workspace, "add", "-A")
    _git(workspace, "commit", "-q", "-m", "init")
    target.unlink()
    summary = _summary(workspace)
    assert (summary["additions"], summary["deletions"]) == (0, 3), summary


def test_the_row_and_the_detail_page_still_answer_with_one_number(tmp_path: Path) -> None:
    """同一行在两头的 `None` 是同一个意思：本批只动求和，不动那一格的判法。"""
    workspace = tmp_path / "both"
    workspace.mkdir()
    (workspace / "a\udcff.md").write_text("one\ntwo\n", encoding="utf-8")
    (workspace / "a\ufffd.md").write_text("x\n", encoding="utf-8")
    _repo(workspace)
    inspector = ChangeInspector(workspace)
    summary = inspector.summary()
    row = _row(summary, "a\ufffd.md")
    diff = inspector.diff("a\ufffd.md")
    assert (row["additions"], row["name_resolution"]) == (None, "ambiguous"), row
    assert (diff["additions"], diff["deletions"]) == (None, None), diff
    assert summary["additions"] is None, summary
