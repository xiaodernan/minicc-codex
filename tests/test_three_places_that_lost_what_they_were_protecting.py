"""M8-T300 / T301 / T302 — 三处「保护自己的东西，却把保护对象弄丢了」

| 编号 | 位置 | 现象 |
| --- | --- | --- |
| M8-T300 | `minicc/changes.py` | 只被**读取**的文件被当成 "modified" 变更上报（patch 为空，状态写着 modified） |
| M8-T301 | `minicc/tools/editor.py` | 备份裁剪按**源文件 mtime** 排序 —— 源文件 mtime 旧，刚生成的备份立刻被自己触发的裁剪删掉，编辑前的原文丢失 |
| M8-T302 | `minicc/tools/memory.py` | 记忆文件**读不出来**时被当成"空文件"，写入时整体覆盖 —— 历史记忆静默全丢，且没有任何错误 |

This door pins all three.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from minicc.changes import ChangeInspector
from minicc.tools.editor import Editor
from minicc.tools.memory import MemoryEntry, MemoryTools


# --- M8-T300: a read is not a change ------------------------------------------


def test_a_read_file_is_not_reported_as_modified(tmp_path: Path) -> None:
    """The change panel must report changes, not reads."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "README.md").write_text("# demo\n", encoding="utf-8")

    editor = Editor(workspace, audit_path=workspace / ".minicc" / "audit.jsonl")
    editor.read_file("README.md")

    inspector = ChangeInspector(workspace)
    reported = {item["path"] for item in inspector.summary()["files"]}
    assert "README.md" not in reported, (
        "a file the agent only read was reported as a change"
    )


def test_a_written_file_is_still_reported(tmp_path: Path) -> None:
    """The control: the fallback still works for a real change."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "notes.md").write_text("# demo\n", encoding="utf-8")

    editor = Editor(workspace, audit_path=workspace / ".minicc" / "audit.jsonl")
    editor.write_file("notes.md", "# changed\n")

    inspector = ChangeInspector(workspace)
    reported = {item["path"] for item in inspector.summary()["files"]}
    assert "notes.md" in reported, "a written file was not reported as a change"


# --- M8-T301: a fresh backup must not be the first victim ---------------------


def test_a_fresh_backup_of_an_old_file_survives_the_pruning(tmp_path: Path) -> None:
    """``copy2`` preserves the source mtime, and the order is by mtime."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    old = workspace / "old.txt"
    old.write_text("original\n", encoding="utf-8")
    # A file whose mtime is older than every backup made afterwards.
    os.utime(old, (0, 0))

    editor = Editor(workspace)
    # Fill the backup table.  The first write creates the file (and so makes
    # no backup), so the count only reaches the cap on the second one.
    for index in range(202):
        editor.write_file("hot.txt", f"v{index}\n")
    backup_dir = workspace / ".minicc" / "backup"
    assert len(list(backup_dir.iterdir())) >= 200, "the backup table is not full"

    editor.write_file("old.txt", "changed\n")

    backups = list(backup_dir.iterdir())
    old_backups = [item for item in backups if item.name.startswith("old.txt")]
    assert old_backups, (
        "the backup of the pre-edit content was deleted by the edit that "
        "created it"
    )
    assert "original" in old_backups[0].read_text(encoding="utf-8"), (
        "the surviving backup does not hold the pre-edit content"
    )


# --- M8-T302: a memory file we cannot read must not be overwritten ------------


def test_an_unreadable_memory_file_is_not_overwritten(tmp_path: Path) -> None:
    """A read failure must not be mistaken for "the file is empty"."""
    workspace = tmp_path / "ws"
    (workspace / ".minicc").mkdir(parents=True)
    memory_file = workspace / ".minicc" / "MEMORY.md"
    original = "- [mem-aaaa1111] (created=2026-01-01T00:00:00Z, source=model) 重要结论\n"
    memory_file.write_bytes(original.encode("gbk"))

    tools = MemoryTools(workspace)
    with pytest.raises(Exception) as excinfo:
        tools.append(MemoryEntry(
            id="mem-bbbb2222",
            scope="project",
            content="新记忆",
            created="2026-01-02T00:00:00Z",
            source="model",
        ))
    assert "memory" in str(excinfo.value).lower(), (
        f"the refusal did not name the memory file: {excinfo.value}"
    )
    assert memory_file.read_bytes() == original.encode("gbk"), (
        "the unreadable memory file was overwritten"
    )


def test_a_readable_memory_file_is_appended(tmp_path: Path) -> None:
    """The control: the ordinary path still appends."""
    workspace = tmp_path / "ws"
    (workspace / ".minicc").mkdir(parents=True)
    memory_file = workspace / ".minicc" / "MEMORY.md"
    original = "- [mem-aaaa1111] (created=2026-01-01T00:00:00Z, source=model) 重要结论\n"
    memory_file.write_text(original, encoding="utf-8")

    tools = MemoryTools(workspace)
    tools.append(MemoryEntry(
        id="mem-bbbb2222",
        scope="project",
        content="新记忆",
        created="2026-01-02T00:00:00Z",
        source="model",
    ))
    text = memory_file.read_text(encoding="utf-8")
    assert "重要结论" in text, "the earlier memory was lost"
    assert "新记忆" in text
