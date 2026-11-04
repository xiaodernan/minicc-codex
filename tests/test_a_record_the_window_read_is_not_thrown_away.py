"""M8-T567（第五百四十九批）：窗口读进来的每一行都得算数。

第五百四十八批量到的是「我没看到」说不出；这一批量到的是更难看的：**已经读到手**
的记录被 500 行上限丢掉了，一个数都不说；而字节切点落在记录边界上时，整条记录
也会被当成残片丢掉。两支探针的现场（`scratch/probe567.py`、`scratch/probe567b.py`）：

  E1  34,332 字节 / 601 行的轨迹，第一条是 delete   -> 清单 0 个文件、详情页 clean
  E2  同一份轨迹解析 500 行、丢掉 101 行            -> payload 里没有任何数
  E3  320,937 字节的轨迹（1269 条记录）             -> 64,937 字节从没读，键里没有数
  E4  切点正好落在整条 delete 记录的第一个字节      -> 那条记录照样被丢
  E5  300 个磁盘上真有的文件                        -> 上限与全解析都 ~1.5 s（逐文件 diff 主导）
  E6  本仓库自己的 .minicc/audit.jsonl              -> 298,447 字节 / 1270 行
  E7  轨迹不是一个文件                              -> 读失败；「没读的字节」该答不知道
  E8  轨迹根本不存在                                -> 没东西可读，0 是对的
  E9  字节切点落在一条记录中间                      -> 残片丢掉，且不算「读不出来的一行」
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from minicc import changes as changes_module
from minicc.changes import ChangeInspector
from minicc.tools.editor import Editor

TAIL = changes_module._AUDIT_TAIL_BYTES
DIGEST = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def _workspace(root: Path, name: str, files: dict[str, str] | None = None) -> Path:
    workspace = root / name
    for rel, body in (files or {"keep.md": "stay\n"}).items():
        target = workspace / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body.encode("utf-8"))
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def _trail_path(workspace: Path) -> Path:
    return workspace / ".minicc" / "audit.jsonl"


def _write(workspace: Path, blobs: list[bytes]) -> int:
    path = _trail_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = b"".join(blobs)
    path.write_bytes(data)
    return len(data)


def _record(action: str, path: str, detail: str = "", **extra) -> bytes:
    item = {"action": action, "path": path, "detail": detail, **extra}
    return json.dumps(item, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"


def _delete(path: str, detail: str = "") -> bytes:
    return _record("delete", path, detail, before_digest=DIGEST)


def _edit(path: str, detail: str = "written") -> bytes:
    return _record("edit", path, detail)


def _editor(workspace: Path) -> Editor:
    return Editor(workspace, audit_path=_trail_path(workspace))


def _summary(workspace: Path) -> dict:
    return ChangeInspector(workspace).summary()


def _diff(workspace: Path, path: str) -> dict:
    return ChangeInspector(workspace).diff(path)


def _size(workspace: Path) -> int:
    return _trail_path(workspace).stat().st_size


# --------------------------------------------------------------------------
# 读到手又丢掉的那一族
# --------------------------------------------------------------------------

def test_a_delete_record_past_the_line_cap_stays_in_the_list(tmp_path: Path) -> None:
    """E1：一条 34 KB 的轨迹，第一行的 delete 被 500 行上限丢掉了。"""
    workspace = _workspace(tmp_path, "busy")
    records = [_delete("gone.md")] + [_edit(f"f{i:05d}.md") for i in range(600)]
    size = _write(workspace, records)
    assert size < TAIL, size
    summary = _summary(workspace)
    assert summary["total_files"] == 1, summary["files"]
    assert [item["path"] for item in summary["files"]] == ["gone.md"], summary["files"]
    assert summary["files"][0]["status"] == "deleted", summary["files"]
    assert summary["audit_window_truncated"] is False, summary


def test_a_line_the_window_read_but_could_not_parse_is_counted(tmp_path: Path) -> None:
    """E2：读不出来的一行在被上限丢掉的那一段里——第五百三十二批那个数看不见它。"""
    workspace = _workspace(tmp_path, "garbage")
    records = [b"not json at all\n"] * 100 + [_edit(f"f{i:05d}.md") for i in range(560)]
    size = _write(workspace, records)
    assert size < TAIL, size
    summary = _summary(workspace)
    assert summary["audit_unreadable_lines"] == 100, summary


def test_the_bytes_outside_the_tail_are_reported(tmp_path: Path) -> None:
    """E3：窗外 64,937 字节——现在有一个数说得出它。"""
    workspace = _workspace(tmp_path, "far")
    filler = _edit("x" * 90 + ".md", "y" * 120)
    count = TAIL // len(filler) + 200
    size = _write(workspace, [_delete("gone.md")] + [filler] * count)
    summary = _summary(workspace)
    assert size > TAIL, size
    assert summary["audit_bytes_unread"] == size - TAIL, summary
    assert summary["audit_window_truncated"] is True, summary


def test_the_detail_page_carries_the_same_number(tmp_path: Path) -> None:
    """详情页与汇总说同一个数——两处各数一遍就会各说各的。"""
    workspace = _workspace(tmp_path, "both")
    filler = _edit("x" * 90 + ".md", "y" * 120)
    count = TAIL // len(filler) + 200
    size = _write(workspace, [_delete("gone.md")] + [filler] * count)
    summary = _summary(workspace)
    diff = _diff(workspace, "gone.md")
    assert diff["audit_bytes_unread"] == summary["audit_bytes_unread"] == size - TAIL, (
        diff["audit_bytes_unread"],
        summary["audit_bytes_unread"],
    )
    assert diff["audit_window_truncated"] is summary["audit_window_truncated"] is True, diff


def test_a_window_that_fits_lists_its_change(tmp_path: Path) -> None:
    """对照（落地前也绿）：窗内什么都没漏，那条改动就在清单里。"""
    workspace = _workspace(tmp_path, "fits")
    _write(workspace, [_edit("keep.md")])
    summary = _summary(workspace)
    assert summary["audit_window_truncated"] is False, summary
    assert [item["path"] for item in summary["files"]] == ["keep.md"], summary["files"]


def test_a_window_that_fits_reports_zero_unread_bytes(tmp_path: Path) -> None:
    """同一个现场：0 个字节没读，说的是实话。"""
    workspace = _workspace(tmp_path, "fits-zero")
    _write(workspace, [_edit("keep.md")])
    summary = _summary(workspace)
    assert summary["audit_bytes_unread"] == 0, summary


# --------------------------------------------------------------------------
# 字节切点上的两种第一行
# --------------------------------------------------------------------------

def _filler() -> bytes:
    blob = _edit("pad.md", "0" * 18)
    assert len(blob) == 64, len(blob)
    return blob


def test_a_whole_record_at_the_byte_boundary_is_read(tmp_path: Path) -> None:
    """E4：切点正好落在一条完整 delete 记录的第一个字节上——它不是残片。"""
    workspace = _workspace(tmp_path, "boundary")
    filler = _filler()
    width = 0
    while True:
        name = "gone" + "x" * width + ".md"
        blob = _delete(name)
        if len(blob) % 64 == 0:
            break
        width += 1
    after = (TAIL - len(blob)) // 64
    assert len(blob) + after * 64 == TAIL, (len(blob), after)
    trail = filler * 1000 + blob + filler * after
    cut = 1000 * 64
    size = _write(workspace, [trail])
    assert size - TAIL == cut, (size, cut)
    assert (trail[cut:]).startswith(b'{"action":"delete"'), trail[cut : cut + 32]
    summary = _summary(workspace)
    assert [item["path"] for item in summary["files"]] == [name], summary["files"]
    assert summary["files"][0]["status"] == "deleted", summary["files"]


def test_a_fragment_at_the_byte_boundary_is_still_a_fragment(tmp_path: Path) -> None:
    """E9：切点落在记录中间——残片丢掉，且不算「读不出来的一行」。"""
    workspace = _workspace(tmp_path, "fragment")
    filler = _filler()
    name = "c"
    blob = _delete(name, "dd")
    assert len(blob) == 128, len(blob)
    after = (TAIL - len(blob) // 2) // 64
    trail = filler * 1000 + blob + filler * after
    want = 1000 * 64 + len(blob) // 2
    size = _write(workspace, [trail])
    assert size - TAIL == want, (size, want)
    assert not trail[want:].startswith(b'{"action"'), trail[want : want + 24]
    summary = _summary(workspace)
    assert name not in [item["path"] for item in summary["files"]], summary["files"]
    assert summary["audit_unreadable_lines"] == 0, summary
    assert summary["audit_bytes_unread"] == size - TAIL, summary


# --------------------------------------------------------------------------
# 读不出来与没有可读的：两个答案
# --------------------------------------------------------------------------

def test_a_trail_that_is_not_a_file_answers_unknown_not_zero(tmp_path: Path) -> None:
    """E7：读不出来时「没读的字节」是不知道，不是 0。"""
    workspace = _workspace(tmp_path, "broken")
    _trail_path(workspace).mkdir(parents=True)
    summary = _summary(workspace)
    assert summary["audit_read_error"], summary
    assert summary["audit_bytes_unread"] is None, summary
    diff = _diff(workspace, "keep.md")
    assert diff["audit_bytes_unread"] is None, diff
    assert diff["audit_read_error"], diff


def test_a_missing_trail_answers_zero(tmp_path: Path) -> None:
    """E8：根本没有轨迹——0 个字节没读。"""
    workspace = _workspace(tmp_path, "missing")
    summary = _summary(workspace)
    assert summary["audit_read_error"] is None, summary
    assert summary["audit_bytes_unread"] == 0, summary


# --------------------------------------------------------------------------
# 上一位的那个词还站着；行上限只剩一个家
# --------------------------------------------------------------------------

def test_the_preimage_word_still_stands_on_the_byte_cut(tmp_path: Path) -> None:
    """第五百四十八批的词跟着字节走：backup 行在窗外，预像答 not-in-window。"""
    workspace = _workspace(tmp_path, "word", {"notes.md": "hello\n"})
    editor = _editor(workspace)
    editor.delete("notes.md")
    filler = _edit("x" * 90 + ".md", "y" * 120)
    count = TAIL // len(filler) + 200
    _write(workspace, [filler] * count + [_delete("notes.md")])
    diff = _diff(workspace, "notes.md")
    assert diff["deletion_preimage"] == "not-in-window", diff


def test_the_byte_cut_still_carries_its_number_beside_the_word(tmp_path: Path) -> None:
    """同一个现场，数也在：词与数说的是同一道切法。"""
    workspace = _workspace(tmp_path, "word-number", {"notes.md": "hello\n"})
    editor = _editor(workspace)
    editor.delete("notes.md")
    filler = _edit("x" * 90 + ".md", "y" * 120)
    count = TAIL // len(filler) + 200
    _write(workspace, [filler] * count + [_delete("notes.md")])
    diff = _diff(workspace, "notes.md")
    assert diff["audit_bytes_unread"] == _size(workspace) - TAIL, diff


def test_the_line_cap_has_no_home_left(tmp_path: Path) -> None:
    """500 行上限整个撤掉；窗只剩字节这一道界。"""
    source = inspect.getsource(changes_module)
    assert "_AUDIT_WINDOW_LINES" not in source, "行上限还在"
    assert "for line in lines:" in source
    assert "_AUDIT_TAIL_BYTES = 256_000" in source
