"""M8-T566（第五百四十八批）：窗外那份配得上的副本，被答成「从来没记过」。

第五百四十四批让面板去 `.minicc/backup/` 读回删除之前的内容（`minicc/changes.py`
的 `_read_deletion_preimage`），第五百四十五批让清单跟着它数。它读的是**窗口里**的
行：`_audit_paths` 只把审计文件末尾 `_AUDIT_TAIL_BYTES`（`minicc/changes.py:61`）
个字节读进来，再只看最后 `_AUDIT_WINDOW_LINES`（`:57`）行（`minicc/changes.py:403`）。
一条 `backup` 行落在窗外，`_audit_backup_copies` 里就没有它（`:502`），配对落空，
`:549` 那一条兜底就把「我没看到」说成 `not-recorded`——和「轨迹从来没写过副本」
同一个词。

探针（`scratch/pre566/probe566.py`，在 `dd3d9e2` 的干净克隆里跑）量到的形状：

  Q1  窗口装得下：`copy`、清单 del=3、详情页补丁 83 字节
  Q2  `backup` 行被 256 KB 尾窗切掉 64,772 字节：`not-recorded`、del=0、补丁 0 字节，
      而 `summary["audit_window_truncated"]` 仍答 **False**——那一个布尔只数行
      （`:402`），字节窗外的 64,772 字节它一个字也没说
  Q3  整份文件 43,572 字节全在字节窗内，`backup` 行被 500 行上限挤掉：
      `not-recorded`，同一份 payload 里 `audit_window_truncated` 却是 True
  Q4  轨迹真没记过副本、窗口也没切：`not-recorded` 是**该说的**
  Q6  `delete` 行也在窗外：这一格根本不在清单里（total_files=0），详情页答 `clean`
  Q9  两条删除都在窗内、只有一条 `backup` 行在窗外：同一份 payload 里
      `notes.md`=`copy`/3 行，`other.md`=`not-recorded`/0 行——磁盘上两份副本都
      digest 得成各自的见证

本批把「窗口没读到」和「轨迹没写过」分成两个词（`not-in-window`），并把那一个
布尔换成「读者有没有看过整份轨迹」。
"""

from __future__ import annotations

import json
from pathlib import Path

from minicc import changes as changes_module
from minicc.changes import (
    _AUDIT_TAIL_BYTES,
    ChangeInspector,
)
from minicc.tools.editor import Editor, sha256_digest

BODY = "hello world\nsecond line\nthird line\n"
OTHER = "one\ntwo\n"


def _workspace(root: Path, name: str, files: dict[str, str]) -> Path:
    workspace = root / name
    for rel, body in files.items():
        target = workspace / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def _editor(workspace: Path) -> Editor:
    return Editor(workspace, audit_path=workspace / ".minicc" / "audit.jsonl")


def _trail(workspace: Path) -> Path:
    return workspace / ".minicc" / "audit.jsonl"


def _write_trail(workspace: Path, records: list[dict]) -> None:
    """Bytes, not ``write_text``: the window is counted in bytes.

    ``Path.write_text`` on this host turns every ``\\n`` into ``\\r\\n``, so a
    shape built to put the byte boundary inside one record would land it
    somewhere else.
    """
    trail = _trail(workspace)
    trail.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(json.dumps(record, ensure_ascii=False) for record in records)
    trail.write_bytes((body + "\n").encode("utf-8"))


def _lines(workspace: Path) -> list[str]:
    return _trail(workspace).read_text(encoding="utf-8").splitlines()


def _pair(workspace: Path, path: str) -> tuple[dict, dict]:
    """The ``backup`` and ``delete`` lines the editor wrote for one file."""
    records = [json.loads(line) for line in _lines(workspace)]
    backup = next(r for r in records if r.get("action") == "backup" and r.get("path") == path)
    delete = next(r for r in records if r.get("action") == "delete" and r.get("path") == path)
    return backup, delete


def _filler(count: int, width: int) -> list[dict]:
    return [
        {"action": "read", "path": "notes.md", "detail": "p" * width, "n": i}
        for i in range(count)
    ]


def _deleted(workspace: Path, path: str = "notes.md") -> None:
    _editor(workspace).delete(path)


def _diff(workspace: Path, path: str) -> dict:
    return ChangeInspector(workspace).diff(path)


def _row(workspace: Path, path: str) -> dict | None:
    return next(
        (item for item in ChangeInspector(workspace).summary()["files"] if item["path"] == path),
        None,
    )


def _bytes_outside(workspace: Path) -> int:
    return max(0, _trail(workspace).stat().st_size - _AUDIT_TAIL_BYTES)


