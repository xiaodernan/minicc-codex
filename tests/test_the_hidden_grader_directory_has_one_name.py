"""M8-T349 — 「评测隐藏目录」这个名字只有一个，bench 与工具层必须说同一件事

`minicc/bench_tasks.py` 与 `minicc/tools/fs.py` 各有一份
`GRADER_DIR_NAME = ".graders"`。

而 `bench_tasks.resolve_grader_dir` 的 docstring 明写着："the ``.graders`` name
is blocked at the tool layer regardless"——**文档声明了两份名字必须一致，却没
有任何东西维持它**。

漂移一次的后果不是"两条路径给出不同答案"这么轻：bench 把评测驱动脚本放在
`<仓库同级>/.graders`，而工具层拒绝的是**另一个**名字时，隐藏目录就对 agent
可见了——而 M4-T5 的契约是"隐藏的评测驱动对 agent 必须既不可见也不可改"。

本门钉住：名字只有一个家；bench 的默认评测目录用的就是工具层拒绝的那个名字；
控制组——工具层照旧拒绝 `.graders` 路径。
"""

from __future__ import annotations

import pytest

from minicc import bench_tasks
from minicc.tools import fs


def test_the_hidden_grader_directory_has_one_name() -> None:
    """One home: the bench does not keep its own copy."""
    assert bench_tasks.GRADER_DIR_NAME is fs.GRADER_DIR_NAME


def test_the_bench_default_directory_carries_the_blocked_name() -> None:
    """The behaviour the docstring promises: the tool layer blocks that name."""
    default_dir = bench_tasks.resolve_grader_dir()
    assert default_dir.name == fs.GRADER_DIR_NAME, default_dir
    assert fs.GRADER_DIR_NAME in str(default_dir), default_dir


def test_the_tool_layer_still_refuses_that_directory() -> None:
    """The control: the refusal is still there."""
    with pytest.raises(Exception) as caught:
        fs._reject_graders(f"somewhere/{fs.GRADER_DIR_NAME}/grader.py")
    assert fs.GRADER_DIR_NAME in str(caught.value), caught.value
