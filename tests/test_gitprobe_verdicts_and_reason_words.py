"""M8-T762 — ``minicc/gitprobe.py`` 的判定词汇与推理句构造器。

这个模块是"目录是不是一个 git 工作树"的唯一家（M8-T547/548/546/628），
加上三类 ``git status`` 失败的**唯一**文字家。单测直接锁词汇表与函数契约：

1. ``work_tree_verdict`` 的三动词词汇（"yes"/"no"/"unknown"）；
2. 对临时 git 仓库 → ``("yes", "")``；对普通目录 → ``("no", "")``；对临时 git 仓库
   里的子目录 → ``("yes", "")``；
3. ``subprocess.run`` 直接抛异常 → ``("unknown", 原因非空)``；
4. 三个 ``git_status_*_reason`` 携带入参里的事实：exit code、stderr 第一行、
   ``timeout_seconds`` 的整数化。
"""

from __future__ import annotations

import subprocess

import pytest

from minicc import gitprobe


REPO_FALLBACK = True  # git 在开发机上可用（CI runner 也可用）


def _init_repo(path):
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)


def test_work_tree_verdict_vocabulary():
    assert gitprobe.WORK_TREE_VERDICT_YES == "yes"
    assert gitprobe.WORK_TREE_VERDICT_NO == "no"
    assert gitprobe.WORK_TREE_VERDICT_UNKNOWN == "unknown"


def test_work_tree_verdict_inside_a_repo(tmp_path):
    _init_repo(tmp_path)
    verdict, why = gitprobe.work_tree_verdict(tmp_path)
    assert verdict == "yes"
    assert why == ""


def test_work_tree_verdict_inside_a_subdirectory(tmp_path):
    _init_repo(tmp_path)
    sub = tmp_path / "sub"
    sub.mkdir()
    verdict, why = gitprobe.work_tree_verdict(sub)
    assert verdict == "yes"
    assert why == ""


def test_work_tree_verdict_outside_a_repo(tmp_path):
    verdict, why = gitprobe.work_tree_verdict(tmp_path)
    assert verdict == "no"
    assert why == ""


def test_work_tree_verdict_wallpaper_is_unknown_when_git_cannot_run(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("git not found")

    monkeypatch.setattr(subprocess, "run", boom)
    verdict, why = gitprobe.work_tree_verdict(tmp_path)
    assert verdict == "unknown"
    assert "git not found" in why


def test_git_status_unavailable_reason_carries_timeout_and_subject():
    text = gitprobe.git_status_unavailable_reason(None, timeout_seconds=20.0, subject="ctx")
    assert "20" in text
    assert "ctx" in text


def test_git_status_unavailable_reason_with_exception_mentions_it():
    text = gitprobe.git_status_unavailable_reason(OSError("boom"), subject="ctx")
    assert "boom" in text


def test_git_status_timeout_reason_carries_seconds_and_subject():
    text = gitprobe.git_status_timeout_reason(5.5, "changes")
    assert "5" in text
    assert "changes" in text


def test_git_status_exit_reason_carries_code_and_first_stderr_line():
    text = gitprobe.git_status_exit_reason(128, "fatal: not a git repository.\nsecond line")
    assert "128" in text
    assert "fatal: not a git repository." in text
    assert "second line" not in text  # 只带第一行


def test_git_status_exit_reason_works_without_stderr():
    text = gitprobe.git_status_exit_reason(2, "")
    assert "2" in text
