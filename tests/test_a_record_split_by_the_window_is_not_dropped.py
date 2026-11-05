"""M8-T573（第五百五十五批）：窗口第一行是整条还是半条，不能靠猜。

第五百四十九批（T567）在切点落在记录边界时保住了那条记录，却在切点落在记录
中间时把碎片无声丢掉：它不进清单、不进 `audit_unreadable_lines`，payload 里也
没有一个数说「有一条记录被切开了」。探针 `scratch/probe573.py` 在 T572 定稿上
量到：

  P1  切点在整条 delete 记录的第一个字节 -> 清单有它、unread=64,000、没有 split 键
  P2  切点在同一条记录的中间             -> 清单没有它、unread=64,064、没有 split 键
  P3  切点在一条整行但不是对象的 JSON 上 -> 被当残片丢掉，unreadable=0

修法：窗口第一行是不是整条，由窗口前一个字节决定（换行=边界），不再由「这行
能不能解析成对象」猜。整行但不是记录的行照常进 `audit_unreadable_lines`；被切开
的记录尾巴仍丢掉（它的开头在窗外），但 `audit_records_split` 说有一条没读全。
切点正好落在行终止符上时，窗口第一行是空串——那是边界，不是残片（F8/F9）。

第五百五十六批（T574）起，头在窗外 64 KB 以内的记录会被读回整条；本门的两格
（中间切点、详情页）因此改成一条头在 66,000 字节外的 delete——这种记录仍是
T573 说的「有一条没读全」，尾巴丢掉、split=1。读回整条的那一族在 T574 的门里。
"""

from __future__ import annotations

import json
from pathlib import Path

from minicc import changes as changes_module
from minicc.changes import ChangeInspector

TAIL = changes_module._AUDIT_TAIL_BYTES
DIGEST = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def _workspace(root: Path, name: str) -> Path:
    workspace = root / name
    workspace.mkdir(parents=True)
    (workspace / "keep.md").write_bytes(b"stay\n")
    (workspace / "pad.md").write_bytes(b"pad\n")
    return workspace


