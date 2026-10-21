"""M8-T331 / M8-T345 — 每一个 manifest 写者都必须在锁里，而门禁要看**锁**

`capture()` 是 `manifest.json` 的第五个读者/写者，却是**唯一**一个在模块锁
之外的。而它写的 manifest 是**从零开始**的（**根本没有** `touched` 键）。

它与 journal 的 `before_write`/`after_write` 交错时，那次写会把对方刚写进去的
`touched`（前置镜像 / 确认 digest）**整段抹掉**：磁盘上预制镜像还在，manifest
却不再列出它 → `restore` 跳过那个文件并报"普通跳过"——**正是加锁要消灭的那个
症状**。

M8-T345：**这条门禁原本看不见它要钉的东西。** 它把 `_save` 同时替换给两个
写者，于是第二个写者被**测试自己的事件**（`release_save`）挡住，而不是被**模块
锁**挡住——把 `capture` 的锁整个摘掉，这条门禁照样全绿（已实测）。

现在两件事分开钉：

* **动态**：capture 在写盘期间，另一个**按生产路径取锁**的写者进不来；
* **静态**：`minicc/snapshots.py` 里每一个 `_save(...)` 调用点都在
  `with _MANIFEST_LOCK` 里面——"每一个写者"这句话不再只是标题。
"""

from __future__ import annotations

import ast
import threading
import time
from pathlib import Path
from typing import Any

from minicc.snapshots import capture


def test_the_capture_holds_the_lock_while_it_writes(tmp_path: Path) -> None:
    """While the capture writes, no other writer may enter the manifest lock."""
    import minicc.snapshots as snapshots_module

    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "a.py").write_text("a\n", encoding="utf-8")

    real_save = snapshots_module._save
    inside_save = threading.Event()
    release_save = threading.Event()
    other_write = threading.Event()
    entered_lock = threading.Event()
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
            try:
                # M8-T345: a real second writer (the journal's before_write /
                # after_write) takes the **module lock** and only then touches
                # the manifest.  The gate has to watch the lock, not the
                # test's own event: with the monkeypatch on both writers the
                # second one waited on ``release_save``, so the lock's
                # absence stayed invisible - the gate was blind to the very
                # mutation it claimed to pin.
                with snapshots_module._MANIFEST_LOCK:
                    entered_lock.set()
            finally:
                other_done.set()

        writer_thread = threading.Thread(target=other_writer)
        writer_thread.start()
        assert other_write.wait(timeout=10), "the second writer never started"
        time.sleep(0.3)  # wait-claim: the second writer has had its chance to start
        assert not entered_lock.is_set(), (
            "a second writer entered the manifest lock while the capture was writing"
        )
        release_save.set()
        for thread in (capture_thread, writer_thread):
            thread.join(timeout=30)
            assert not thread.is_alive(), "a snapshot thread outlived its join"
        assert entered_lock.is_set(), "the second writer never got the lock"
        assert other_done.is_set(), "the second writer never finished"
    finally:
        snapshots_module._save = real_save  # type: ignore[assignment]


def test_every_manifest_writer_calls_save_inside_the_module_lock() -> None:
    """The "every writer" half: no writer may write outside the lock."""
    import minicc.snapshots as snapshots_module

    source = Path(str(snapshots_module.__file__)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    parents: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node

    def inside_lock(node: ast.AST) -> bool:
        cursor: ast.AST | None = node
        while cursor is not None:
            if isinstance(cursor, ast.With):
                for item in cursor.items:
                    if any(
                        isinstance(part, ast.Name) and part.id == "_MANIFEST_LOCK"
                        for part in ast.walk(item.context_expr)
                    ):
                        return True
            cursor = parents.get(cursor)
        return False

    call_sites = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_save"
    ]
    assert call_sites, "the manifest writer disappeared"
    outside = sorted(node.lineno for node in call_sites if not inside_lock(node))
    assert not outside, (
        f"these manifest writers call _save outside the module lock: {outside}"
    )