def _trail_size(records: list[dict]) -> int:
    """How many bytes `_write_trail` will put on disk for these records."""
    body = "\n".join(json.dumps(record, ensure_ascii=False) for record in records)
    return len((body + "\n").encode("utf-8"))


# --------------------------------------------------------------------------
# 窗外那一份：本批要它换个词
# --------------------------------------------------------------------------

def test_a_copy_line_left_out_of_the_tail_is_not_a_copy_that_was_never_recorded(
    tmp_path: Path,
) -> None:
    """E2（探针 Q2）：`backup` 行在 256 KB 尾窗之外，`delete` 行在窗内。"""
    workspace = _workspace(tmp_path, "tail", {"notes.md": BODY})
    _deleted(workspace)
    backup, delete = _pair(workspace, "notes.md")
    _write_trail(workspace, [backup, *_filler(300, 1000), delete])
    assert _bytes_outside(workspace) > 0, _trail(workspace).stat().st_size
    diff = _diff(workspace, "notes.md")
    assert diff["status"] == "deleted", diff
    assert diff["deletion_preimage"] == "not-in-window", diff
    assert diff["patch"] == "", diff


def test_the_byte_window_is_disclosed_beside_the_word(tmp_path: Path) -> None:
    """那一个布尔问的是「读者看过整份轨迹吗」，不是「行数超上限了吗」。"""
    workspace = _workspace(tmp_path, "disclose", {"notes.md": BODY})
    _deleted(workspace)
    backup, delete = _pair(workspace, "notes.md")
    _write_trail(workspace, [backup, *_filler(300, 1000), delete])
    summary = ChangeInspector(workspace).summary()
    assert _bytes_outside(workspace) > 0, _trail(workspace).stat().st_size
    assert summary["audit_window_truncated"] is True, summary


def test_the_detail_page_says_which_half_of_the_trail_was_never_read(tmp_path: Path) -> None:
    """详情页是说出这个词的那一页：窗外这件事也得在它自己那一格里。"""
    workspace = _workspace(tmp_path, "detail", {"notes.md": BODY})
    _deleted(workspace)
    backup, delete = _pair(workspace, "notes.md")
    _write_trail(workspace, [backup, *_filler(300, 1000), delete])
    diff = _diff(workspace, "notes.md")
    assert diff["audit_window_truncated"] is True, diff
    assert diff["deletion_preimage"] == "not-in-window", diff


def test_a_copy_line_past_the_line_cap_is_read_not_answered_as_never_recorded(
    tmp_path: Path,
) -> None:
    """E4（探针 Q3，第五百四十九批改口）：整份文件都在字节窗内，`backup` 行排在第 602 条。

    第五百四十八批在这一格答 `not-in-window`——那是当时的事实：500 行上限把
    `backup` 行丢掉了。第五百四十九批把上限撤掉，这一行**读得到**，所以副本配得上，
    预像该答 `copy` 并给出内容。
    """
    workspace = _workspace(tmp_path, "cap", {"notes.md": BODY})
    _deleted(workspace)
    backup, delete = _pair(workspace, "notes.md")
    _write_trail(workspace, [backup, *_filler(600, 4), delete])
    assert _bytes_outside(workspace) == 0, _trail(workspace).stat().st_size
    diff = _diff(workspace, "notes.md")
    assert diff["deletion_preimage"] == "copy", diff
    assert "-hello world" in diff["patch"], diff


def test_a_record_split_by_the_byte_boundary_is_not_a_record_that_was_never_written(
    tmp_path: Path,
) -> None:
    """E5：尾窗的起点落在 `backup` 行**中间**——第五百五十六批把这条记录读了回来。

    第五百五十五批在这一格答 `not-in-window`：那时读者把开头那一行残片当已知残缺
    丢掉。这一格被切的是**文件的第一条**记录，它的头就在字节 0，回扫够得着，
    于是整条读回来、副本配得上、截断的说法跟着收回——窗外一个字节也没剩下。
    """
    workspace = _workspace(tmp_path, "split", {"notes.md": BODY})
    _deleted(workspace)
    backup, delete = _pair(workspace, "notes.md")
    filler = {"action": "read", "path": "notes.md", "detail": "", "n": 0}
    # Put the boundary inside the backup line: leave exactly half of it unread.
    target = _AUDIT_TAIL_BYTES + len(json.dumps(backup, ensure_ascii=False).encode("utf-8")) // 2
    filler_width = target - _trail_size([backup, filler, delete])
    assert filler_width > 0, (target, _trail_size([backup, filler, delete]))
    filler["detail"] = "p" * filler_width
    _write_trail(workspace, [backup, filler, delete])
    size = _trail(workspace).stat().st_size
    assert size == target, (size, target)
    unread = size - _AUDIT_TAIL_BYTES
    assert 0 < unread < len(json.dumps(backup, ensure_ascii=False).encode("utf-8")) + 1, unread
    assert _bytes_outside(workspace) > 0, size
    summary = ChangeInspector(workspace).summary()
    assert summary["audit_unreadable_lines"] == 0, summary
    assert summary["audit_records_split"] == 0, summary
    assert summary["audit_bytes_unread"] == 0, summary
    assert summary["audit_window_truncated"] is False, summary
    assert summary["files"][0]["deletion_preimage"] == "copy", summary["files"]


