"""M8-T546: a dirty read that failed is not a clean workspace.

Measured on HEAD before the change, four temporary repositories each holding one
untracked file (except the control), ``snapshots.capture`` asked what the
workspace looked like:

  A  git works, one dirty file   -> captured=True  complete=True  files=['a.txt']
  B  git works, nothing dirty    -> captured=True  complete=True  files=[]
  C  git status raises OSError   -> captured=True  complete=True  files=[]
  D  git status exits 128        -> captured=True  complete=True  files=[]

C and D are the same summary as B, and the manifest written to disk says
``files: []`` with no reason anywhere.  The caller stores that summary as the
task's ``workspace_snapshot`` checkpoint and goes on to hand the agent a
writable workspace, so a read that could not run is answered as 「the tree is
clean, there is nothing to preserve」.  The read fails for reasons users meet:
``fatal: detected dubious ownership`` (safe.directory), an ``index.lock`` held
by a concurrent git command, a twenty-second timeout on a large tree, or no git
on PATH at all.

The four outcomes are one answer today because ``_git_dirty_files`` returns a
bare list and its three failure branches all return ``[]``.  The fix gives the
read a second half — the reason — carries it into the manifest, and makes the
summary say out loud that it could not read.  The control gate exists so the
fix cannot be satisfied by calling every workspace unreadable: a repo with
nothing dirty must still answer ``captured=True`` and record that the read
succeeded.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from minicc import snapshots


def _repo(root: Path) -> None:
    for argv in (
        ["git", "init", "-q"],
        ["git", "config", "user.email", "t546@example.com"],
        ["git", "config", "user.name", "t546"],
    ):
        subprocess.run(argv, cwd=root, check=True, capture_output=True)


def _stub_status(monkeypatch: pytest.MonkeyPatch, answer) -> None:
    """Answer ``git status`` with ``answer()``; every other git call is real."""
    real_run = subprocess.run

    def run(argv, *args, **kwargs):
        if isinstance(argv, list) and argv[:2] == ["git", "status"]:
            return answer()
        return real_run(argv, *args, **kwargs)

    monkeypatch.setattr(snapshots.subprocess, "run", run)


def _manifest(root: Path, task_id: str) -> dict[str, object]:
    path = snapshots.snapshot_dir(root.resolve(), task_id) / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _refused(summary: dict[str, object], root: Path, task_id: str) -> None:
    """The shape every failed read must answer with, and only a failed read."""
    assert summary["captured"] is False, summary
    assert summary["complete"] is False and summary["partial"] is True, summary
    assert summary["files"] == [] and summary["skipped"] == [], summary
    reason = summary.get("reason")
    assert isinstance(reason, str) and reason.strip(), f"失败没有留下理由：{summary}"
    # The refusal has to survive the process, or the next reader of the snapshot
    # (restore, the Web face, a human) is back to reading an empty file list.
    assert _manifest(root, task_id).get("dirty_read_error") == reason, _manifest(root, task_id)


def test_git_that_cannot_run_is_not_a_clean_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _repo(root)
    (root / "a.txt").write_text("x", encoding="utf-8")

    def cannot_run():
        raise OSError("git 不可用")

    _stub_status(monkeypatch, cannot_run)
    summary = snapshots.capture(root, "t546-oserror")
    _refused(summary, root, "t546-oserror")
    assert "git status" in str(summary["reason"]), summary

    # A second capture answers from the manifest it could not complete, not from
    # a fresh guess about a workspace whose file list was never read.
    assert snapshots.capture(root, "t546-oserror")["captured"] is False


def test_a_git_that_exited_non_zero_is_not_a_clean_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _repo(root)
    (root / "a.txt").write_text("x", encoding="utf-8")

    def dubious_ownership():
        return SimpleNamespace(
            returncode=128, stdout="",
            stderr="fatal: detected dubious ownership in repository at '/tmp/repo'\n",
        )

    _stub_status(monkeypatch, dubious_ownership)
    summary = snapshots.capture(root, "t546-rc")
    _refused(summary, root, "t546-rc")
    reason = str(summary["reason"])
    assert "128" in reason, f"退出码没有留下来：{reason}"
    assert "dubious ownership" in reason, f"git 自己说的话没有留下来：{reason}"


def test_a_git_that_timed_out_is_not_a_clean_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _repo(root)
    (root / "a.txt").write_text("x", encoding="utf-8")

    def timed_out():
        raise subprocess.TimeoutExpired(["git", "status", "--porcelain=v1", "-z", "-uall"], 20)

    _stub_status(monkeypatch, timed_out)
    summary = snapshots.capture(root, "t546-timeout")
    _refused(summary, root, "t546-timeout")
    assert "超时" in str(summary["reason"]), summary


def test_a_repo_with_nothing_dirty_still_says_it_read_the_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control: an empty file list is also the truth, and must stay sayable.

    Without this gate the three above are satisfied by a reader that calls every
    workspace unreadable — the same shape of false green, pointed the other way.
    """
    root = tmp_path / "repo"
    root.mkdir()
    _repo(root)
    summary = snapshots.capture(root, "t546-clean")
    assert summary["captured"] is True and summary["complete"] is True, summary
    assert summary["files"] == [] and summary["skipped"] == [], summary
    assert "reason" not in summary, summary
    assert _manifest(root, "t546-clean").get("dirty_read_error") is None, _manifest(root, "t546-clean")
