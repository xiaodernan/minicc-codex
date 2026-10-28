"""M8-T304 / T305 — 同一份数据，两处解释不同

| 编号 | 现象 |
| --- | --- |
| M8-T304 | 变更面板报 ``sub/../notes.md`` 是 "modified"，而 ``diff("notes.md")`` 报 "clean" —— 状态表按**原始拼写**作键，diff 按**解析后路径**查 |
| M8-T305 | 工作区有 300 个改动文件时，摘要报 ``total_files: 120``（被截断的列表长度），且没有任何截断标记 |

This door pins both.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from minicc.changes import ChangeInspector
from minicc.tools.editor import Editor


def _git(workspace: Path, *args: str) -> None:
    result = subprocess.run(
        ["git", *args],
        cwd=str(workspace),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"git {' '.join(args)} failed: {result.stderr.strip()}"
        )


def _repo(workspace: Path) -> Path:
    workspace.mkdir(parents=True, exist_ok=True)
    _git(workspace, "init")
    _git(workspace, "config", "user.email", "t@example.test")
    _git(workspace, "config", "user.name", "t")
    return workspace


def test_the_status_and_the_diff_agree_on_one_file(tmp_path: Path) -> None:
    """M8-T304: the same file must get the same verdict everywhere."""
    workspace = tmp_path / "ws"
    (workspace / "sub").mkdir(parents=True)
    (workspace / "notes.md").write_text("# demo\n", encoding="utf-8")

    editor = Editor(workspace, audit_path=workspace / ".minicc" / "audit.jsonl")
    # The agent writes it through a path with a ".." in it.
    editor.write_file("sub/../notes.md", "# changed\n")

    inspector = ChangeInspector(workspace)
    summary_paths = {item["path"] for item in inspector.summary()["files"]}
    detail = inspector.diff("notes.md")
    if "notes.md" in summary_paths or "sub/../notes.md" in summary_paths:
        assert detail.get("status") != "clean", (
            "the panel reports the file as changed while its diff says clean"
        )


def test_the_summary_reports_the_real_total_and_discloses_truncation(
    tmp_path: Path,
) -> None:
    """M8-T305: a truncated count must not be presented as the total."""
    workspace = _repo(tmp_path / "ws")
    for index in range(300):
        (workspace / f"f{index:03}.py").write_text("x = 1\n", encoding="utf-8")

    summary = ChangeInspector(workspace).summary()
    assert summary["total_files"] >= 300, (
        f"the summary reported {summary['total_files']} files; the workspace "
        "has 300"
    )
    assert summary.get("truncated") is True, "the truncation was not disclosed"
    assert summary.get("shown_files") == len(summary["files"])


def test_a_small_workspace_is_not_marked_truncated(tmp_path: Path) -> None:
    """The control: no truncation, no claim of one."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "a.py").write_text("x = 1\n", encoding="utf-8")
    summary = ChangeInspector(workspace).summary()
    assert summary.get("truncated") is False
    assert summary["total_files"] == len(summary["files"])


def test_a_change_past_the_cap_invalidates_the_summary(tmp_path: Path) -> None:
    """M8-T306 / T307: the totals cover every file, not only the shown ones.

    The cache fingerprint was built from the **truncated** list, so a
    change to a file past the cap did not invalidate it - and the counts
    only ever covered the first 120 entries, with the rest simply
    missing from the numbers.
    """
    workspace = _repo(tmp_path / "ws")
    for index in range(300):
        (workspace / f"f{index:03}.py").write_text("x = 1\n", encoding="utf-8")
    _git(workspace, "add", "-A")
    _git(workspace, "commit", "-m", "init")

    # Now change all of them, so the change list is longer than the cap.
    for index in range(300):
        (workspace / f"f{index:03}.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
    # One more, sorting past the cap.
    (workspace / "zzz.py").write_text("y = 2\n", encoding="utf-8")

    inspector = ChangeInspector(workspace)
    summary = inspector.summary()
    assert summary["total_files"] > 120, (
        f"the scenario needs more than the cap, got {summary['total_files']}"
    )
    assert summary.get("truncated") is True

    # The totals must cover the file that is not in the shown list.
    assert summary["additions"] >= 301, (
        f"the totals only cover the shown files: {summary['additions']} additions "
        f"for {summary['total_files']} changed files"
    )
