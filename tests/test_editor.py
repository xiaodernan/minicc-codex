"""M8-T783: minicc/tools/editor.py - 文件编辑核心的综合测试。

覆盖：
- resolve_in_workspace：路径限制、绝对路径拒绝、.. 逃逸拒绝
- Editor.read_file / read_file_meta：行号读取、边界、缺失文件
- Editor.write_file：原子写入、expected_digest 校验、digest 不匹配拒绝
- Editor.apply_edit：精确匹配、空 old 拒绝、多处匹配拒绝、未命中拒绝、
  空白归一化回退（W113）、预期 digest 校验
- Editor.delete / move：删除、移动、目标已存在拒绝
- Editor.backup：备份创建、超出上限裁剪
- 审计轨迹：每条操作都产生审计行
"""

from __future__ import annotations

import hashlib
import pytest
from pathlib import Path

from minicc.tools.editor import (
    Editor,
    EditError,
    StaleContextError,
    FileRead,
    resolve_in_workspace,
    path_escaped_workspace,
    missing_file_message,
    sha256_digest,
    _normalize_ws_line,
    _relaxed_ws_anchor,
    _PORCELAIN_LINE_RE,
    _UNMERGED_PAIRS,
    classify_workspace_changes,
    MAX_READ_LINES,
    MAX_BACKUP_FILES,
)


def _write(path: Path, content: str) -> None:
    """Write text content as bytes to avoid Windows CRLF translation."""
    path.write_bytes(content.encode("utf-8"))


def _read(path: Path) -> str:
    """Read file content as text."""
    return path.read_bytes().decode("utf-8")


# ============================================================================
# resolve_in_workspace
# ============================================================================

