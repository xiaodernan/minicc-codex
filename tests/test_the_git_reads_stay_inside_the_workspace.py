"""M8-T842: a git read answers about the workspace, not about its container.

Git finds a repository by walking up from the working directory. The read tools
used to hand that behaviour straight to the model, so a workspace that is a
subdirectory of a larger checkout reported - and named - files the agent is not
allowed to open. Real-run evidence: an inspection workspace under this repo
listed ``../../_check_failures.py`` and four sibling probe scripts.

The rule these tests pin: at the repository root there is nothing to narrow and
behaviour is unchanged; anywhere below it, ``status``, ``diff`` and ``summary``
answer only about paths under the workspace.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from minicc.tools.git import GitTools


def _git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(f"git {args} failed: {completed.stderr}")
    return (completed.stdout or "").strip()


def _prepare(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "minicc-test")
    (tmp_path / "outside.txt").write_text("base\n", encoding="utf-8")
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "inside.txt").write_text("base\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "base commit")
    return workspace


def _dirty_both(workspace: Path) -> None:
    (workspace / "inside.txt").write_text("changed inside\n", encoding="utf-8")
    (workspace.parent / "outside.txt").write_text("changed outside\n", encoding="utf-8")


def _visible(result) -> str:
    """Everything the model would see: ToolResult splits long output into head/tail."""
    return "\n".join(part for part in (result.output, result.head, result.tail) if part)


def test_status_names_only_files_inside_the_workspace(tmp_path: Path) -> None:
    workspace = _prepare(tmp_path)
    _dirty_both(workspace)

    result = GitTools(workspace).status({})

    assert result.status == "ok"
    assert "inside.txt" in _visible(result)
    assert "outside.txt" not in _visible(result), (
        "a read answered about the enclosing repository: " + _visible(result)
    )


def test_summary_counts_only_the_workspaces_own_changes(tmp_path: Path) -> None:
    workspace = _prepare(tmp_path)
    _dirty_both(workspace)

    result = GitTools(workspace).summary({})

    assert result.status == "ok"
    assert result.data["dirty_count"] == 1, result.data


def test_diff_does_not_show_changes_outside_the_workspace(tmp_path: Path) -> None:
    workspace = _prepare(tmp_path)
    _dirty_both(workspace)

    result = GitTools(workspace).diff({})

    assert result.status == "ok"
    assert "inside.txt" in _visible(result)
    assert "outside.txt" not in _visible(result)


def test_a_workspace_at_the_repository_root_still_sees_its_whole_tree(tmp_path: Path) -> None:
    _prepare(tmp_path)

    (tmp_path / "outside.txt").write_text("changed at root\n", encoding="utf-8")
    result = GitTools(tmp_path).status({})

    assert result.status == "ok"
    assert "outside.txt" in _visible(result)
