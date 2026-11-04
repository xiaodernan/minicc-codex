"""M8-T568（第五百五十批）：只读了一半的轨迹，撑不起一个「干净」。

第五百四十九批把「窗切过」和「切掉多少字节」带进了详情页的 payload，可决定这页
补丁空不空的那道条件（`minicc/changes.py:863`～`:870`）没看它们：文件在磁盘上、
没有基线、状态是兜底来的 `clean`，于是 `before = after`、补丁 0 字节、`+0/-0`——
与「整份轨迹读完、确实没人点过这个名」同一个答案。探针 `scratch/probe568.py`：

  X1  265,050 字节的轨迹，写记录在尾窗之前   -> 详情页 clean、补丁 0 行、+0/-0
  X2  删除记录也在尾窗之前                   -> 同样 clean（本批不改这一条）
  X3  同一份记录不越界                       -> modified、+3（答案本来就对）
  X4  窗切过、这一格在窗内                   -> modified、+1（不该一律不答）
  X5  轨迹读不出来（对照上一族）             -> 兜底让路：补丁 6 行、+3
  X7  git 读得到、已提交且没动、轨迹切过     -> clean、0 行（git 说话，本批不动）
  X8  gitignore 里的文件、轨迹切过           -> clean、0 行
  X9  没有 git、窗没切过、没人点名           -> clean、0 行（读出来的，站得住）
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from minicc import changes as changes_module
from minicc.changes import ChangeInspector

TAIL = changes_module._AUDIT_TAIL_BYTES


def _workspace(root: Path, name: str, files: dict[str, str] | None = None) -> Path:
    workspace = root / name
    for rel, body in (files or {"keep.md": "stay\n"}).items():
        target = workspace / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body.encode("utf-8"))
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def _record(action: str, path: str, detail: str = "") -> bytes:
    item = {"action": action, "path": path, "detail": detail}
    return json.dumps(item, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"


def _edit(path: str, detail: str = "written") -> bytes:
    return _record("edit", path, detail)


def _pad(extra: int = 9_000) -> bytes:
    """一条把尾窗顶到记录中间、且比尾窗多出 ``extra`` 字节的填充记录。"""
    return _record("edit", "pad.md", "0" * (TAIL + extra - 60))


def _write(workspace: Path, blobs: list[bytes]) -> int:
    path = workspace / ".minicc" / "audit.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = b"".join(blobs)
    path.write_bytes(data)
    return len(data)


def _commit(workspace: Path) -> None:
    subprocess.run(["git", "init", "-q", "."], cwd=workspace, check=True)
    subprocess.run(["git", "add", "-A"], cwd=workspace, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=gate",
            "-c",
            "user.email=gate@minicc.local",
            "commit",
            "-q",
            "-m",
            "baseline",
        ],
        cwd=workspace,
        check=True,
    )


def _diff(workspace: Path, path: str) -> dict:
    return ChangeInspector(workspace).diff(path)


def _summary(workspace: Path) -> dict:
    return ChangeInspector(workspace).summary()


# --------------------------------------------------------------------------
# 窗外那一次写：兜底撑不住
# --------------------------------------------------------------------------

def test_a_write_recorded_before_the_window_shows_its_bytes(tmp_path: Path) -> None:
    """X1：写记录在尾窗之前——「干净」是猜的，字节得画出来。"""
    workspace = _workspace(tmp_path, "outside", {"late.md": "one\ntwo\nthree\n"})
    _write(workspace, [_edit("late.md"), _pad()])
    diff = _diff(workspace, "late.md")
    assert diff["audit_window_truncated"] is True, diff
    assert diff["patch"].strip(), f"窗外的写被画成了空补丁：{diff}"
    assert "+one" in diff["patch"], diff["patch"]
    assert diff["additions"] == 3, diff


def test_the_number_beside_the_patch_says_what_was_not_read(tmp_path: Path) -> None:
    """同一个现场：补丁不再为空，「没读的字节」这个数也还在。"""
    workspace = _workspace(tmp_path, "outside-number", {"late.md": "one\ntwo\nthree\n"})
    size = _write(workspace, [_edit("late.md"), _pad()])
    diff = _diff(workspace, "late.md")
    assert diff["audit_bytes_unread"] == size - TAIL, diff
    assert diff["audit_read_error"] is None, diff


def test_an_ignored_file_with_a_cut_trail_shows_its_bytes(tmp_path: Path) -> None:
    """X8：gitignore 里的文件——git 不说，窗外也可能有人点过名。"""
    workspace = _workspace(
        tmp_path, "ignored", {".gitignore": "hidden.txt\n", "hidden.txt": "a\nb\nc\nd\n"}
    )
    _commit(workspace)
    _write(workspace, [_edit("hidden.txt", "old"), _pad()])
    diff = _diff(workspace, "hidden.txt")
    assert diff["audit_window_truncated"] is True, diff
    assert diff["patch"].strip(), f"窗外可能有一次写，补丁却是空的：{diff}"
    assert diff["additions"] == 4, diff


# --------------------------------------------------------------------------
# 本批**不**改的那几格：控制
# --------------------------------------------------------------------------

def test_the_status_word_this_batch_does_not_rename(tmp_path: Path) -> None:
    """状态这一格本批不动：词还是 `clean`，改的是那道兜底条件。"""
    workspace = _workspace(tmp_path, "word", {"late.md": "one\ntwo\nthree\n"})
    _write(workspace, [_edit("late.md"), _pad()])
    diff = _diff(workspace, "late.md")
    assert diff["status"] == "clean", diff
    assert diff["source"] == "git-or-empty-baseline", diff


def test_a_trail_read_whole_still_answers_an_empty_patch(tmp_path: Path) -> None:
    """X9：整份轨迹读完了、没人点过这个名——`clean` 是读出来的，站得住。"""
    workspace = _workspace(tmp_path, "whole", {"quiet.md": "a\nb\n"})
    _write(workspace, [_edit("elsewhere.md")])
    diff = _diff(workspace, "quiet.md")
    assert diff["audit_window_truncated"] is False, diff
    assert diff["audit_bytes_unread"] == 0, diff
    assert diff["patch"] == "", diff
    assert diff["additions"] == 0, diff


def test_a_committed_untouched_file_is_not_turned_into_an_addition(
    tmp_path: Path,
) -> None:
    """X7：git 读得到、已提交且没动——轨迹切过也不把整份文件画成新增。"""
    workspace = _workspace(tmp_path, "committed", {"kept.md": "one\ntwo\nthree\n"})
    _commit(workspace)
    _write(workspace, [_edit("other.md", "old"), _pad()])
    diff = _diff(workspace, "kept.md")
    assert diff["audit_window_truncated"] is True, diff
    assert diff["status"] == "clean", diff
    assert diff["patch"] == "", diff
    assert diff["additions"] == 0, diff


def test_a_file_named_inside_the_window_is_still_modified(tmp_path: Path) -> None:
    """X4：窗切过、这一格在窗内——不该因为「切过」就一律不答。"""
    workspace = _workspace(tmp_path, "inside", {"seen.md": "a\n"})
    _write(workspace, [_pad(), _edit("seen.md")])
    diff = _diff(workspace, "seen.md")
    assert diff["status"] == "modified", diff
    assert diff["additions"] == 1, diff
    assert diff["audit_window_truncated"] is True, diff


def test_a_file_no_source_named_at_all_is_not_claimed_as_a_change(
    tmp_path: Path,
) -> None:
    """磁盘上没有这个文件：兜底本来就没走，本批也不让它走。"""
    workspace = _workspace(tmp_path, "missing", {"seen.md": "a\n"})
    _write(workspace, [_pad(), _edit("seen.md")])
    diff = _diff(workspace, "never_mentioned.md")
    assert diff["status"] == "clean", diff
    assert diff["patch"] == "", diff


def test_a_file_deleted_before_the_window_is_still_not_in_the_list(
    tmp_path: Path,
) -> None:
    """X2：删除记录本身也在窗外——本批一个词也加不上，钉住「没改这个」。"""
    workspace = _workspace(tmp_path, "deleted-outside", {"gone.md": "x\n"})
    (workspace / "gone.md").unlink()
    _write(workspace, [_record("delete", "gone.md"), _pad()])
    summary = _summary(workspace)
    diff = _diff(workspace, "gone.md")
    assert summary["audit_window_truncated"] is True, summary
    assert [item["path"] for item in summary["files"]] == [], summary["files"]
    assert diff["status"] == "clean", diff
    assert diff["patch"] == "", diff


def test_the_list_does_not_gain_a_row_from_the_detail_page_fix(
    tmp_path: Path,
) -> None:
    """X1 的清单那一头：窗外那条记录点不出名，本批只改详情页。"""
    workspace = _workspace(tmp_path, "list-unchanged", {"late.md": "one\ntwo\n"})
    _write(workspace, [_edit("late.md"), _pad()])
    summary = _summary(workspace)
    assert summary["total_files"] == 0, summary
    assert summary["audit_bytes_unread"] > 0, summary
