"""M8-T300 — 时间窗要按"上次**构建**"算，而且要真的到期

检索索引的 memo 键是 stat 签名（免费的），而"等长原地改写"这个洞由**时间窗**
兜底：记录超过 `RECORD_MAX_AGE_SECONDS` 就重建。

但第一版的记账有两处自相矛盾：

* 时间戳记的是"上次**被看到**"，不是"上次**被构建**"——于是年龄永远不增长；
* 时间戳只在"缓存变了"的分支上刷新——树没变时**早退**，时间戳永不刷新。

净效果：窗口一旦过期，年龄只增不减 → 每次刷新都重读整棵树。而重建出的
记录**值相等** → 缓存比较仍然相等 → 继续早退 → 时间戳仍不刷新 → **永久重建**。

这与注释承诺的"每个窗口每文件一次读取"正好相反，也破坏了索引自己的契约
（未变树的刷新不得打开任何文件体）。

本门禁钉住：窗口到期后重建**一次**，之后不再重建。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from minicc.agent.retrieval import LocalEvidenceIndex


def _counted_index(workspace: Path) -> tuple[LocalEvidenceIndex, list[str]]:
    index = LocalEvidenceIndex(workspace, refresh_interval=0.0)
    builds: list[str] = []

    original = index._build_record

    def counting(path: Path, rel: str):
        builds.append(rel)
        return original(path, rel)

    index._build_record = counting  # type: ignore[method-assign]
    return index, builds


def test_the_window_expires_once_and_then_the_reads_stop(tmp_path: Path) -> None:
    """One read per file per window - not one per tick."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "a.py").write_text("x = 1\n", encoding="utf-8")

    index, builds = _counted_index(workspace)
    index.refresh()
    assert len(builds) == 1, builds

    # The window is gone: the next refresh rebuilds.
    index._record_built = {key: value - 3600 for key, value in index._record_built.items()}
    index.refresh()
    assert len(builds) == 2, f"the window did not expire: {builds}"

    # And the ticks after that must not read again.
    index.refresh()
    index.refresh()
    assert len(builds) == 2, (
        f"the tree was re-read on every tick after the window expired: {builds}"
    )


def test_an_unchanged_tree_is_not_re_read_at_all(tmp_path: Path) -> None:
    """The index's own contract, and the reason the age exists."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    for index in range(5):
        (workspace / f"f{index}.py").write_text("x = 1\n", encoding="utf-8")

    index, builds = _counted_index(workspace)
    index.refresh()
    assert len(builds) == 5, builds
    index.refresh()
    index.refresh()
    assert len(builds) == 5, (
        f"an unchanged tree was re-read: {builds}"
    )
