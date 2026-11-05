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


def _split_trail() -> tuple[list[bytes], int]:
    """切点落在一条 128 字节 delete 记录的正中间。"""
    half = _delete("c", "dd")
    assert len(half) == 128, len(half)
    after = (TAIL - len(half) // 2) // 64
    return [_filler() * 1000, half, _filler() * after], 1000 * 64 + len(half) // 2


def _boundary_trail() -> tuple[list[bytes], int]:
    """切点正好在整条 delete 记录的第一个字节。"""
    whole = _boundary_delete()
    after = (TAIL - len(whole)) // 64
    return [_filler() * 1000, whole, _filler() * after], 1000 * 64


def test_a_record_cut_by_the_window_is_counted(tmp_path: Path) -> None:
    blobs, cut = _split_trail()
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
    blobs, _cut = _split_trail()
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