def test_a_split_beyond_the_recovery_reach_still_says_the_window_never_reached_it(
    tmp_path: Path,
) -> None:
    """E5b：同一条被切开的记录，头在回扫上限之外——那个词还得留着。

    `backup` 行整个在窗外，窗口的起点落在一条大 `read` 记录的 detail 里，而它自己
    的头离起点比 `_AUDIT_RECOVERY_BYTES` 还远。回扫够不着，残片照旧丢掉、记一条
    split，截断照旧披露，预像照旧答 `not-in-window`——不是 `not-recorded`。
    """
    workspace = _workspace(tmp_path, "beyond", {"notes.md": BODY})
    _deleted(workspace)
    backup, delete = _pair(workspace, "notes.md")
    reach = getattr(changes_module, "_AUDIT_RECOVERY_BYTES", 65_536)
    inside = reach + 4096
    pad = {"action": "read", "path": "notes.md", "detail": "", "n": 0}
    # size - TAIL - (backup line + its newline) == inside: the cut sits this far
    # into the pad record, so the back-scan of `reach` bytes stays inside it.
    width = inside + _AUDIT_TAIL_BYTES - len(json.dumps(delete, ensure_ascii=False).encode("utf-8")) - 2
    width -= len(json.dumps(pad, ensure_ascii=False).encode("utf-8"))
    assert width > 0, width
    pad["detail"] = "p" * width
    _write_trail(workspace, [backup, pad, delete])
    size = _trail(workspace).stat().st_size
    start = size - _AUDIT_TAIL_BYTES
    head_of_pad = len(json.dumps(backup, ensure_ascii=False).encode("utf-8")) + 1
    assert start - head_of_pad == inside, (start, head_of_pad, inside)
    assert start - head_of_pad > reach, (start, head_of_pad, reach)
    summary = ChangeInspector(workspace).summary()
    assert summary["audit_unreadable_lines"] == 0, summary
    assert summary["audit_records_split"] == 1, summary
    assert summary["audit_bytes_unread"] == start, summary
    assert summary["audit_window_truncated"] is True, summary
    assert summary["files"][0]["deletion_preimage"] == "not-in-window", summary["files"]


# --------------------------------------------------------------------------
# 对照：这些形状本来就说对了，本批不许改口
# --------------------------------------------------------------------------

def test_the_trail_that_never_recorded_a_copy_still_says_so(tmp_path: Path) -> None:
    """E6（探针 Q4）：窗口没切、轨迹也确实没写过副本——`not-recorded` 才是答案。"""
    workspace = _workspace(tmp_path, "never", {"notes.md": BODY})
    digest = sha256_digest(BODY.encode("utf-8"))
    _write_trail(workspace, [{"action": "delete", "path": "notes.md", "detail": "", "before_digest": digest}])
    (workspace / "notes.md").unlink()
    assert _bytes_outside(workspace) == 0, _trail(workspace).stat().st_size
    diff = _diff(workspace, "notes.md")
    assert diff["deletion_preimage"] == "not-recorded", diff
    assert ChangeInspector(workspace).summary()["audit_window_truncated"] is False, diff


def test_the_copy_inside_the_window_is_still_read(tmp_path: Path) -> None:
    """E1（探针 Q1）：两行都看得见时，内容照旧从副本里读回来。"""
    workspace = _workspace(tmp_path, "in-window", {"notes.md": BODY})
    _deleted(workspace)
    diff = _diff(workspace, "notes.md")
    assert diff["deletion_preimage"] == "copy", diff
    assert diff["deletions"] == 3, diff
    assert "-hello world" in diff["patch"], diff
    assert ChangeInspector(workspace).summary()["audit_window_truncated"] is False, diff
    assert _row(workspace, "notes.md")["deletions"] == 3, _row(workspace, "notes.md")


