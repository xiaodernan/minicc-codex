"""M8-T548: a change view that could not read git may not answer 「没有变更」.

``ChangeInspector.summary()`` builds the file list from ``_status_lines()``.
That helper answered a bare list, and ``git status`` failing answered ``[]`` —
the same answer as a clean tree.  Measured on HEAD, six shapes through
``summary()``:

| 形状 | total_files | 有错误键 |
| --- | --- | --- |
| A 仓库，改了一个文件 | 1 | 无 |
| B 仓库，干净 | 0 | 无 |
| C 非仓库目录（支持的形态） | 0 | 无 |
| D 仓库，status 退出 128（dubious ownership） | 0 | 无 |
| E git 无法运行 | 0 | 无 |
| F status 超时 | 0 | 无 |

B is a true "nothing changed"; C is a supported empty baseline (the module
exists for fresh interview repositories with no commit yet); D, E and F are
"I could not read the tree" - and the panel told all five the same thing.
The per-file ``diff()`` path had the same collapse twice: its status map was
empty, so the file was called ``clean``, and the ``clean`` shortcut copied
the file onto its own baseline, printing an empty patch for a modified file.

The fix separates 「the tree is clean」 from 「the tree could not be read」:
``_status_lines`` returns ``(lines, reason)``, ``summary()`` carries
``status_read_error``, and ``diff()`` carries the same reason and no longer
takes the clean shortcut while the status table is unknown.  A workspace
that is not a repository still answers ``None`` — that is a readable fact,
not a failed read.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from minicc.changes import ChangeInspector


def _git(workspace: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=str(workspace), capture_output=True, encoding="utf-8"
    )


def _repo(root: Path) -> Path:
    workspace = root / "ws"
    workspace.mkdir()
    _git(workspace, "init")
    _git(workspace, "config", "user.email", "t@example.test")
    _git(workspace, "config", "user.name", "t")
    (workspace / "a.txt").write_text("one\n", encoding="utf-8")
    _git(workspace, "add", "a.txt")
    _git(workspace, "commit", "-m", "init")
    return workspace


class _StubGit:
    """Answers ``git status`` with ``status()``; ``rev-parse`` with "true"."""

    def __init__(self, status):
        self.status = status

    def __enter__(self):
        import minicc.changes as changes

        real = changes.subprocess.run

        def run(argv, *args, **kwargs):
            if isinstance(argv, list) and argv[:2] == ["git", "status"]:
                return self.status()
            if isinstance(argv, list) and argv[:3] == ["git", "rev-parse", "--is-inside-work-tree"]:
                return SimpleNamespace(returncode=0, stdout="true\n", stderr="")
            return real(argv, *args, **kwargs)

        self.saved = real
        changes.subprocess.run = run
        return self

    def __exit__(self, *exc):
        import minicc.changes as changes

        changes.subprocess.run = self.saved


def _refused_status():
    return SimpleNamespace(
        returncode=128, stdout="",
        stderr="fatal: detected dubious ownership in repository at '/ws'\n",
    )


def _no_git():
    raise FileNotFoundError("git")


def _slow():
    raise subprocess.TimeoutExpired(["git", "status"], 20)


def test_a_failed_status_read_is_not_a_clean_workspace(tmp_path: Path) -> None:
    workspace = _repo(tmp_path)
    (workspace / "a.txt").write_text("one\ntwo\n", encoding="utf-8")

    with _StubGit(_refused_status):
        summary = ChangeInspector(workspace).summary()

    reason = summary.get("status_read_error")
    assert isinstance(reason, str) and reason, (
        f"读不出改动清单，变更视图却答了「没有变更」：{summary}"
    )
    assert "128" in reason and "dubious ownership" in reason, reason


def test_a_git_that_cannot_run_is_a_failed_read(tmp_path: Path) -> None:
    workspace = _repo(tmp_path)

    with _StubGit(_no_git):
        summary = ChangeInspector(workspace).summary()

    reason = summary.get("status_read_error")
    assert isinstance(reason, str) and reason, summary
    assert "无法运行" in reason, reason


def test_a_git_that_timed_out_is_a_failed_read(tmp_path: Path) -> None:
    workspace = _repo(tmp_path)

    with _StubGit(_slow):
        summary = ChangeInspector(workspace).summary()

    reason = summary.get("status_read_error")
    assert isinstance(reason, str) and reason, summary
    assert "超时" in reason, reason


def test_the_control_a_clean_repo_still_says_it_read_the_tree(tmp_path: Path) -> None:
    """A clean tree has no error; otherwise the three gates above are cheap."""
    workspace = _repo(tmp_path)
    summary = ChangeInspector(workspace).summary()
    assert summary["total_files"] == 0
    assert summary.get("status_read_error") is None, summary


def test_a_workspace_that_is_not_a_repository_is_not_a_failed_read(tmp_path: Path) -> None:
    """The module's own reason to exist: a fresh workspace with no repository.

    If 「not a repository」 raised the failure flag, every fresh interview
    workspace would report an error instead of an empty change list.
    """
    workspace = tmp_path / "plain"
    workspace.mkdir()
    (workspace / "a.txt").write_text("free\n", encoding="utf-8")
    summary = ChangeInspector(workspace).summary()
    assert summary["total_files"] == 0
    assert summary.get("status_read_error") is None, summary


class _AllGitDown(_StubGit):
    """Every git command fails — no status, no baseline, no rev-parse."""

    def __enter__(self):
        import minicc.changes as changes

        real = changes.subprocess.run

        def run(argv, *args, **kwargs):
            if isinstance(argv, list) and argv[:1] == ["git"]:
                return SimpleNamespace(returncode=128, stdout="",
                                       stderr="fatal: detected dubious ownership in repository at '/ws'\n")
            return real(argv, *args, **kwargs)

        self.saved = real
        changes.subprocess.run = run
        return self

    def __exit__(self, *exc):
        import minicc.changes as changes

        changes.subprocess.run = self.saved


def test_a_diff_carries_the_same_failed_read(tmp_path: Path) -> None:
    """The per-file route answers with the same reason the summary does."""
    workspace = _repo(tmp_path)
    (workspace / "a.txt").write_text("one\ntwo\n", encoding="utf-8")

    with _StubGit(_refused_status):
        diff = ChangeInspector(workspace).diff("a.txt")

    reason = diff.get("status_read_error")
    assert isinstance(reason, str) and reason, diff
    assert "+two" in diff["patch"], diff["patch"]


def test_a_diff_of_a_modified_file_does_not_claim_it_did_not_change(
    tmp_path: Path,
) -> None:
    """All of git down: status unknown meant 「clean」, baseline empty meant
    「before == after」 — and the modified file diffed to an empty patch."""
    workspace = _repo(tmp_path)
    (workspace / "a.txt").write_text("one\ntwo\n", encoding="utf-8")

    with _AllGitDown(_refused_status):
        diff = ChangeInspector(workspace).diff("a.txt")

    assert diff["patch"].strip(), (
        f"改动清单读不出来时，diff 把改过的文件画成了空补丁：{diff}"
    )
    assert "+two" in diff["patch"], diff["patch"]


def test_the_control_a_clean_file_still_diffs_to_nothing(tmp_path: Path) -> None:
    """The clean shortcut is right when the status table was actually read."""
    workspace = _repo(tmp_path)
    diff = ChangeInspector(workspace).diff("a.txt")
    assert diff.get("status_read_error") is None, diff
    assert diff["patch"] == "", diff
