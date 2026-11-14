"""Workspace digest: read-only fact pack for /api/digest and the Almanac.

M8-T905: the digest answers "what is this place" with numbers read from
git and the repository's own documents — never from the network. These
tests pin: it works on a real git repository, it degrades to is_git:false
(and never raises) on a plain directory, and the roadmap/changelog
counters read the files that actually exist.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from minicc.digest import build_digest


def _git(workspace: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=workspace,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        timeout=10,
    ).stdout


@pytest.fixture()
def git_repo(tmp_path: Path) -> Path:
    ws = tmp_path / "repo"
    ws.mkdir()
    _git(ws, "init", "-b", "main")
    _git(ws, "config", "user.email", "digest@example.test")
    _git(ws, "config", "user.name", "Digest Test")
    (ws / "a.txt").write_text("one", encoding="utf-8")
    _git(ws, "add", "a.txt")
    _git(ws, "commit", "-m", "first")
    (ws / "b.txt").write_text("two", encoding="utf-8")
    _git(ws, "add", "b.txt")
    _git(ws, "commit", "-m", "second")
    return ws


def test_digest_in_a_real_git_repo(git_repo: Path) -> None:
    payload = build_digest(git_repo)
    assert payload["schema_version"] == "minicc.digest.v1"
    assert payload["is_git"] is True
    assert payload["branch"] == "main"
    assert payload["head_short"]
    assert payload["total_commits"] == 2
    assert payload["first_commit_at"]
    assert payload["tracked_files"] == 2
    # nothing under tests/ yet
    assert payload["test_files"] == 0
    # an untracked file shows up as dirty
    (git_repo / "dirty.txt").write_text("x", encoding="utf-8")
    assert build_digest(git_repo)["dirty_entries"] == 1
    # upstream is not configured: the field degrades to null, never a crash
    assert payload["upstream_ahead"] is None
    assert payload["upstream_behind"] is None


def test_digest_without_git_degrades_and_never_raises(tmp_path: Path) -> None:
    ws = tmp_path / "plain"
    ws.mkdir()
    payload = build_digest(ws)
    assert payload["is_git"] is False
    assert payload["branch"] is None
    assert payload["head_short"] is None
    assert payload["total_commits"] is None
    assert payload["dirty_entries"] is None
    assert payload["tracked_files"] is None
    assert payload["test_files"] is None
    # the file-based counters still answer (the directory is readable)
    assert payload["roadmap_batches"] is None
    assert payload["changelog_lines"] is None


def test_digest_reads_roadmap_and_changelog_counts(git_repo: Path) -> None:
    docs = git_repo / "docs"
    docs.mkdir()
    roadmap = docs / "ROADMAP_TO_PRODUCT.md"
    roadmap.write_text(
        "# roadmap\n\n"
        "## 批次 900 - M8-T900: first\nbody\n"
        "## 批次 901 - M8-T901: second\nbody\n"
        "## 其它标题不算\nbody\n"
        "## 批次 902 - M8-T902: third\nbody\n",
        encoding="utf-8",
    )
    changelog = docs / "CHANGELOG.md"
    changelog.write_text("# changelog\n- one\n- two\n- three\n", encoding="utf-8")
    payload = build_digest(git_repo)
    assert payload["roadmap_batches"] == 3
    assert payload["roadmap_lines"] == 10
    assert payload["changelog_lines"] == 4


def test_digest_counts_test_files_by_git_pathspec(git_repo: Path) -> None:
    tests = git_repo / "tests"
    tests.mkdir()
    (tests / "test_one.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
    (tests / "frontend_smoke.mjs").write_text("// smoke\n", encoding="utf-8")
    (tests / "notes.txt").write_text("not a test\n", encoding="utf-8")
    _git(git_repo, "add", "tests")
    _git(git_repo, "commit", "-m", "add test files")
    payload = build_digest(git_repo)
    assert payload["test_files"] == 2
    assert payload["tracked_files"] == 5


def test_digest_missing_workspace_never_raises(tmp_path: Path) -> None:
    payload = build_digest(tmp_path / "does-not-exist")
    assert payload["is_git"] is False
    assert payload["workspace"].endswith("does-not-exist")


def test_digest_carries_recent_commits_bounded(git_repo: Path) -> None:
    payload = build_digest(git_repo)
    assert payload["recent_commits"] is not None
    recent = payload["recent_commits"]
    assert len(recent) == 2
    # newest first
    assert recent[0]["subject"] == "second"
    assert recent[1]["subject"] == "first"
    for item in recent:
        assert item["short"]
        assert item["at"]
        assert len(item["subject"]) <= 140
