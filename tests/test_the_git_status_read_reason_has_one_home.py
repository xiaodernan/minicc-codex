"""M8-T546 — the wording of a failed changed-file read has one home.

「git status 为什么没能告诉我改了什么」的失败句子，以前在三个模块里各拼一遍：
the agent loop's ``_git_changed_paths``, the snapshot reader's
``_git_dirty_files`` and the change view's ``_status_failure``.  Same fact
(git did not run / git timed out / git exited N), three homes, each
hand-spelling its own copy - and each copy drifted.

The home is ``minicc/gitprobe.py``: the work-tree probe (M8-T547/548) already
settled where that question lives, and the failure wording is that same
question's answer.  The builders below are the one home; every reader asks
them, and no reader hand-spells the sentence.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/gitprobe.py"
SENTENCES = (
    "git status 无法运行",
    "git status 超时",
    "git status 退出码",
)
READERS = {
    "minicc/agent/loop.py": (
        "git_status_unavailable_reason(",
        "git_status_timeout_reason(",
        "git_status_exit_reason(",
    ),
    "minicc/snapshots.py": (
        "git_status_unavailable_reason(",
        "git_status_timeout_reason(",
        "git_status_exit_reason(",
    ),
    "minicc/changes.py": (
        "git_status_unavailable_reason(",
        "git_status_exit_reason(",
    ),
}


def _sites(fragment: str) -> list[str]:
    found: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if fragment in node.value:
                    found.append(f"{path.relative_to(REPO).as_posix()}:{node.lineno}")
    return found


def test_the_home_pins_each_failure_sentence() -> None:
    from minicc.gitprobe import (
        git_status_exit_reason,
        git_status_timeout_reason,
        git_status_unavailable_reason,
    )

    assert git_status_unavailable_reason(RuntimeError("git")) == "git status 无法运行: git"
    assert git_status_timeout_reason(15, "改动清单") == (
        "git status 超时（15 秒）：工作区可能太大，改动清单没有读出来"
    )
    assert git_status_exit_reason(128, "fatal: detected dubious ownership\n") == (
        "git status 退出码 128: fatal: detected dubious ownership"
    )


def test_each_failure_sentence_has_exactly_one_home() -> None:
    for sentence in SENTENCES:
        offenders = _sites(sentence)
        homes = {site.split(":", 1)[0] for site in offenders}
        assert homes == {HOME}, (
            f"the sentence {sentence!r} is spelled outside its one home: "
            + ", ".join(sorted(homes))
        )


def test_the_readers_ask_the_single_home() -> None:
    for rel, builders in READERS.items():
        src = (REPO / rel).read_text(encoding="utf-8")
        for builder in builders:
            assert builder in src, f"{rel} must ask the gitprobe home via {builder}"


def test_the_shared_git_helper_carries_the_failure_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M8-T551: the shared ``_git`` carries the reason, so timeout and
    unrunnable-git are no longer one collapsed answer."""
    import minicc.changes as changes
    from minicc.changes import ChangeInspector

    def timed_out():
        raise subprocess.TimeoutExpired(["git", "status"], 20)

    real_run = subprocess.run

    def run(argv, *args, **kwargs):
        if isinstance(argv, list) and argv[:2] == ["git", "status"]:
            return timed_out()
        return real_run(argv, *args, **kwargs)

    monkeypatch.setattr(changes.subprocess, "run", run)
    workspace = tmp_path / "plain"
    workspace.mkdir()
    lines, reason = ChangeInspector(workspace)._status_lines()
    assert lines == []
    assert reason is not None
    assert "超时" in reason, reason
