"""M8-T560（第五百四十二批）：审计里的移动只说了源，目标那头被答成「没有这个文件」。

`_audit_paths` 把 `move` 记的那条**路径**放进集合——那是**源**（`minicc/tools/editor.py:745`
里 `self._audit("move", src, f"→ {dst}", ...)`），移动成功之后源已经不在；兜底那一步
只列还在的文件（`minicc/changes.py:545` 的 `is_file()`），于是这一行说得出动作、说得出
一个路径，面板却答「什么都没变」。新位置只在 `detail` 里，从来没被读过。

git 看得见两头的时候（源 deleted + 目标 ?? ）这条不成立；成立的是 git **看不见**的两种
工作区：没有仓库，和目标被 `.gitignore` 挡住。探针 probe_560 实测：

  P1 无仓库，真跑 `Editor.move`          -> total=0，两头都没有
  P2 git 仓库 + `out/` 被忽略            -> 只有源以 deleted 出现，目标没有
  P5 合成的 `move` 行，`detail` 没有箭头 -> 什么都不列（修法不许凭空造路径）
  P6 合成行，目标是个目录                -> 不列成文件
  P7 对照：无仓库里一条真 `write`        -> 照常列出（audit）
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from minicc.changes import ChangeInspector
from minicc.tools.editor import Editor

FILES = {"notes.md": "hello world\nsecond line\n", "keep.txt": "stay\n"}


def _workspace(root: Path, name: str, files: dict[str, str] | None = None) -> Path:
    workspace = root / name
    for rel, body in (files if files is not None else FILES).items():
        target = workspace / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def _repo(workspace: Path) -> Path:
    for argv in (
        ["git", "init", "-q"],
        ["git", "config", "user.email", "t560@example.com"],
        ["git", "config", "user.name", "t560"],
        ["git", "add", "-A"],
        ["git", "commit", "-qm", "base"],
    ):
        subprocess.run(argv, cwd=workspace, check=True, capture_output=True)
    return workspace


def _audit(workspace: Path, records: list[dict]) -> None:
    trail = workspace / ".minicc" / "audit.jsonl"
    trail.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(json.dumps(record, ensure_ascii=False) for record in records)
    trail.write_text(body + "\n", encoding="utf-8")


def _move(workspace: Path, src: str, dst: str) -> None:
    Editor(workspace, audit_path=workspace / ".minicc" / "audit.jsonl").move(src, dst)


def _paths(summary: dict) -> list[str]:
    return [str(item["path"]) for item in summary["files"]]


# --------------------------------------------------------------------------
# 目标那一头
# --------------------------------------------------------------------------

def test_a_real_move_lists_the_file_that_exists_now(tmp_path: Path) -> None:
    """移动之后还在的那个文件是这次操作的产物——面板一个都没列。"""
    workspace = _workspace(tmp_path, "real")
    _move(workspace, "notes.md", "out/renamed.md")
    summary = ChangeInspector(workspace).summary()
    assert _paths(summary) == ["out/renamed.md"], summary
    assert summary["files"][0]["raw"] == "audit", summary


def test_a_synthetic_move_record_lists_its_destination(tmp_path: Path) -> None:
    """轨迹可以是编辑器之外的人写的：认的是同一份 `→ 路径` 拼法。"""
    workspace = _workspace(tmp_path, "synthetic")
    (workspace / "out").mkdir()
    (workspace / "out" / "renamed.md").write_text("hello world\n", encoding="utf-8")
    (workspace / "notes.md").unlink()
    _audit(workspace, [{"action": "move", "path": "notes.md", "detail": "→ out/renamed.md"}])
    assert _paths(ChangeInspector(workspace).summary()) == ["out/renamed.md"]


def test_the_listed_destination_diffs_like_a_change(tmp_path: Path) -> None:
    """清单列了它，详情页就不能说它没改。"""
    workspace = _workspace(tmp_path, "detail")
    _move(workspace, "notes.md", "out/renamed.md")
    inspector = ChangeInspector(workspace)
    diff = inspector.diff("out/renamed.md")
    assert diff["status"] == "modified", diff
    assert diff["patch"].strip(), diff
    assert diff["additions"] == 2, diff


def test_a_gitignored_destination_is_still_listed(tmp_path: Path) -> None:
    """git 拒绝看的那个位置，审计替它作证。"""
    workspace = _workspace(tmp_path, "ignored")
    (workspace / ".gitignore").write_text("out/\n", encoding="utf-8")
    _repo(workspace)
    _move(workspace, "notes.md", "out/renamed.md")
    summary = ChangeInspector(workspace).summary()
    listed = {str(item["path"]): str(item["raw"]) for item in summary["files"]}
    assert listed.get("out/renamed.md") == "audit", listed
    assert "notes.md" in listed, listed


# --------------------------------------------------------------------------
# 对照：git 看得见两头时不能多列、不能重列
# --------------------------------------------------------------------------

def test_the_control_a_move_git_can_see_lists_each_path_once(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, "both-visible")
    _repo(workspace)
    _move(workspace, "notes.md", "out/renamed.md")
    summary = ChangeInspector(workspace).summary()
    paths = _paths(summary)
    assert "out/renamed.md" in paths, paths
    assert len(paths) == len(set(paths)), summary


def test_the_control_a_real_write_is_still_listed(tmp_path: Path) -> None:
    """第五百三十一批的那条路没被本批改道。"""
    workspace = _workspace(tmp_path, "write-control")
    _audit(workspace, [{"action": "write", "path": "keep.txt", "detail": "4 chars"}])
    assert _paths(ChangeInspector(workspace).summary()) == ["keep.txt"]


def test_the_control_a_deleted_file_is_not_answered_a_change(tmp_path: Path) -> None:
    """`delete` 点名的文件已经不在了——本批不给它一个形状（见 §7）。"""
    workspace = _workspace(tmp_path, "delete-control")
    Editor(workspace, audit_path=workspace / ".minicc" / "audit.jsonl").delete("notes.md")
    summary = ChangeInspector(workspace).summary()
    assert _paths(summary) == [], summary
    assert summary["audit_records_without_action"] == 0, summary


# --------------------------------------------------------------------------
# 读不出目标时，什么都不许造
# --------------------------------------------------------------------------

def test_a_move_record_without_the_arrow_invents_no_destination(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, "no-arrow")
    (workspace / "out").mkdir()
    (workspace / "out" / "renamed.md").write_text("hello world\n", encoding="utf-8")
    (workspace / "notes.md").unlink()
    _audit(workspace, [{"action": "move", "path": "notes.md", "detail": "relocated"}])
    assert _paths(ChangeInspector(workspace).summary()) == []


def test_an_empty_destination_is_not_a_path(tmp_path: Path) -> None:
    for index, detail in enumerate(("→ ", "→   ", "→\t")):
        workspace = _workspace(tmp_path, f"empty-destination{index}")
        (workspace / "notes.md").unlink()
        _audit(workspace, [{"action": "move", "path": "notes.md", "detail": detail}])
        assert _paths(ChangeInspector(workspace).summary()) == [], detail


def test_a_destination_that_is_not_a_string_is_not_a_path(tmp_path: Path) -> None:
    """强转动作在第五百三十九批吃过一次亏：这里把 `str()` 出来的名字真的造出来。"""
    for index, detail in enumerate((["out-x"], 42, True, None)):
        workspace = _workspace(tmp_path, f"shaped-destination{index}")
        (workspace / "notes.md").unlink()
        (workspace / str(detail)).write_text("x\n", encoding="utf-8")
        _audit(workspace, [{"action": "move", "path": "notes.md", "detail": detail}])
        assert _paths(ChangeInspector(workspace).summary()) == [], detail


def test_an_arrow_in_a_write_detail_is_not_a_destination(tmp_path: Path) -> None:
    """`→ 路径` 是 `move` 那一行的拼法；一条 `write` 的 detail 里出现它，
    不代表这次写还造了另一个文件。"""
    workspace = _workspace(tmp_path, "arrow-in-write")
    _audit(workspace, [{"action": "write", "path": "keep.txt", "detail": "→ notes.md"}])
    assert _paths(ChangeInspector(workspace).summary()) == ["keep.txt"]


def test_a_destination_wrapped_in_a_container_keeps_the_readable_line(tmp_path: Path) -> None:
    """一个读不出形状的 `detail` 不能把整本兜底带走：同一次审计里那条写得出来的还得在。"""
    workspace = _workspace(tmp_path, "boxed-detail")
    (workspace / "out").mkdir()
    (workspace / "out" / "renamed.md").write_text("hello world\n", encoding="utf-8")
    _audit(
        workspace,
        [
            {"action": "write", "path": "keep.txt", "detail": "5 chars"},
            {"action": "move", "path": "notes.md", "detail": ["→ out/renamed.md"]},
        ],
    )
    summary = ChangeInspector(workspace).summary()
    assert _paths(summary) == ["keep.txt", "notes.md"], summary
    assert summary["audit_read_error"] is None, summary


def test_a_destination_outside_the_workspace_is_not_listed(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, "ws")
    (workspace / "notes.md").unlink()
    (tmp_path / "escape.md").write_text("out of tree\n", encoding="utf-8")
    _audit(workspace, [{"action": "move", "path": "notes.md", "detail": "→ ../escape.md"}])
    assert _paths(ChangeInspector(workspace).summary()) == []


def test_a_directory_shaped_destination_is_not_listed(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, "dir-destination")
    (workspace / "somedir").mkdir()
    (workspace / "notes.md").unlink()
    _audit(workspace, [{"action": "move", "path": "notes.md", "detail": "→ somedir"}])
    assert _paths(ChangeInspector(workspace).summary()) == []


def test_a_backslash_spelled_destination_is_listed(tmp_path: Path) -> None:
    """目标走的是同一份归一化：`out\\renamed.md` 与 `out/renamed.md` 是一个文件。"""
    workspace = _workspace(tmp_path, "backslash")
    (workspace / "out").mkdir()
    (workspace / "out" / "renamed.md").write_text("hello world\n", encoding="utf-8")
    (workspace / "notes.md").unlink()
    _audit(
        workspace,
        [{"action": "move", "path": "notes.md", "detail": "→ out\\renamed.md"}],
    )
    assert _paths(ChangeInspector(workspace).summary()) == ["out/renamed.md"]


def test_a_backslash_spelled_internal_destination_is_not_listed(tmp_path: Path) -> None:
    """归一化管的是工具自己的那本账：反斜杠拼法绕过忽略名单，就把备份读成改动。"""
    workspace = _workspace(tmp_path, "backslash-internal")
    backup = workspace / ".minicc" / "backup"
    backup.mkdir(parents=True)
    (backup / "notes.md.2026").write_text("old\n", encoding="utf-8")
    _audit(
        workspace,
        [{"action": "move", "path": "notes.md", "detail": "→ .minicc\\backup\\notes.md.2026"}],
    )
    assert _paths(ChangeInspector(workspace).summary()) == ["notes.md"]


def test_the_destination_is_read_only_for_a_record_with_a_usable_source(
    tmp_path: Path,
) -> None:
    """闸门顺序：源那一格读不出来，整条记录就已经进了第五百三十九批那本账。"""
    workspace = _workspace(tmp_path, "bad-source")
    _audit(workspace, [{"action": "move", "path": 123, "detail": "→ keep.txt"}])
    summary = ChangeInspector(workspace).summary()
    assert _paths(summary) == [], summary
    assert summary["audit_records_without_path"] == 1, summary


def test_a_destination_inside_the_tools_own_state_is_not_listed(tmp_path: Path) -> None:
    """`.minicc/` 里的东西不是工作区的改动——第五百三十六批那条规矩也管目标。"""
    workspace = _workspace(tmp_path, "internal-destination")
    backup = workspace / ".minicc" / "backup"
    backup.mkdir(parents=True)
    (backup / "notes.md.2026").write_text("old\n", encoding="utf-8")
    _audit(
        workspace,
        [{"action": "move", "path": "notes.md", "detail": "→ .minicc/backup/notes.md.2026"}],
    )
    assert _paths(ChangeInspector(workspace).summary()) == ["notes.md"]


def test_a_refused_move_adds_no_destination(tmp_path: Path) -> None:
    """第五百四十批那道闸门在前：一行拒绝既没写源，也没写目标。"""
    workspace = _workspace(tmp_path, "refused")
    (workspace / "out").mkdir()
    (workspace / "out" / "renamed.md").write_text("was here\n", encoding="utf-8")
    _audit(
        workspace,
        [{"action": "move", "path": "notes.md", "detail": "拒绝: 目标已存在 out/renamed.md"}],
    )
    summary = ChangeInspector(workspace).summary()
    assert _paths(summary) == [], summary
    assert summary["audit_refused_records"] == 1, summary


def test_the_arrow_is_read_for_move_alone(tmp_path: Path):
    """`backup` 那行也写 `→ 名字`（编辑器里同一份拼法），它不是工作区的改动。"""
    workspace = _workspace(tmp_path, "backup")
    _audit(
        workspace,
        [
            {
                "action": "backup",
                "path": ".minicc/backup/notes.md.2026",
                "detail": "→ notes.md",
            }
        ],
    )
    assert _paths(ChangeInspector(workspace).summary()) == []


def test_the_destination_is_read_through_one_home(tmp_path: Path) -> None:
    """`→ 路径` 的读法只有一个家，面板不能自己拼一份。"""
    root = Path(__file__).resolve().parents[1] / "minicc"
    sources = {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(root.rglob("*.py"))
    }
    owners = [name for name, text in sources.items() if "def move_destination(" in text]
    assert owners == ["editor.py"], owners
    changes = sources["changes.py"]
    assert "move_destination(" in changes, "面板没有问那个家"
    assert '"→ "' not in changes, "面板自己复制了拼法"
