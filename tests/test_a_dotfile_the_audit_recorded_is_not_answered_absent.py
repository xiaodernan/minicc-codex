"""M8-T556: a dotfile the audit recorded is not a file that never changed.

``_audit_paths`` admits a recorded path only when it passes
``not path.startswith(".") and not _ignored_path(path)``.  ``_ignored_path``
already refuses the tool's own state (``.git``, ``.minicc`` and its prefix
list), so the leading-dot clause adds nothing but a silent veto of every
user dotfile: ``.env``, ``.gitignore``, ``.editorconfig``.  The git-status
reader has never had that clause - it decides with ``_ignored_path`` alone -
so the two sources disagree about which paths exist.  Measured on HEAD
through ``summary()`` / ``diff()``:

| 形状 | 结果 |
| --- | --- |
| A 非仓库，`.env` 与 `.gitignore` 各有一条可读记录 | total=0，计数 0 |
| B 非仓库，只有 `.env` 一条记录 | total=0；diff(".env") 是 clean、空补丁 |
| C 仓库，`.env` 在 .gitignore 里，写后只有审计记下 | total=0（git status 只有 `?? .minicc/`） |
| D 仓库，被跟踪的点文件改了（git 看得见） | total=1，与审计无关 |
| E 对照：点文件存在但没有记录 | total=0（不该被列） |
| F 对照：`.minicc/`、`node_modules/`、`output/` 的记录 | total=0（内部状态不该被列） |
| G 对照：记录点名了不存在的点文件 | total=0（不该列幽灵） |

A/B/C are the defect: the only witness recorded the write, and the panel
answers "no such file".  The fix is one predicate - the audit fallback now
uses the same ``_ignored_path`` the git path uses - so a dotfile is kept
unless it is the tool's own state, and internal paths stay hidden.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from minicc.changes import ChangeInspector

GIT = ["-c", "user.email=t@example.test", "-c", "user.name=t"]


def _record(path: str, action: str = "write") -> str:
    return json.dumps(
        {"timestamp": "2026-10-30T00:00:00+08:00", "action": action, "path": path},
        ensure_ascii=False,
    )


def _audit(workspace: Path, *records: str) -> Path:
    audit = workspace / ".minicc" / "audit.jsonl"
    audit.parent.mkdir(parents=True, exist_ok=True)
    audit.write_text("\n".join(records) + "\n", encoding="utf-8")
    return audit


def _git(workspace: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *GIT, *args],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _paths(inspector: ChangeInspector) -> list[str]:
    return [item["path"] for item in inspector.summary()["files"]]


def test_a_dotfile_the_audit_recorded_is_listed(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("TOKEN=abc\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text(".env\n", encoding="utf-8")
    _audit(tmp_path, _record(".env"), _record(".gitignore"))
    summary = ChangeInspector(tmp_path).summary()
    assert sorted(item["path"] for item in summary["files"]) == [
        ".env",
        ".gitignore",
    ], summary
    assert summary["total_files"] == 2, summary


def test_the_dotfile_the_audit_recorded_is_not_answered_clean(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("TOKEN=abc\n", encoding="utf-8")
    _audit(tmp_path, _record(".env"))
    diff = ChangeInspector(tmp_path).diff(".env")
    assert diff["status"] == "modified", diff
    assert "+TOKEN=abc" in diff["patch"], diff


def test_the_gitignored_write_only_the_audit_witnessed_is_listed(tmp_path: Path) -> None:
    """git status sees only ``?? .minicc/``; the audit sees the ``.env`` write."""
    (tmp_path / ".gitignore").write_text(".env\n", encoding="utf-8")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "init")
    (tmp_path / ".env").write_text("TOKEN=abc\n", encoding="utf-8")
    _audit(tmp_path, _record(".env"))
    status = _git(tmp_path, "status", "--porcelain").stdout
    assert "?? .minicc/" in status and ".env" not in status, status
    summary = ChangeInspector(tmp_path).summary()
    assert summary["total_files"] == 1, summary
    item = summary["files"][0]
    assert item["path"] == ".env" and item["raw"] == "audit", item
    assert summary.get("status_read_error") is None, summary


def test_the_gitignored_write_is_not_answered_clean_by_the_diff(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text(".env\n", encoding="utf-8")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "init")
    (tmp_path / ".env").write_text("TOKEN=abc\n", encoding="utf-8")
    _audit(tmp_path, _record(".env"))
    diff = ChangeInspector(tmp_path).diff(".env")
    assert diff["status"] == "modified", diff
    assert "+TOKEN=abc" in diff["patch"], diff


def test_a_dotfile_the_repository_sees_is_still_listed_once(tmp_path: Path) -> None:
    """Control: when git witnesses it, the audit must not duplicate the file."""
    (tmp_path / ".editorconfig").write_text("root = true\n", encoding="utf-8")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "init")
    (tmp_path / ".editorconfig").write_text("root = false\n", encoding="utf-8")
    _audit(tmp_path, _record(".editorconfig"))
    summary = ChangeInspector(tmp_path).summary()
    assert summary["total_files"] == 1, summary
    item = summary["files"][0]
    assert item["path"] == ".editorconfig" and item["raw"] != "audit", item


def test_the_control_a_dotfile_no_record_names_is_still_absent(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("TOKEN=abc\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("hello\n", encoding="utf-8")
    _audit(tmp_path, _record("notes.md"))
    assert _paths(ChangeInspector(tmp_path)) == ["notes.md"]


def test_the_control_internal_paths_are_still_not_listed(tmp_path: Path) -> None:
    for name in (".minicc/snapshots/step.json", "node_modules/x.js", "output/log.txt"):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("hello\n", encoding="utf-8")
    _audit(
        tmp_path,
        _record(".minicc/snapshots/step.json"),
        _record("node_modules/x.js"),
        _record("output/log.txt"),
        _record("notes.md"),
    )
    assert _paths(ChangeInspector(tmp_path)) == ["notes.md"]


def test_the_control_a_recorded_dotfile_that_is_gone_is_still_absent(
    tmp_path: Path,
) -> None:
    (tmp_path / "notes.md").write_text("hello\n", encoding="utf-8")
    _audit(tmp_path, _record(".env"))
    summary = ChangeInspector(tmp_path).summary()
    assert summary["total_files"] == 0, summary
