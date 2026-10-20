"""M8-T321 — 一道门禁要算"存在"，必须先在仓库里

这一批的前身是一次**很具体的翻车**：M8-T320 的修复早就在树里，它的门禁文件
也**在工作树里存在**，而且**在全量套件里跑过**（pytest 收集的是文件系统，
不是 git 索引）——但它**从未 `git add` 过**。于是：

* 它**从没进过任何一个提交**；
* 文档指针检查器读的是 `git ls-files`，所以它**看不见**这条门禁；
* 谁把它删掉（它看起来就是个临时产物），**没有任何东西会红**。

也就是说：那条修复当时是**无人看守**的。

本门禁钉住：**`tests/` 下每一个门禁文件都必须被 git 跟踪**。

它有一条明确的代价，而且这个代价就是它的意义：写完门禁必须 `git add`，
否则套件是红的。这正是上一批学到的——**"工作树里的文件"只是"还没被提交的
文件"**，包括那些看起来像正式门禁的。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
TESTS = REPO / "tests"


def _tracked_test_files() -> set[str]:
    """The gate files git knows about, or skip when git cannot answer."""
    try:
        completed = subprocess.run(
            ["git", "ls-files", "--", "tests/"],
            cwd=REPO,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        pytest.skip("git is not available here")
    if completed.returncode != 0:
        pytest.skip("this is not a git working tree")
    return {
        Path(line.strip()).name
        for line in completed.stdout.splitlines()
        if line.strip().startswith("tests/test_")
    }


def test_every_gate_file_on_disk_is_tracked_by_git() -> None:
    """A gate that is not in the repository is not a gate.

    The M8-T320 gate ran in this very suite and was in no commit: pytest
    collects the filesystem, so an untracked gate looks exactly like a
    tracked one until somebody deletes it.
    """
    tracked = _tracked_test_files()
    on_disk = {path.name for path in TESTS.glob("test_*.py")}
    untracked = sorted(on_disk - tracked)
    assert not untracked, (
        "these gate files exist in the working tree but are not tracked by "
        f"git, so they are in no commit and the doc-pointer checker (which "
        f"reads `git ls-files`) cannot see them: {untracked}. Add them: "
        f"`git add {' '.join('tests/' + name for name in untracked)}`"
    )


def test_the_tracked_gate_files_are_all_present_on_disk() -> None:
    """The other direction: a gate in the index but not on disk is dead too."""
    tracked = _tracked_test_files()
    on_disk = {path.name for path in TESTS.glob("test_*.py")}
    missing = sorted(tracked - on_disk)
    assert not missing, (
        f"these gate files are tracked but not on disk: {missing}"
    )


def test_the_check_itself_is_tracked() -> None:
    """The meta-gate obeys the rule it enforces."""
    tracked = _tracked_test_files()
    assert Path(__file__).name in tracked, (
        "this file is not tracked by git - it is the gate that says gates "
        "must be tracked, and it is not"
    )


def test_every_gate_file_contains_at_least_one_test() -> None:
    """A file with no test in it guards nothing.

    pytest collects a module and finds no test in it: the file is "there",
    the suite is green, and the thing it was supposed to check is not
    checked by anything.  The name alone (``test_*.py``) is not a promise.
    """
    import ast

    empty: list[str] = []
    for path in sorted(TESTS.glob("test_*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError) as exc:
            empty.append(f"{path.name} (unreadable: {exc})")
            continue
        found = False
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("test"):
                    found = True
                    break
            elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                found = True
                break
        if not found:
            empty.append(path.name)
    assert not empty, (
        "these gate files contain no test, so they guard nothing while "
        f"looking like guards: {empty}"
    )
