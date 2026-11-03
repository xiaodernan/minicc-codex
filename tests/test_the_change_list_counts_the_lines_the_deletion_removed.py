"""M8-T563（第五百四十五批）：清单说 0 行，详情页说 del=N——同一件事两个答案。

第五百四十四批让详情页读回了删除前的内容，探针 `probe_563` 在同一份 payload 上
量到两处答案对不上：

  S1  无仓库真跑 delete         清单 `add=0 del=0`，详情页 `del=3`
  S3  git 仓库里被 ignore 挡住  清单 0/0，详情页 del=2
  S4  从没提交过的文件被删      清单 0/0，详情页 del=2
  S6  write 之后再 delete       清单 0/0，详情页 del=1（数的是删除那一份副本）
  S7  两条删除的总和            清单 `sum_del=0`，两条详情页各说 3 与 1
  S12 create 之后 delete        清单 0/0，详情页 del=1
  S2  对照：git 看得见这条删除  两处都是 3（本批不动）
  S8  副本被裁剪掉              两处都是 0——而「没数出来」与「数到 0」是两件事
  S11 先算清单再裁剪副本        清单第二趟仍吃缓存

清单那一格的数从来不知道这件事：`_computed_files` 只从 numstat 取
（`minicc/changes.py:518`），无仓库时退成「工作区里现在有几行」（`:524`），
一条已经不在的文件于是永远是 0/0，而 `summary()` 的总和把这些 0 加起来
（`:777`）报给面板与模型。

计数口径也得一并统一：详情页的 `deletions` 数的是补丁里的 `-` 行
（`minicc/changes.py:689`），它拿 `startswith("---")` 跳文件头，于是**内容里
那行本身以 `--` 开头**时被当成表头不算——`probe563b` 实测 `-- config line`
那份两行的文件详情页说 `del=1`。清单若改按 `splitlines()` 数就是 2，同一个病
换个方向再犯一次。两处共用水一把尺子，才谈得上「一个答案」。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from minicc.changes import (
    PREIMAGE_MISMATCH,
    PREIMAGE_NOT_READABLE,
    PREIMAGE_NOT_RECORDED,
    PREIMAGE_READ,
    ChangeInspector,
)
from minicc.tools.editor import Editor, sha256_digest

FILES = {"notes.md": "hello world\nsecond line\n", "keep.txt": "stay\n"}


def _workspace(root: Path, name: str, files: dict[str, str] | None = None) -> Path:
    workspace = root / name
    for rel, body in (files if files is not None else FILES).items():
        target = workspace / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        # newline="" 让字节逐字落盘：`\r\n` 形状在 Windows 上不许被翻译成 `\r\r\n`。
        with target.open("w", encoding="utf-8", newline="") as handle:
            handle.write(body)
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def _repo(workspace: Path) -> Path:
    for argv in (
        ["git", "init", "-q"],
        ["git", "config", "user.email", "t563@example.com"],
        ["git", "config", "user.name", "t563"],
        ["git", "add", "-A"],
        ["git", "commit", "-qm", "base"],
    ):
        subprocess.run(argv, cwd=workspace, check=True, capture_output=True)
    return workspace


def _editor(workspace: Path) -> Editor:
    return Editor(workspace, audit_path=workspace / ".minicc" / "audit.jsonl")


def _audit(workspace: Path, records: list[dict]) -> None:
    trail = workspace / ".minicc" / "audit.jsonl"
    trail.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(json.dumps(record, ensure_ascii=False) for record in records)
    trail.write_text(body + "\n", encoding="utf-8")


def _backup_dir(workspace: Path) -> Path:
    return workspace / ".minicc" / "backup"


def _prune_copies(workspace: Path) -> None:
    for copy in _backup_dir(workspace).iterdir():
        copy.unlink()


def _row(workspace: Path, path: str) -> dict:
    for item in ChangeInspector(workspace).summary()["files"]:
        if item["path"] == path:
            return item
    raise AssertionError(f"{path} 没在清单里")


def _diff(workspace: Path, path: str) -> dict:
    return ChangeInspector(workspace).diff(path)


def _summary(workspace: Path) -> dict:
    return ChangeInspector(workspace).summary()


# --------------------------------------------------------------------------
# 清单跟着详情页读回来的那份内容走
# --------------------------------------------------------------------------

def test_a_listed_deletion_reports_the_lines_the_copy_kept(tmp_path: Path) -> None:
    """副本里躺着两行，清单那一格就不能说 0——面板不能一边说删了它一边说没拿走东西。"""
    workspace = _workspace(tmp_path, "S1")
    _editor(workspace).delete("notes.md")
    entry = _row(workspace, "notes.md")
    assert (entry["status"], entry["raw"]) == ("deleted", "audit"), entry
    assert entry["deletions"] == 2, entry
    assert entry["additions"] == 0, entry


def test_the_summary_total_counts_the_lines_the_copies_kept(tmp_path: Path) -> None:
    """总和是清单各行加起来；各行都报 0 的总和，说出口就是「这些删除没拿走一行」。"""
    workspace = _workspace(tmp_path, "S7")
    editor = _editor(workspace)
    editor.delete("notes.md")
    editor.delete("keep.txt")
    summary = _summary(workspace)
    assert summary["total_files"] == 2, summary
    assert summary["deletions"] == 3, summary
    assert summary["additions"] == 0, summary


def test_the_list_and_the_detail_page_answer_the_same_number(tmp_path: Path) -> None:
    """同一份 payload 里两处答案相等——这就是本批要钉的那件事本身。"""
    for name, body in (
        ("plain", "one\ntwo\nthree\n"),
        ("no_trailing_newline", "one\ntwo"),
        ("one_blank_line", "\n"),
        ("crlf", "one\r\ntwo\r\n"),
    ):
        workspace = _workspace(tmp_path, name, {"notes.md": body, "keep.txt": "stay\n"})
        _editor(workspace).delete("notes.md")
        entry = _row(workspace, "notes.md")
        detail = _diff(workspace, "notes.md")
        assert entry["deletions"] == detail["deletions"], (name, entry, detail)
        assert entry["deletions"] == len(body.splitlines()), (name, entry)


def test_the_word_for_the_number_is_the_word_the_detail_page_uses(tmp_path: Path) -> None:
    """数的出处那一格不许自造第五个词——它与详情页的 `deletion_preimage` 是同一件事。"""
    workspace = _workspace(tmp_path, "S1w")
    _editor(workspace).delete("notes.md")
    entry = _row(workspace, "notes.md")
    assert entry["deletion_preimage"] == PREIMAGE_READ, entry
    assert entry["deletion_preimage"] == _diff(workspace, "notes.md")["deletion_preimage"], entry


def test_a_deleted_line_that_reads_like_a_patch_header_is_still_counted(tmp_path: Path) -> None:
    """内容里那行以 `--` 起头，补丁把它印成 `---` 起头——它仍是一行被删掉的内容。"""
    workspace = _workspace(tmp_path, "H1", {"notes.md": "-- config line\nsecond\n", "keep.txt": "stay\n"})
    _editor(workspace).delete("notes.md")
    detail = _diff(workspace, "notes.md")
    assert detail["deletions"] == 2, detail
    assert _row(workspace, "notes.md")["deletions"] == 2, _row(workspace, "notes.md")


def test_an_added_line_that_reads_like_a_patch_header_is_still_counted(tmp_path: Path) -> None:
    """同一把尺子的另一头：以 `++` 起头的一行新增也不是表头。"""
    workspace = _workspace(tmp_path, "H2")
    _editor(workspace).write_file("notes.md", "++ build flag\nsecond\n")
    detail = _diff(workspace, "notes.md")
    assert detail["additions"] == 2, detail
    assert _row(workspace, "notes.md")["additions"] == 2, _row(workspace, "notes.md")


def test_the_count_follows_the_copy_the_deletion_made(tmp_path: Path) -> None:
    """先改后删：删除那一行的副本是一行，不是最初那三行。"""
    workspace = _workspace(tmp_path, "S6", {"notes.md": "one\ntwo\nthree\n", "keep.txt": "stay\n"})
    editor = _editor(workspace)
    editor.write_file("notes.md", "changed once\n")
    editor.delete("notes.md")
    entry = _row(workspace, "notes.md")
    assert entry["deletions"] == 1, entry
    assert entry["deletions"] == _diff(workspace, "notes.md")["deletions"], entry


def test_a_deleted_file_git_never_saw_is_counted_from_the_copy(tmp_path: Path) -> None:
    """仓库里被 .gitignore 挡住的位置：git 从来没数过它，数得出来的是磁盘上那份副本。"""
    workspace = _repo(_workspace(tmp_path, "S3", {"notes.md": "a\nb\nc\n", "keep.txt": "stay\n"}))
    (workspace / ".gitignore").write_text("ignored.md\n", encoding="utf-8")
    (workspace / "ignored.md").write_text("one\ntwo\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=workspace, check=True)
    subprocess.run(["git", "commit", "-qm", "ignore"], cwd=workspace, check=True)
    _editor(workspace).delete("ignored.md")
    assert _row(workspace, "ignored.md")["deletions"] == 2, _row(workspace, "ignored.md")


def test_an_untracked_deletion_in_a_repo_is_counted_from_the_copy(tmp_path: Path) -> None:
    """从没提交过的文件被删：git 里没有它的账，副本里有它的字节。"""
    workspace = _repo(_workspace(tmp_path, "S4", {"notes.md": "a\nb\nc\n", "keep.txt": "stay\n"}))
    (workspace / "fresh.md").write_text("never committed\nat all\n", encoding="utf-8")
    _editor(workspace).delete("fresh.md")
    entry = _row(workspace, "fresh.md")
    assert entry["deletions"] == 2, entry
    assert entry["deletions"] == _diff(workspace, "fresh.md")["deletions"], entry


def test_a_deletion_past_the_cap_still_counts_into_the_total(tmp_path: Path) -> None:
    """M8-T307 承诺过总和覆盖每一个文件；一条删除行不该在总账里是 0。"""
    import minicc.changes as changes_module

    workspace = _workspace(tmp_path, "S7cap", {"a.md": "1\n2\n", "b.md": "1\n2\n3\n"})
    editor = _editor(workspace)
    editor.delete("a.md")
    editor.delete("b.md")
    original = changes_module._MAX_FILES
    changes_module._MAX_FILES = 1
    try:
        summary = _summary(workspace)
        assert len(summary["files"]) == 1, summary
        assert summary["deletions"] == 5, summary
    finally:
        changes_module._MAX_FILES = original


# --------------------------------------------------------------------------
# 数不出来的那一路：0 要说清是数到的 0 还是没数
# --------------------------------------------------------------------------

def test_a_copy_pruned_after_the_list_ran_is_not_still_counted(tmp_path: Path) -> None:
    """清单吃缓存；副本被裁剪掉之后那个数得跟着磁盘重算，不许继续报旧账。"""
    workspace = _workspace(tmp_path, "S11")
    _editor(workspace).delete("notes.md")
    first = _row(workspace, "notes.md")
    assert (first["deletions"], first["deletion_preimage"]) == (2, PREIMAGE_READ), first
    _prune_copies(workspace)
    second = _row(workspace, "notes.md")
    assert second["deletion_preimage"] == PREIMAGE_NOT_READABLE, second
    assert second["deletions"] == 0, second


def test_a_deletion_whose_copy_cannot_be_read_says_so_instead_of_nothing(tmp_path: Path) -> None:
    """一条都没读过就先答 0，那个 0 就与「这里本来没有内容」同词——读失败运动的老形状。"""
    workspace = _workspace(tmp_path, "S8")
    editor = _editor(workspace)
    editor.delete("notes.md")
    _prune_copies(workspace)
    entry = _row(workspace, "notes.md")
    assert entry["deletion_preimage"] == PREIMAGE_NOT_READABLE, entry
    assert entry["deletions"] == 0, entry
    assert entry["deletions"] == _diff(workspace, "notes.md")["deletions"], entry


def test_a_deletion_that_never_named_a_copy_says_not_recorded(tmp_path: Path) -> None:
    """delete 行有 witness、窗口里没有配得上它的 backup 行——这是「没记过」，不是「没内容」。"""
    workspace = _workspace(tmp_path, "N1")
    digest = sha256_digest(FILES["notes.md"].encode("utf-8"))
    _audit(workspace, [{"action": "delete", "path": "notes.md", "detail": "", "before_digest": digest}])
    (workspace / "notes.md").unlink()
    entry = _row(workspace, "notes.md")
    assert entry["deletion_preimage"] == PREIMAGE_NOT_RECORDED, entry
    assert entry["deletions"] == 0, entry


def test_a_copy_that_no_longer_digests_to_the_witness_says_so(tmp_path: Path) -> None:
    """副本后来被改写：数它等于数别人的内容，那一格要说 digest-mismatch。"""
    workspace = _workspace(tmp_path, "N2")
    editor = _editor(workspace)
    editor.delete("notes.md")
    for copy in _backup_dir(workspace).iterdir():
        copy.write_bytes(b"somebody overwrote this\n")
    entry = _row(workspace, "notes.md")
    assert entry["deletion_preimage"] == PREIMAGE_MISMATCH, entry
    assert entry["deletions"] == 0, entry


def test_an_empty_deleted_file_is_a_counted_zero(tmp_path: Path) -> None:
    """读回来了、内容确实是空——这个 0 是数出来的，得与「没数出来」分得开。"""
    workspace = _workspace(tmp_path, "Z1", {"notes.md": "", "keep.txt": "stay\n"})
    _editor(workspace).delete("notes.md")
    entry = _row(workspace, "notes.md")
    assert entry["deletion_preimage"] == PREIMAGE_READ, entry
    assert entry["deletions"] == 0, entry
    assert entry["additions"] == 0, entry


# --------------------------------------------------------------------------
# 不抢 git 的账
# --------------------------------------------------------------------------

def test_a_deletion_git_already_counted_keeps_gits_number(tmp_path: Path) -> None:
    """git 数的是 HEAD 那一版，副本数的是删除那一版——本批只补那些没有数的格子。"""
    workspace = _repo(_workspace(tmp_path, "S2", {"notes.md": "one\ntwo\nthree\n", "keep.txt": "stay\n"}))
    editor = _editor(workspace)
    editor.write_file("notes.md", "changed\n")
    editor.delete("notes.md")
    entry = _row(workspace, "notes.md")
    assert entry["deletions"] == 3, entry
    assert entry["raw"].startswith(" D"), entry
    assert "deletion_preimage" not in entry, entry


def test_a_write_still_counts_the_lines_that_are_here(tmp_path: Path) -> None:
    """对照：改动的文件在本批之外，那一路的数法一个字都没动。"""
    workspace = _workspace(tmp_path, "S5")
    _editor(workspace).write_file("notes.md", "a\nb\nc\n")
    entry = _row(workspace, "notes.md")
    assert (entry["status"], entry["additions"], entry["deletions"]) == ("modified", 3, 0), entry
    assert "deletion_preimage" not in entry, entry


def test_a_file_that_is_back_is_not_counted_as_removed(tmp_path: Path) -> None:
    """对照：删掉又写回来，清单说的是现在这几行，不问副本。"""
    workspace = _workspace(tmp_path, "S9")
    editor = _editor(workspace)
    editor.delete("notes.md")
    editor.write_file("notes.md", "back\nagain\n")
    entry = _row(workspace, "notes.md")
    assert (entry["status"], entry["additions"], entry["deletions"]) == ("modified", 2, 0), entry
    assert "deletion_preimage" not in entry, entry


def test_a_clean_tree_lists_no_numbers(tmp_path: Path) -> None:
    """对照：没有变更就没有行，本批不给空清单造一格 0。"""
    workspace = _workspace(tmp_path, "C1")
    summary = _summary(workspace)
    assert summary["files"] == [], summary
    assert (summary["additions"], summary["deletions"]) == (0, 0), summary


def test_the_counted_number_is_served_from_the_memo_when_nothing_changed(tmp_path: Path, monkeypatch) -> None:
    """清单的缓存不许因为本批多读了一格就失效：什么都没变的第二趟不该再去读副本。"""
    workspace = _workspace(tmp_path, "M1")
    _editor(workspace).delete("notes.md")
    assert ChangeInspector(workspace).summary()["files"][0]["deletions"] == 2
    calls: list[str] = []
    original = ChangeInspector._read_deletion_preimage

    def counting(self, path: str) -> tuple[str, str]:
        calls.append(path)
        return original(self, path)

    monkeypatch.setattr(ChangeInspector, "_read_deletion_preimage", counting)
    again = ChangeInspector(workspace).summary()["files"][0]
    assert again["deletions"] == 2, again
    assert calls == [], calls


# --------------------------------------------------------------------------
# 家规：一个数法、一套词
# --------------------------------------------------------------------------

def test_the_patch_lines_are_counted_in_one_place(tmp_path: Path) -> None:
    """`+`/`-` 的数法只许有一个家；两处各自数一遍是本批要修的病，不许留下第二遍。"""
    import inspect

    from minicc import changes as changes_module

    source = inspect.getsource(changes_module)
    assert source.count('startswith("+")') == 1, source.count('startswith("+")')
    assert source.count('startswith("-")') == 1, source.count('startswith("-")')
    assert source.count("def _patch_counts(") == 1
    assert "_patch_counts(patch)" in source, "详情页没有走那把唯一的尺子"


def test_the_stale_memo_is_the_fingerprint_job(tmp_path: Path) -> None:
    """指纹里那份「副本的账」只许有一个家，且它数的是要打开的那几份。"""
    import inspect

    from minicc import changes as changes_module

    source = inspect.getsource(changes_module)
    assert source.count("def _preimage_signature(") == 1
    assert source.count("self._preimage_signature(") == 1, "指纹里只有一处吃它"
    assert "digest != witness" in source, "指纹没有限制在真会打开的那几份副本"


def test_a_row_never_invents_a_fifth_word(tmp_path: Path) -> None:
    """清单那一格的词只能取自详情页那四个常量——多一个说法就是多一个家。"""
    workspace = _workspace(tmp_path, "W1")
    _editor(workspace).delete("notes.md")
    readable = _row(workspace, "notes.md")["deletion_preimage"]

    other = _workspace(tmp_path, "W2")
    editor = _editor(other)
    editor.delete("notes.md")
    _prune_copies(other)
    pruned = _row(other, "notes.md")["deletion_preimage"]

    allowed = {PREIMAGE_READ, PREIMAGE_NOT_RECORDED, PREIMAGE_NOT_READABLE, PREIMAGE_MISMATCH}
    assert {readable, pruned} <= allowed, (readable, pruned)
