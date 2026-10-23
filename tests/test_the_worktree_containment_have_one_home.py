"""The worktree containment check must have exactly one home."""

from __future__ import annotations

import pathlib

import pytest

from minicc.worktree import WorktreeError, WorktreeManager

REPO = pathlib.Path(__file__).resolve().parents[1]


def _manager(tmp_path: pathlib.Path) -> WorktreeManager:
    return WorktreeManager(tmp_path)


def test_home_returns_the_resolved_target(tmp_path):
    manager = _manager(tmp_path)
    target = manager._target_within_root("feature-a")
    assert target == (manager.root / "feature-a").resolve()


def test_home_rejects_an_escape(tmp_path):
    manager = _manager(tmp_path)
    with pytest.raises(WorktreeError, match="worktree 路径越界"):
        manager._target_within_root("../outside")


def test_census_exactly_one_message_and_it_is_the_home():
    hits = []
    for path in sorted((REPO / "minicc").rglob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if "worktree 路径越界" in line:
                hits.append((path.relative_to(REPO).as_posix(), lineno))
    assert len(hits) == 1, hits
    path, lineno = hits[0]
    assert path == "minicc/worktree.py"
    source = (REPO / path).read_text(encoding="utf-8")
    lines = source.splitlines()
    window = "\n".join(lines[max(0, lineno - 12):lineno + 2])
    assert "def _target_within_root" in window, window


def test_call_sites_use_the_home():
    source = (REPO / "minicc" / "worktree.py").read_text(encoding="utf-8")
    assert source.count("_target_within_root(") == 3
