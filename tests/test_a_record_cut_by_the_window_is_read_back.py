"""M8-T574（第五百五十六批）：被切开的记录，头就在窗外几十到几百字节处。

第五百五十五批（T573）让 `audit_records_split` 说出「有一条没读全」，但那条记录
本身仍被丢掉：探针 `scratch/probe574.py` 在 T573 定稿上量到——

  H1  切在一条 delete 记录中间          -> back=64、split=1、清单没有它、详情页 clean
  H3  切在 70 KB 记录里 10,000 字节处   -> back=10,000、split=1
  H4  切在 100 KB 记录里 70,000 字节处  -> back=70,000（越过 64 KB 回扫上限）
  H5  CRLF 轨迹、切在 delete 记录中间   -> back=64、split=1
  H6  本仓库自己的轨迹                  -> 窗口起点离上一个换行 210 字节

修法：窗口第一行是尾巴时，向回读最多 `_AUDIT_RECOVERY_BYTES`（64 KB），找到上一个
行终止符，把那条记录整个读进来；`start` 前移到记录开头，所以 `audit_bytes_unread`
跟着变小、`audit_records_split` 归 0。头比上限还远才保留 T573 的答案（尾巴丢掉、
split=1）；记录从文件第一个字节开始时也能读回（无终止符但也没越过上限）。
"""

from __future__ import annotations

import json
from pathlib import Path

from minicc import changes as changes_module
from minicc.changes import ChangeInspector

TAIL = changes_module._AUDIT_TAIL_BYTES
# 落地前常量还不存在；用默认值让红是断言红，不是收集错误。
CAP = getattr(changes_module, "_AUDIT_RECOVERY_BYTES", 65_536)
DIGEST = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def _workspace(root: Path, name: str, files: dict[str, str] | None = None) -> Path:
    workspace = root / name
    workspace.mkdir(parents=True)
    (workspace / "keep.md").write_bytes(b"stay\n")
    (workspace / "pad.md").write_bytes(b"pad\n")
    for rel, body in (files or {}).items():
        target = workspace / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body.encode("utf-8"))
    return workspace