def test_a_pruned_copy_seen_in_window_outweighs_the_window_being_cut(tmp_path: Path) -> None:
    """窗外什么也没看见，窗内却看见一条点了名、文件却被裁剪掉的副本——说 `not-readable`。

    「有一份副本，我打不开」是本批那个词不允许顶替的事实。
    """
    workspace = _workspace(tmp_path, "pruned", {"notes.md": BODY})
    _deleted(workspace)
    backup, delete = _pair(workspace, "notes.md")
    for copy in (workspace / ".minicc" / "backup").iterdir():
        copy.unlink()
    _write_trail(workspace, [*_filler(600, 4), backup, delete])
    diff = _diff(workspace, "notes.md")
    assert diff["deletion_preimage"] == "not-readable", diff


# --------------------------------------------------------------------------
# 一格一格：同一份 payload 里两个答案各说各的窗外
# --------------------------------------------------------------------------

def test_two_deletions_speak_for_themselves_when_only_one_copy_line_is_outside(
    tmp_path: Path,
) -> None:
    """E7（探针 Q9）：两条 `delete` 都在窗内，只有 `other.md` 的副本行在窗外。"""
    workspace = _workspace(tmp_path, "mixed", {"notes.md": BODY, "other.md": OTHER})
    editor = _editor(workspace)
    editor.delete("other.md")
    editor.delete("notes.md")
    other_backup, other_delete = _pair(workspace, "other.md")
    notes_backup, notes_delete = _pair(workspace, "notes.md")
    _write_trail(
        workspace,
        [other_backup, *_filler(300, 1000), notes_backup, other_delete, notes_delete],
    )
    files = {item["path"]: item for item in ChangeInspector(workspace).summary()["files"]}
    assert files["notes.md"]["deletion_preimage"] == "copy", files
    assert files["other.md"]["deletion_preimage"] == "not-in-window", files
    # 磁盘上那两份都不是幻影：各自 digest 成轨迹里那一条 `delete` 行的见证。
    witnesses = {
        record["path"]: record["before_digest"]
        for record in map(json.loads, _lines(workspace))
        if record.get("action") == "delete"
    }
    directory = workspace / ".minicc" / "backup"
    digests = {sha256_digest(p.read_bytes()) for p in directory.iterdir()}
    assert digests == set(witnesses.values()), (digests, witnesses)


def test_the_lost_row_still_counts_zero_lines(tmp_path: Path) -> None:
    """本批只换词，不换数：窗外那一份的行数在清单里仍是 0。

    这一条钉的是本批**没做**的那一步（§6 第 3 条）。下一批要让数也老实起来，
    就得到这里来改口——它不该被静默地改掉。
    """
    workspace = _workspace(tmp_path, "number", {"notes.md": BODY})
    _deleted(workspace)
    backup, delete = _pair(workspace, "notes.md")
    _write_trail(workspace, [backup, *_filler(300, 1000), delete])
    row = _row(workspace, "notes.md")
    assert row is not None and row["deletion_preimage"] == "not-in-window", row
    assert (row["additions"], row["deletions"]) == (0, 0), row


# --------------------------------------------------------------------------
# 家规
# --------------------------------------------------------------------------

def test_the_preimage_vocabulary_has_one_home(tmp_path: Path) -> None:
    """五个词只在 `minicc/changes.py` 里拼一次，别处不许自己抄一个。"""
    import inspect
    import subprocess

    source = inspect.getsource(changes_module)
    for word in ("copy", "not-recorded", "not-readable", "digest-mismatch", "not-in-window"):
        assert f'"{word}"' in source, word
    tracked = subprocess.run(
        ["git", "ls-files", "--", "*.py", "*.js"],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="surrogateescape",
    ).stdout.splitlines()
    spellers = []
    root = Path(__file__).resolve().parents[1]
    for rel in tracked:
        if rel.startswith("tests/") or not (root / rel).is_file():
            continue
        body = (root / rel).read_text(encoding="utf-8", errors="replace")
        if "not-in-window" in body and rel != "minicc/changes.py":
            spellers.append(rel)
    assert spellers == [], spellers


def test_the_window_falls_back_to_the_word_only_when_nothing_was_seen(tmp_path: Path) -> None:
    """`not-in-window` 只站在最后那一条兜底上：三条有事实的路不许它插话。"""
    import inspect

    source = inspect.getsource(changes_module.ChangeInspector._read_deletion_preimage)
    assert source.index("PREIMAGE_MISMATCH") < source.index("PREIMAGE_NOT_IN_WINDOW")
    assert source.index("PREIMAGE_NOT_READABLE") < source.index("PREIMAGE_NOT_IN_WINDOW")
    assert source.count("return PREIMAGE_NOT_RECORDED") == 1
    assert source.count("return PREIMAGE_NOT_IN_WINDOW") == 1