def _record(action: str, path: str, detail: str = "", **extra) -> bytes:
    item = {"action": action, "path": path, "detail": detail, **extra}
    return json.dumps(item, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"


def _delete(path: str, detail: str = "") -> bytes:
    return _record("delete", path, detail, before_digest=DIGEST)


def _edit(path: str, detail: str = "written") -> bytes:
    return _record("edit", path, detail)


def _write(workspace: Path, blobs: list[bytes]) -> int:
    target = workspace / ".minicc" / "audit.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    data = b"".join(blobs)
    target.write_bytes(data)
    return len(data)


def _summary(workspace: Path) -> dict:
    return ChangeInspector(workspace).summary()


def _diff(workspace: Path, path: str) -> dict:
    return ChangeInspector(workspace).diff(path)


def _filler() -> bytes:
    blob = _edit("pad.md", "0" * 18)
    assert len(blob) == 64, len(blob)
    return blob


def _boundary_delete() -> bytes:
    width = 0
    while True:
        blob = _delete("gone" + "x" * width + ".md")
        if len(blob) % 64 == 0:
            return blob
        width += 1


def _pad_to(rem: int) -> bytes:
    width = 0
    while True:
        blob = _edit("pad.md", "z" * width)
        if len(blob) % 64 == rem:
            return blob
        width += 1
        assert width < 400, width


def _unrecoverable_trail() -> tuple[list[bytes], int]:
    """切点落在一条头的距离超过回扫上限的 delete 记录里（65,600 字节处）。"""
    record = _delete("c", "0" * 70_000)
    cut_in = 65_600
    assert len(record) > cut_in, (len(record), cut_in)
    prefix = _filler() * 1000
    cut = len(prefix) + cut_in
    suffix = cut + TAIL - len(prefix) - len(record)
    assert suffix >= 0, suffix
    pad = _pad_to(suffix % 64)
    count = (suffix - len(pad)) // 64
    return [prefix, record, _filler() * count, pad], cut


def _boundary_trail() -> tuple[list[bytes], int]:
    """切点正好在整条 delete 记录的第一个字节。"""
    whole = _boundary_delete()
    after = (TAIL - len(whole)) // 64
    return [_filler() * 1000, whole, _filler() * after], 1000 * 64


def _terminator_trail(crlf: bool) -> tuple[list[bytes], int]:
    """切点正好落在记录末尾的行终止符上：LF 的那个 LF，或 CRLF 的那个 CR。"""
    unit = 65 if crlf else 64
    term = 2 if crlf else 1
    fill = _filler()
    if crlf:
        fill = fill.replace(b"\n", b"\r\n")
    rest = TAIL - term
    width = 0
    while True:
        blob = _delete("gone" + "x" * width + ".md")
        if crlf:
            blob = blob.replace(b"\n", b"\r\n")
        if len(blob) % unit == rest % unit:
            break
        width += 1
    after = (rest - len(blob)) // unit
    return [fill * 1000, blob, fill * after], 1000 * unit - term


def test_a_record_cut_by_the_window_is_counted(tmp_path: Path) -> None:
    """T573 的中间切点：头在 65,600 字节外——读不回来，split=1、清单没有它。"""
    blobs, cut = _unrecoverable_trail()
    workspace = _workspace(tmp_path, "split")
    size = _write(workspace, blobs)
    summary = _summary(workspace)
    assert size - TAIL == cut, (size, cut)
    assert summary.get("audit_records_split", 0) == 1, summary
    assert "c" not in [item["path"] for item in summary["files"]], summary["files"]
    assert summary["audit_unreadable_lines"] == 0, summary
    assert summary["audit_bytes_unread"] == size - TAIL, summary
    assert summary["audit_window_truncated"] is True, summary


def test_a_whole_record_at_the_window_start_is_not_called_split(tmp_path: Path) -> None:
    blobs, cut = _boundary_trail()
    workspace = _workspace(tmp_path, "boundary")
    size = _write(workspace, blobs)
    summary = _summary(workspace)
    assert size - TAIL == cut, (size, cut)
    assert summary.get("audit_records_split", 0) == 0, summary
    paths = [item["path"] for item in summary["files"]]
    assert any(path.startswith("gone") for path in paths), summary["files"]
    assert summary["audit_unreadable_lines"] == 0, summary
    assert summary["audit_bytes_unread"] == size - TAIL, summary


def test_a_window_that_begins_on_a_terminator_is_not_called_split(tmp_path: Path) -> None:
    """F8/F9：切点落在行终止符上——第一行是空串，但没有记录被切开。"""
    for crlf in (False, True):
        blobs, cut = _terminator_trail(crlf)
        workspace = _workspace(tmp_path, f"terminator-{crlf}")
        size = _write(workspace, blobs)
        summary = _summary(workspace)
        assert size - TAIL == cut, (crlf, size, cut)
        assert summary.get("audit_records_split", 0) == 0, (crlf, summary)
        assert summary["audit_unreadable_lines"] == 0, (crlf, summary)
        assert any(
            item["path"].startswith("gone") for item in summary["files"]
        ), (crlf, summary["files"])
        assert summary["audit_bytes_unread"] == size - TAIL, (crlf, summary)


def test_a_whole_line_that_is_not_a_record_is_counted_as_unreadable(tmp_path: Path) -> None:
    nonobject = b'"' + b"x" * 61 + b'"\n'
    assert len(nonobject) == 64
    after = (TAIL - len(nonobject)) // 64
    workspace = _workspace(tmp_path, "nonobject")
    size = _write(workspace, [_filler() * 1000, nonobject, _filler() * after])
    summary = _summary(workspace)
    assert size - TAIL == 1000 * 64, size
    assert summary.get("audit_records_split", 0) == 0, summary
    assert summary["audit_unreadable_lines"] == 1, summary
    assert [item["path"] for item in summary["files"]] == ["pad.md"], summary["files"]


def test_the_detail_page_carries_the_split_count(tmp_path: Path) -> None:
    blobs, _cut = _unrecoverable_trail()
    workspace = _workspace(tmp_path, "detail")
    size = _write(workspace, blobs)
    diff = _diff(workspace, "c")
    assert diff.get("audit_records_split", 0) == 1, diff
    assert diff["audit_window_truncated"] is True, diff
    assert diff["audit_bytes_unread"] == size - TAIL, diff
    assert diff["audit_unreadable_lines"] == 0, diff
    assert diff["status"] == "clean", diff
    assert (diff["additions"], diff["deletions"]) == (0, 0), diff


def test_a_trail_read_whole_has_nothing_split(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, "whole")
    _write(workspace, [_edit("pad.md")])
    summary = _summary(workspace)
    assert summary.get("audit_records_split", 0) == 0, summary
    assert summary["audit_window_truncated"] is False, summary
    assert summary["audit_bytes_unread"] == 0, summary
    assert [item["path"] for item in summary["files"]] == ["pad.md"], summary["files"]


def test_a_trail_that_cannot_be_read_answers_unknown(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, "broken")
    (workspace / ".minicc" / "audit.jsonl").mkdir(parents=True)
    summary = _summary(workspace)
    assert summary.get("audit_records_split") is None, summary
    assert summary["audit_bytes_unread"] is None, summary
    assert summary["audit_read_error"], summary