def _record(action: str, path: str, detail: str = "", **extra) -> bytes:
    item = {"action": action, "path": path, "detail": detail, **extra}
    return json.dumps(item, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"


def _delete(path: str, detail: str = "") -> bytes:
    return _record("delete", path, detail, before_digest=DIGEST)


def _edit(path: str, detail: str = "written") -> bytes:
    return _record("edit", path, detail)


def _with_eol(blob: bytes, crlf: bool) -> bytes:
    return blob.replace(b"\n", b"\r\n") if crlf else blob


def _filler(crlf: bool = False) -> bytes:
    blob = _with_eol(_edit("pad.md", "0" * 18), crlf)
    assert len(blob) == (65 if crlf else 64), len(blob)
    return blob


def _pad_to(rem: int, unit: int, crlf: bool) -> bytes:
    width = 0
    while True:
        blob = _with_eol(_edit("pad.md", "z" * width), crlf)
        if len(blob) % unit == rem:
            return blob
        width += 1
        assert width < 400, width


def _trail(record: bytes, cut_in_record: int, crlf: bool = False) -> tuple[list[bytes], int]:
    """把 ``record`` 放在切点里，返回 (块, 切点偏移)。"""
    unit = 65 if crlf else 64
    prefix = _filler(crlf) * 1000
    cut = len(prefix) + cut_in_record
    suffix = cut + TAIL - len(prefix) - len(record)
    assert suffix >= 0, suffix
    pad = _pad_to(suffix % unit, unit, crlf)
    count = (suffix - len(pad)) // unit
    assert len(pad) + count * unit == suffix, (len(pad), count, suffix)
    return [prefix, record, _filler(crlf) * count, pad], cut


def _unrecoverable_delete() -> tuple[list[bytes], int, bytes]:
    """头越过回扫上限的记录：切在它里面 65,600 字节处。"""
    record = _delete("c", "0" * 70_000)
    cut_in = 65_600
    assert cut_in > CAP, (cut_in, CAP)
    assert len(record) > cut_in, (len(record), cut_in)
    blobs, cut = _trail(record, cut_in)
    return blobs, cut, record


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


def test_a_record_cut_within_reach_is_read_back(tmp_path: Path) -> None:
    """H1 的答案：那条 delete 现在整条读回来——清单有它，split=0，没读的字节少了 64。"""
    blobs, cut = _trail(_delete("c", "dd"), 64)
    workspace = _workspace(tmp_path, "near")
    size = _write(workspace, blobs)
    summary = _summary(workspace)
    assert size - TAIL == cut, (size, cut)
    assert summary.get("audit_records_split", 0) == 0, summary
    rows = [item for item in summary["files"] if item["path"] == "c"]
    assert len(rows) == 1, summary["files"]
    assert rows[0]["status"] == "deleted", rows[0]
    assert summary["audit_bytes_unread"] == size - TAIL - 64, summary
    assert summary["audit_window_truncated"] is True, summary
    assert summary["audit_unreadable_lines"] == 0, summary


def test_the_detail_page_answers_the_record_it_could_not_see_before(tmp_path: Path) -> None:
    """同一个现场：详情页也从「clean、0/0」变成 deleted，数与前移后的窗一致。"""
    blobs, cut = _trail(_delete("c", "dd"), 64)
    workspace = _workspace(tmp_path, "near-detail")
    size = _write(workspace, blobs)
    diff = _diff(workspace, "c")
    assert diff["status"] == "deleted", diff
    assert diff.get("audit_records_split", 0) == 0, diff
    assert diff["audit_bytes_unread"] == size - TAIL - 64, diff
    assert diff["audit_unreadable_lines"] == 0, diff


def test_a_record_whose_head_is_beyond_reach_is_still_counted(tmp_path: Path) -> None:
    """H4：头在 64 KB 之外——不读回整条，T573 的数与「没有它」都还在。"""
    blobs, cut, _record = _unrecoverable_delete()
    workspace = _workspace(tmp_path, "far")
    size = _write(workspace, blobs)
    summary = _summary(workspace)
    assert size - TAIL == cut, (size, cut)
    assert summary.get("audit_records_split", 0) == 1, summary
    assert "c" not in [item["path"] for item in summary["files"]], summary["files"]
    assert summary["audit_bytes_unread"] == size - TAIL, summary
    assert summary["audit_unreadable_lines"] == 0, summary


def test_the_detail_page_keeps_the_unrecoverable_split(tmp_path: Path) -> None:
    """同一个远现场：详情页不把「没读到」画成「没有改动」之外的东西。"""
    blobs, _cut, _record = _unrecoverable_delete()
    workspace = _workspace(tmp_path, "far-detail")
    size = _write(workspace, blobs)
    diff = _diff(workspace, "c")
    assert diff.get("audit_records_split", 0) == 1, diff
    assert diff["audit_bytes_unread"] == size - TAIL, diff
    assert diff["status"] == "clean", diff
    assert (diff["additions"], diff["deletions"]) == (0, 0), diff


def test_a_boundary_cut_still_reads_the_record_whole(tmp_path: Path) -> None:
    """对照：切在记录的第一个字节——回扫什么都不做，答案与 T573 一致。"""
    width = 0
    while True:
        whole = _delete("gone" + "x" * width + ".md")
        if len(whole) % 64 == 0:
            break
        width += 1
    after = (TAIL - len(whole)) // 64
    workspace = _workspace(tmp_path, "boundary")
    size = _write(workspace, [_filler() * 1000, whole, _filler() * after])
    summary = _summary(workspace)
    assert summary.get("audit_records_split", 0) == 0, summary
    names = [item["path"] for item in summary["files"]]
    assert any(name.startswith("gone") for name in names), summary["files"]
    assert summary["audit_bytes_unread"] == size - TAIL, summary


def test_a_crlf_record_cut_within_reach_is_read_back(tmp_path: Path) -> None:
    """H5：CRLF 轨迹的回扫落在 CRLF 之后，记录同样整条读回来。"""
    blobs, cut = _trail(_with_eol(_delete("c", "dd"), True), 64, crlf=True)
    workspace = _workspace(tmp_path, "crlf")
    size = _write(workspace, blobs)
    summary = _summary(workspace)
    assert size - TAIL == cut, (size, cut)
    assert summary.get("audit_records_split", 0) == 0, summary
    rows = [item for item in summary["files"] if item["path"] == "c"]
    assert len(rows) == 1, summary["files"]
    assert rows[0]["status"] == "deleted", rows[0]
    assert summary["audit_bytes_unread"] == size - TAIL - 64, summary
    assert summary["audit_unreadable_lines"] == 0, summary


def test_a_record_that_starts_at_the_files_first_byte_is_read_back(tmp_path: Path) -> None:
    """窗口前整段没有终止符、但文件从头读：记录从第一个字节开始，照样读回。"""
    record = _edit("only.md", "0" * 300_000)
    workspace = _workspace(tmp_path, "start", {"only.md": "line\n"})
    size = _write(workspace, [record])
    start = size - TAIL
    assert 0 < start <= CAP, (size, start, CAP)
    summary = _summary(workspace)
    assert summary.get("audit_records_split", 0) == 0, summary
    assert summary["audit_bytes_unread"] == 0, summary
    assert summary["audit_window_truncated"] is False, summary
    assert [item["path"] for item in summary["files"]] == ["only.md"], summary["files"]


def test_a_trail_read_whole_and_a_failed_read_are_unchanged(tmp_path: Path) -> None:
    """对照：整份读完与读不出来，两条老答案都不动。"""
    whole = _workspace(tmp_path, "whole")
    _write(whole, [_edit("pad.md")])
    summary = _summary(whole)
    assert summary.get("audit_records_split", 0) == 0, summary
    assert summary["audit_bytes_unread"] == 0, summary

    broken = _workspace(tmp_path, "broken")
    (broken / ".minicc" / "audit.jsonl").mkdir(parents=True)
    summary = _summary(broken)
    assert summary.get("audit_records_split") is None, summary
    assert summary["audit_bytes_unread"] is None, summary
