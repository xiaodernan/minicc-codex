"""Git workflow tools tests: summary digest + merge conflict precheck."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from minicc.tools.editor import Editor
from minicc.tools.git import GitTools
from minicc.tools.registry import ToolError


def _git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", check=False
    )
    if completed.returncode != 0:
        raise AssertionError(f"git {args} failed: {completed.stderr}")
    return (completed.stdout or "").strip()


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "minicc-test")
    (tmp_path / "file.txt").write_text("base\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "base commit")
    return tmp_path


def test_summary_reports_branch_and_dirty_state(repo: Path) -> None:
    tools = GitTools(repo)
    result = tools.summary({})
    assert result.status == "ok"
    assert result.data["branch"] == "main" or result.data["branch"] == "master"
    assert result.data["dirty_count"] == 0
    assert "base commit" in result.data["last_commit"]

    (repo / "file.txt").write_text("changed\n", encoding="utf-8")
    dirty = tools.summary({})
    assert dirty.data["dirty_count"] == 1


def test_merge_precheck_clean_merge(repo: Path) -> None:
    _git(repo, "checkout", "-q", "-b", "feature-clean")
    (repo / "feature.txt").write_text("feature\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "feature work")
    _git(repo, "checkout", "-q", "main" if _git(repo, "branch", "--show-current") == "main" else "master")
    tools = GitTools(repo)
    result = tools.merge_precheck({"branch": "feature-clean"})
    assert result.status == "ok"
    assert result.data["clean"] is True
    assert result.data["conflicts"] == []


def test_merge_precheck_reports_conflicts(repo: Path) -> None:
    current = _git(repo, "branch", "--show-current")
    _git(repo, "checkout", "-q", "-b", "feature-conflict")
    (repo / "file.txt").write_text("feature version\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "feature edit")
    _git(repo, "checkout", "-q", current)
    (repo / "file.txt").write_text("main version\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "main edit")

    tools = GitTools(repo)
    result = tools.merge_precheck({"branch": "feature-conflict"})
    assert result.status == "ok"  # precheck succeeds; the merge itself would conflict
    assert result.data["clean"] is False
    assert len(result.data["conflicts"]) >= 1


def test_merge_precheck_rejects_bad_branch(repo: Path) -> None:
    tools = GitTools(repo)
    with pytest.raises(ToolError, match="branch 参数非法"):
        tools.merge_precheck({"branch": ""})
    with pytest.raises(ToolError, match="branch 参数非法"):
        tools.merge_precheck({"branch": "--exec=rm"})


def test_registered_as_readonly(repo: Path) -> None:
    from minicc.tools import build_registry

    registry = build_registry(Editor(repo))
    assert registry.risk_of("git_summary") == "readonly"
    assert registry.risk_of("git_merge_precheck") == "readonly"
    assert registry.spec("git_merge_precheck") is not None