def test_resolve_in_workspace_relative_path(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    target = workspace / "sub" / "file.txt"
    target.parent.mkdir()
    _write(target, "data")

    result = resolve_in_workspace(workspace, "sub/file.txt")
    assert result == target


def test_resolve_in_workspace_absolute_path_rejected(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()

    # On Windows, "/etc/passwd" is treated as relative (no drive letter)
    # so it goes through the "超出 workspace 根" path.
    with pytest.raises(EditError, match="超出 workspace 根"):
        resolve_in_workspace(workspace, "/etc/passwd")


def test_resolve_in_workspace_dotdot_escape_rejected(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    outside = tmp_path / "secret.txt"
    _write(outside, "leak")

    with pytest.raises(EditError, match="超出 workspace 根"):
        resolve_in_workspace(workspace, "../secret.txt")


def test_resolve_in_workspace_dotdot_internal_ok(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    sub = workspace / "sub"
    sub.mkdir()
    target = sub / "file.txt"
    _write(target, "data")

    result = resolve_in_workspace(workspace, "sub/../sub/file.txt")
    assert result == target


# ============================================================================
# Editor: read_file / read_file_meta
# ============================================================================

def test_read_file_basic(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    target = workspace / "hello.txt"
    _write(target, "line1\nline2\nline3\n")

    editor = Editor(workspace)
    lines = editor.read_file("hello.txt", offset=1, limit=2)
    assert lines == [(1, "line1"), (2, "line2")]


def test_read_file_meta(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    target = workspace / "data.txt"
    content = b"alpha\nbeta\ngamma\n"
    target.write_bytes(content)

    editor = Editor(workspace)
    result = editor.read_file_meta("data.txt", offset=1, limit=2)

    assert isinstance(result, FileRead)
    assert result.path == "data.txt"
    assert result.digest == hashlib.sha256(content).hexdigest()
    assert result.size == len(content)
    assert result.lines == [(1, "alpha"), (2, "beta")]


def test_read_file_offset_beyond_file(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    target = workspace / "short.txt"
    _write(target, "only one line\n")

    editor = Editor(workspace)
    lines = editor.read_file("short.txt", offset=5, limit=10)
    assert lines == []


def test_read_file_offset_zero_rejected(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    target = workspace / "x.txt"
    _write(target, "x\n")

    editor = Editor(workspace)
    with pytest.raises(EditError, match="offset"):
        editor.read_file("x.txt", offset=0, limit=10)


def test_read_file_limit_exceeds_cap(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    target = workspace / "x.txt"
    _write(target, "x\n")

    editor = Editor(workspace)
    with pytest.raises(EditError, match="limit"):
        editor.read_file("x.txt", offset=1, limit=MAX_READ_LINES + 1)


def test_read_file_missing(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    editor = Editor(workspace)

    with pytest.raises(EditError, match="不存在"):
        editor.read_file("nonexistent.txt")


# ============================================================================
# Editor: write_file
# ============================================================================

def test_write_file_new_file(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    editor = Editor(workspace)

    editor.write_file("new.txt", "hello world\n")

    target = workspace / "new.txt"
    assert target.is_file()
    assert _read(target) == "hello world\n"


def test_write_file_existing_overwrites(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    target = workspace / "existing.txt"
    _write(target, "old content\n")

    editor = Editor(workspace)
    editor.write_file("existing.txt", "new content\n")

    assert _read(target) == "new content\n"


def test_write_file_with_expected_digest_match(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    target = workspace / "digest.txt"
    original = b"original content\n"
    target.write_bytes(original)

    editor = Editor(workspace)
    digest = hashlib.sha256(original).hexdigest()
    editor.write_file("digest.txt", "updated content\n", expected_digest=digest)

    assert _read(target) == "updated content\n"


def test_write_file_with_expected_digest_mismatch(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    target = workspace / "digest.txt"
    _write(target, "original\n")

    editor = Editor(workspace)
    with pytest.raises(StaleContextError, match="STALE_CONTEXT"):
        editor.write_file("digest.txt", "new content\n", expected_digest="deadbeef")


def test_write_file_expected_digest_empty_for_new_file(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    editor = Editor(workspace)

    editor.write_file("brand_new.txt", "brand new\n", expected_digest="")
    assert _read(workspace / "brand_new.txt") == "brand new\n"


def test_write_file_expected_digest_nonempty_for_new_file_rejected(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    editor = Editor(workspace)

    with pytest.raises(StaleContextError):
        editor.write_file("brand_new2.txt", "brand new\n", expected_digest="abc123")


# ============================================================================
# Editor: apply_edit
# ============================================================================

def test_apply_edit_exact_match(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    target = workspace / "edit.txt"
    _write(target, "line one\nline two\nline three\n")

    editor = Editor(workspace)
    editor.apply_edit("edit.txt", "line two\n", "line TWO\n")

    result = _read(target)
    assert result == "line one\nline TWO\nline three\n"


def test_apply_edit_old_empty_rejected(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    target = workspace / "x.txt"
    _write(target, "content\n")

    editor = Editor(workspace)
    with pytest.raises(EditError, match="old 不能为空字符串"):
        editor.apply_edit("x.txt", "", "replacement\n")


def test_apply_edit_no_match_rejected(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    target = workspace / "edit.txt"
    _write(target, "hello world\n")

    editor = Editor(workspace)
    with pytest.raises(EditError, match="未命中"):
        editor.apply_edit("edit.txt", "goodbye\n", "hello\n")


def test_apply_edit_multiple_match_rejected(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    target = workspace / "edit.txt"
    _write(target, "repeat\nrepeat\nrepeat\n")

    editor = Editor(workspace)
    with pytest.raises(EditError, match="不唯一"):
        editor.apply_edit("edit.txt", "repeat\n", "REPEAT\n")


def test_apply_edit_whitespace_normalized_match(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    target = workspace / "edit.txt"
    _write(target, "line one\twith\ttabs\nline two\n")

    editor = Editor(workspace)
    editor.apply_edit("edit.txt", "line one with tabs\n", "line ONE normalized\n")

    result = _read(target)
    assert "line ONE normalized" in result
    assert "line two\n" in result


def test_apply_edit_expected_digest_match(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    target = workspace / "edit.txt"
    original = b"original content\n"
    target.write_bytes(original)

    editor = Editor(workspace)
    digest = hashlib.sha256(original).hexdigest()
    editor.apply_edit("edit.txt", "original content\n", "updated content\n", expected_digest=digest)

    assert _read(target) == "updated content\n"


def test_apply_edit_expected_digest_mismatch_rejected(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    target = workspace / "edit.txt"
    _write(target, "original\n")

    editor = Editor(workspace)
    with pytest.raises(StaleContextError):
        editor.apply_edit("edit.txt", "original\n", "new\n", expected_digest="deadbeef")


# ============================================================================
# Editor: delete / move
# ============================================================================

def test_delete_file(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    target = workspace / "delete_me.txt"
    _write(target, "bye\n")

    editor = Editor(workspace)
    editor.delete("delete_me.txt")

    assert not target.exists()


def test_delete_missing_file_rejected(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    editor = Editor(workspace)

    with pytest.raises(EditError, match="不存在"):
        editor.delete("nonexistent.txt")


def test_move_file(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    src = workspace / "src.txt"
    dst = workspace / "sub" / "dst.txt"
    _write(src, "moving\n")

    editor = Editor(workspace)
    editor.move("src.txt", "sub/dst.txt")

    assert not src.exists()
    assert dst.is_file()
    assert _read(dst) == "moving\n"


def test_move_destination_exists_rejected(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    src = workspace / "src.txt"
    dst = workspace / "dst.txt"
    _write(src, "src\n")
    _write(dst, "dst\n")

    editor = Editor(workspace)
    with pytest.raises(EditError, match="目标已存在"):
        editor.move("src.txt", "dst.txt")


# ============================================================================
# Editor: backup
# ============================================================================

def test_backup_creates_copy(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    target = workspace / "important.txt"
    _write(target, "important data\n")

    editor = Editor(workspace)
    editor._backup(target)

    backup_dir = workspace / ".minicc" / "backup"
    backups = list(backup_dir.iterdir())
    assert len(backups) == 1
    backup_content = _read(backups[0])
    assert backup_content == "important data\n"


def test_backup_prune_respects_cap(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    target = workspace / "changing.txt"
    editor = Editor(workspace)

    for i in range(MAX_BACKUP_FILES + 5):
        _write(target, f"version {i}\n")
        editor._backup(target)

    backup_dir = workspace / ".minicc" / "backup"
    backups = list(backup_dir.iterdir())
    assert len(backups) == MAX_BACKUP_FILES


# ============================================================================
# classify_workspace_changes
# ============================================================================

def test_classify_workspace_changes_agent_change(tmp_path: Path) -> None:
    status_output = " M agent_modified.py\n"
    agent_paths = {"agent_modified.py"}

    result = classify_workspace_changes(status_output, agent_paths=agent_paths)
    assert result["agent_changes"] == ["agent_modified.py"]
    assert result["user_changes"] == []
    assert result["unknown"] == []


def test_classify_workspace_changes_user_change(tmp_path: Path) -> None:
    status_output = " M user_modified.py\n"
    agent_paths = set()

    result = classify_workspace_changes(status_output, agent_paths=agent_paths)
    assert result["user_changes"] == ["user_modified.py"]
    assert result["agent_changes"] == []
    assert result["unknown"] == []


def test_classify_workspace_changes_ignored(tmp_path: Path) -> None:
    status_output = "!! build/output.o\n"

    result = classify_workspace_changes(status_output, agent_paths=set())
    assert result["agent_changes"] == []
    assert result["user_changes"] == []
    assert result["unknown"] == []


def test_classify_workspace_changes_unknown(tmp_path: Path) -> None:
    status_output = "?? untracked_file.txt\n"

    result = classify_workspace_changes(status_output, agent_paths=set())
    assert result["unknown"] == ["untracked_file.txt"]


# ============================================================================
# _normalize_ws_line / _relaxed_ws_anchor
# ============================================================================

def test_normalize_ws_line_tabs_to_spaces() -> None:
    assert _normalize_ws_line("line\twith\ttabs") == "line with tabs"


def test_normalize_ws_line_trailing_spaces_stripped() -> None:
    assert _normalize_ws_line("line   ") == "line"


def test_relaxed_ws_anchor_match(tmp_path: Path) -> None:
    text = "line one\twith\ttabs\nline two\n"
    old = "line one with tabs\n"
    result = _relaxed_ws_anchor(text, old)
    assert result is not None
    start, end, occurrences = result
    assert occurrences == 1


def test_relaxed_ws_anchor_multiple_match_rejected(tmp_path: Path) -> None:
    text = "repeat\nrepeat\nrepeat\n"
    old = "repeat\n"
    result = _relaxed_ws_anchor(text, old)
    assert result is not None
    start, end, occurrences = result
    assert occurrences == 3


def test_relaxed_ws_anchor_no_match_returns_none(tmp_path: Path) -> None:
    text = "completely different\ncontent\n"
    old = "not present\n"
    result = _relaxed_ws_anchor(text, old)
    assert result is None


# ============================================================================
# Editor: edit end-to-end with audit
# ============================================================================

def test_edit_audit_trail(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    target = workspace / "audit_test.txt"
    _write(target, "original\n")

    editor = Editor(workspace)
    editor.apply_edit("audit_test.txt", "original\n", "modified\n")

    assert len(editor.audit) == 2
    assert editor.audit[0].action == "backup"
    assert editor.audit[1].action == "edit"
    assert editor.audit[1].path == "audit_test.txt"


# ============================================================================
# Editor: write then read round-trip
# ============================================================================

def test_write_then_read_round_trip(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    editor = Editor(workspace)

    editor.write_file("roundtrip.txt", "hello world\n")
    result = editor.read_file("roundtrip.txt")

    assert result == [(1, "hello world")]


# ============================================================================
# Editor: delete then read raises
# ============================================================================

def test_delete_then_read_rejected(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    target = workspace / "to_delete.txt"
    _write(target, "gone\n")

    editor = Editor(workspace)
    editor.delete("to_delete.txt")

    with pytest.raises(EditError, match="不存在"):
        editor.read_file("to_delete.txt")
