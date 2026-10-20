"""M8-T297 — 提到检查点标记的消息，不该被当成检查点删掉

`[CONTEXT COMPACTED]` 是本项目自己的检查点标记。原来对它的判定是**子串
匹配**，于是任何一条**提到**这个标记的消息都被当成检查点：

* 它被从对话里移走 → **用户自己的话从模型的上下文里消失了**；
* 它的���实（文件路径、digest、失败信息）一条都不进检查点。

触发很容易：模型把检查点复述回来、用户粘了一段含该标记的日志。

本门禁钉住：只有**形状确凿**的检查点（标记在开头，后面是带版本的 JSON）
才被当成检查点；其它消息留在对话里，事实照常提取。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from minicc.agent.context import (
    COMPACTION_MARKER,
    _checkpoint_message,
    compact_with_checkpoint,
)


def _long_history() -> list[dict[str, Any]]:
    return [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "A" * 300},
        {"role": "assistant", "content": "B" * 300},
        {"role": "user", "content": "C" * 300},
        {"role": "assistant", "content": "D" * 300},
    ]


def test_a_message_that_mentions_the_marker_keeps_its_place() -> None:
    """The user's own words must not disappear from the context."""
    history = _long_history()
    history.insert(2, {
        "role": "user",
        "content": f"{COMPACTION_MARKER} 是个标记，我想知道它是什么意思",
    })

    compacted, _checkpoint = compact_with_checkpoint(history, threshold=100, keep_recent=2)
    kept = [str(item.get("content") or "") for item in compacted]
    assert any("我想知道它是什么意思" in text for text in kept), (
        "the message was removed from the conversation"
    )


def test_a_message_that_mentions_the_marker_still_contributes_its_facts() -> None:
    """Its facts are extracted, not dropped."""
    history = _long_history()
    history.insert(2, {
        "role": "user",
        "content": f"{COMPACTION_MARKER} 顺便说一句：必须修复 src/app.py 里的解析器",
    })

    _compacted, checkpoint = compact_with_checkpoint(history, threshold=100, keep_recent=2)
    assert checkpoint is not None
    objectives = " ".join(str(item) for item in checkpoint.get("objectives", []))
    assert "src/app.py" in objectives, checkpoint


def test_a_real_checkpoint_is_still_taken_out_of_the_conversation() -> None:
    """The control: our own checkpoint is recognised and merged.

    The compacted conversation carries **one** checkpoint - the merged
    one.  A prior checkpoint is folded into it, not carried alongside.
    """
    ours = _checkpoint_message({
        "version": 3,
        "objectives": ["做点事"],
        "archive": {"messages": 2, "characters": 10},
    })
    history = _long_history()
    history.insert(2, ours)

    compacted, checkpoint = compact_with_checkpoint(history, threshold=100, keep_recent=2)
    assert checkpoint is not None
    assert checkpoint.get("objectives"), checkpoint

    markers = [
        item for item in compacted
        if str(item.get("content") or "").startswith(COMPACTION_MARKER)
    ]
    assert len(markers) == 1, (
        f"the conversation carries {len(markers)} checkpoints; the prior one "
        "was not folded into the new one"
    )


def test_a_checkpoint_mentioning_its_own_marker_in_the_middle_is_kept() -> None:
    """A model quoting the checkpoint back must not delete itself."""
    history = _long_history()
    history.insert(2, {
        "role": "assistant",
        "content": f"我看到一条 {COMPACTION_MARKER} 记录，里面说要做点事",
    })

    compacted, _checkpoint = compact_with_checkpoint(history, threshold=100, keep_recent=2)
    kept = " ".join(str(item.get("content") or "") for item in compacted)
    assert "我看到一条" in kept, "the quoted message was removed"
