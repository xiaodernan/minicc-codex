"""`minicc --digest` — the read-only repository digest on the CLI surface.

M8-T905 shipped `/api/digest`; M8-T913 brings the same fact pack to the CLI
for operators who never open the web workbench. These tests pin the happy
paths (git and non-git workspaces) and the JSON/human split of output.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from minicc.main import main


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MINICC_HOME", str(tmp_path / "home"))


def _git(workspace: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=workspace,
        check=True,
        capture_output=True,
        timeout=10,
    )


def test_digest_on_a_plain_directory(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ws = tmp_path / "plain"
    ws.mkdir()
    rc = main(["--digest", "--workspace", str(ws)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "repository: not a git work tree" in out
    assert "commits:" not in out  # honest absence of git facts


def test_digest_json_on_a_plain_directory(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ws = tmp_path / "plain"
    ws.mkdir()
    rc = main(["--digest", "--json", "--workspace", str(ws)])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["schema_version"] == "minicc.digest.v1"
    assert payload["is_git"] is False
    assert payload["total_commits"] is None


def test_digest_on_a_real_git_repo(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ws = tmp_path / "repo"
    ws.mkdir()
    _git(ws, "init", "-b", "main")
    _git(ws, "config", "user.email", "digest@example.test")
    _git(ws, "config", "user.name", "Digest CLI")
    (ws / "a.txt").write_text("one", encoding="utf-8")
    _git(ws, "add", "a.txt")
    _git(ws, "commit", "-m", "first")
    rc = main(["--digest", "--workspace", str(ws)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "repository: git" in out
    assert "branch: main" in out
    assert "commits: 1" in out
    assert "roadmap batches: —" in out


def test_digest_json_matches_the_http_schema(git_repo, capsys: pytest.CaptureFixture[str]) -> None:
    # git_repo fixture lives in tests/test_workspace_digest.py; replicate inline
    ws = git_repo
    rc = main(["--digest", "--json", "--workspace", str(ws)])
    payload = json.loads(capsys.readouterr().out)
    assert payload["is_git"] is True
    assert payload["total_commits"] == 2
    assert "first_commit_at" in payload
    assert payload["schema_version"] == "minicc.digest.v1"


@pytest.fixture()
def git_repo(tmp_path: Path) -> Path:
    ws = tmp_path / "repo"
    ws.mkdir()
    _git(ws, "init", "-b", "main")
    _git(ws, "config", "user.email", "digest@example.test")
    _git(ws, "config", "user.name", "Digest CLI")
    (ws / "a.txt").write_text("one", encoding="utf-8")
    _git(ws, "add", "a.txt")
    _git(ws, "commit", "-m", "first")
    (ws / "b.txt").write_text("two", encoding="utf-8")
    _git(ws, "add", "b.txt")
    _git(ws, "commit", "-m", "second")
    return ws
