"""M8-T318 — 静默截断：被丢掉的东西必须**被点名**

`extract_mention_tokens` 扫到 `MENTION_MAX_FILES`（10）就 `break` —— 第 11 条
及以后的提及**消失得干干净净**：没有记录、注入块里没有说明、事件流里也没有。

于是一条"被看过又被丢掉"的提及，和一条"**从来没写过**"的提及长得一模一样。
而**字节预算**那条通道早就有 `omitted` 状态（"超出注入预算"）——**同一种损失，
两条通道，一条会说话、一条不会**。

实测的代价：10 个被拒的提及（`/etc/passwd` 之类）+ 1 个**合法**的提及排在第 11
位 → 那个合法文件**完全没有出现**，而预算一点没花。

本门禁钉住：超出的提及**有名有姓**（记录 + 注入块里的说明）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from minicc.mentions import (
    MENTION_MAX_FILES,
    build_mention_context,
    extract_mention_tokens,
)


def test_the_cap_still_bounds_the_tokens(tmp_path: Path) -> None:
    """The control: the public contract is unchanged."""
    names = " ".join(f"@f{index}.py" for index in range(MENTION_MAX_FILES + 5))
    tokens = extract_mention_tokens(names)
    assert len(tokens) == MENTION_MAX_FILES, tokens


def test_a_mention_past_the_cap_is_named(tmp_path: Path) -> None:
    """The eleventh mention gets a record."""
    (tmp_path / "real.txt").write_text("hello\n", encoding="utf-8")
    names = " ".join(f"@/etc/passwd{index}" for index in range(MENTION_MAX_FILES))
    message = f"{names} @real.txt"

    _block, records = build_mention_context(message, tmp_path)

    named = {item["token"] for item in records}
    assert "real.txt" in named, (
        f"the mention past the cap was dropped without a trace: {records}"
    )
    dropped = [item for item in records if item["token"] == "real.txt"]
    assert dropped[0]["status"] == "omitted", dropped
    assert dropped[0]["reason"], dropped


def test_the_block_says_so(tmp_path: Path) -> None:
    """The model is told, not left to guess."""
    (tmp_path / "real.txt").write_text("hello\n", encoding="utf-8")
    names = " ".join(f"@/etc/passwd{index}" for index in range(MENTION_MAX_FILES))
    message = f"{names} @real.txt"

    block, _records = build_mention_context(message, tmp_path)
    assert "real.txt" in block, block
    assert "条数上限" in block or "超出" in block, block


def test_a_mention_inside_the_cap_is_still_injected(tmp_path: Path) -> None:
    """The control: the ordinary case is unchanged."""
    (tmp_path / "real.txt").write_text("hello\n", encoding="utf-8")
    block, records = build_mention_context("please look at @real.txt", tmp_path)
    assert "hello" in block, block
    assert records[0]["status"] == "injected", records


def test_nothing_is_dropped_when_everything_fits(tmp_path: Path) -> None:
    """The control: no note when there is nothing to note."""
    (tmp_path / "a.txt").write_text("a\n", encoding="utf-8")
    block, records = build_mention_context("@a.txt", tmp_path)
    assert len(records) == 1, records
    assert "条数上限" not in block, block
