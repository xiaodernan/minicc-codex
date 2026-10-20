"""M8-T331 — 同一份 manifest 的**每一个**写者都必须在锁里

`capture()` 是 `manifest.json` 的第五个读者/写者，却是**唯一**一个在模块锁
之外的。而它写的 manifest 是**从零开始**的（**根本没有** `touched` 键）。

它与 journal 的 `before_write`/`after_write` 交错时，那次写会把对方刚写进去的
`touched`（前置镜像 / 确认 digest）**整段抹掉**：磁盘上预制镜像还在，manifest
却不再列出它 → `restore` 跳过那个文件并报"普通跳过"——**正是加锁要消灭的那个
症状**。

（本门禁检验的是**机制**："capture 写盘期间，另一个写者进不来"。那个具体的交错
在今天的调用顺序下其实**难以发生**——journal 的构造需要 manifest 存在，而
manifest 正是 capture 写出来的——所以锁在这里是**防御性**的，而不是在补一个
天天发生的洞。门禁 nevertheless 钉住机制本身：锁一旦被摘掉，症状随时可能回来。）
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import pytest

from minicc.snapshots import capture


def test_the_capture_holds_the_lock_while_it_writes(tmp_path: Path) -> None:
    """While the capture writes, no other writer may write."""
    import minicc.snapshots as snapshots_module

    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "a.py").write_text("a\n", encoding="utf-8")

    real_save = snapshots_module._save
    inside_save = threading.Event()
    release_save = threading.Event()
    other_write = threading.Event()
    other_done = threading.Event()

    def blocking_save(dest: Path, manifest: dict[str, Any]) -> None:
        inside_save.set()
        release_save.wait(timeout=30)
        real_save(dest, manifest)

    snapshots_module._save = blocking_save  # type: ignore[assignment]
    try:
        capture_thread = threading.Thread(target=lambda: capture(workspace, "t1"))
        capture_thread.start()
        assert inside_save.wait(timeout=30), "the capture never reached its write"

        def other_writer() -> None:
            other_write.set()
            # The manifest exists now (the capture's write is in flight but
            # the file is there), so this is a legitimate second writer.
            try:
                snapshots_module._save(
                    snapshots_module.snapshot_dir(workspace.resolve(), "t1"),
                    {"version": 2, "touched": {"a.py": {"digest": "x"}}},
                )
            finally:
                other_done.set()

        writer_thread = threading.Thread(target=other_writer)
        writer_thread.start()
        assert other_write.wait(timeout=10), "the second writer never started"
        # The second writer must be **blocked** while the capture holds the
        # lock - that is the whole point.
        time.sleep(0.3)  # wait-claim: the second writer has had its chance to start
        assert not other_done.is_set(), (
            "a second writer went through while the capture was writing"
        )
        release_save.set()
        for thread in (capture_thread, writer_thread):
            thread.join(timeout=30)
            assert not thread.is_alive(), "a snapshot thread outlived its join"
        assert other_done.is_set(), "the second writer never finished"
    finally:
        snapshots_module._save = real_save  # type: ignore[assignment]
