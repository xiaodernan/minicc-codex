"""M8-T333 — 一份**跑不起来**的评分规格，是坏任务文件，不是"工作区失败"

`spec_blockers` 校验规格的**形状**（文件非空、路径非空、命令非空），但不校验
**值**：

* `file_contract` 某一项的 `"regex": "["` → 评分脚本里的 `re.search` 抛
  `re.error` → 脚本以 **1** 退出；
* 而 `_GRADER_REFUSED = 2` 才是"我拒绝评判"——于是那次崩溃被记成
  **"工作区失败"**（`passed = False`），而不是 NO-RESULT；
* 也就是说：**代理已经跑完一整轮、已经被付费**，而失败的原因是**任务文件本身
  坏了**。

模块自己的契约写着："Same rule the grader applies, applied before the agent is
paid: a spec nobody can execute is a broken task file, not a workspace that
failed"。

本门禁钉住：不可执行的规格在**加载期**就被拒（两道门同一份答案）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from minicc.bench_tasks import loader_blockers, spec_blockers, validate_task


def _file_contract(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "t1",
        "category": "c",
        "prompt": "do it",
        "max_minutes": 5,
        "fixture": {"a.txt": "x"},
        "grader": {"type": "file_contract", "files": [item]},
    }


def test_an_uncompilable_regex_is_refused() -> None:
    """The grader script would raise on it."""
    spec = {"files": [{"path": "a.txt", "regex": "["}]}
    blockers = spec_blockers("file_contract", spec)
    assert blockers, "an uncompilable regex was accepted"
    assert loader_blockers("file_contract", spec), (
        "the loader accepted a spec the grader cannot run"
    )


def test_a_non_string_regex_is_refused() -> None:
    """The script would raise a TypeError on it."""
    spec = {"files": [{"path": "a.txt", "regex": 123}]}
    assert spec_blockers("file_contract", spec), spec
    assert loader_blockers("file_contract", spec), spec


def test_a_non_integer_expect_exit_is_refused() -> None:
    """``int(spec.get("expect_exit", 0))`` would raise."""
    spec = {"command": "python -c 'print(1)'", "expect_exit": None}
    assert spec_blockers("command_contract", spec), spec
    assert loader_blockers("command_contract", spec), spec


def test_a_non_string_stdout_marker_is_refused() -> None:
    """``marker not in proc.stdout`` would raise a TypeError."""
    spec = {"command": "python -c 'print(1)'", "stdout_contains": 123}
    assert spec_blockers("command_contract", spec), spec
    assert loader_blockers("command_contract", spec), spec


def test_the_task_file_is_refused_before_the_agent_runs() -> None:
    """The loader is the door that runs before the agent is paid."""
    task = _file_contract({"path": "a.txt", "regex": "["})
    with pytest.raises(ValueError):
        validate_task(task)


def test_a_usable_spec_is_still_accepted() -> None:
    """The control: the ordinary case is unchanged."""
    spec = {"files": [{"path": "a.txt", "regex": "x+"}]}
    assert spec_blockers("file_contract", spec) == [], spec
    assert loader_blockers("file_contract", spec) == [], spec

    command = {"command": "python -c 'print(1)'", "expect_exit": 0, "stdout_contains": "1"}
    assert spec_blockers("command_contract", command) == [], command
