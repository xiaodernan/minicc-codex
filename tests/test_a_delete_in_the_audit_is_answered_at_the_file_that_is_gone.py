"""M8-T561（第五百四十三批）：审计里已经消失的那一半，被答成「什么都没变」。

`_audit_paths` 把 `delete` 记的那条**路径**放进集合，兜底那一步却只列还在的文件
（`minicc/changes.py:733` 的 `(self.workspace / key).is_file()`）——而 `delete`
这一行说的那个文件，正因为这次操作成功才不在（`minicc/tools/editor.py:847` 在
`target.unlink()` 之后才写下这一行，删除前它还 `self._backup(target)`（:838）把内容
digest 过一遍）。于是这一行说得出动作、说得出一个路径、也说得出它删掉过什么，面板却
答「什么都没变」，`diff` 还答 `clean` 加空补丁。

git 看得见这条的时候（` D notes.md`）缺陷不成立；成立的是 git **看不见**的工作区：
没有仓库、文件被 `.gitignore` 挡住、还有从没提交过的新文件。探针 probe_561 实测：

  D1 无仓库，真跑 `Editor.delete`（轨迹里确有 backup + delete 两行）-> total=0
  D2 同上，问 `diff`                -> clean，补丁 0 字节（副本就在 .minicc/backup/ 里）
  D4 合成的 `delete` 行，文件已不在  -> total=0，diff clean
  D3 对照：git 仓库里删掉跟踪文件     -> deleted，补丁 71 字节（git 那一半本来就对）
  D6 窗口里先 create 后 delete 同一路径 -> 净零：本批也不该列它
  D7 先 delete 后 write 回来          -> 已经在清单里（modified），别变成 deleted
  D9 对照：根本没有轨迹、文件不在      -> total=0 且无理由（这不是缺陷）
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from minicc.changes import ChangeInspector
from minicc.tools.editor import Editor

FILES = {"notes.md": "hello world\nsecond line\n", "keep.txt": "stay\n"}
DIGEST = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


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
        ["git", "config", "user.email", "t561@example.com"],
        ["git", "config", "user.name", "t561"],
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


def _delete(workspace: Path, path: str) -> None:
    Editor(workspace, audit_path=workspace / ".minicc" / "audit.jsonl").delete(path)


def _records(*actions: tuple[str, str]) -> list[dict]:
    return [{"action": action, "path": path, "detail": "", "before_digest": DIGEST}
            for action, path in actions]


def _summary(workspace: Path) -> dict:
    return ChangeInspector(workspace).summary()


def _listed(summary: dict) -> dict[str, tuple[str, str]]:
    return {
        str(item["path"]): (str(item["status"]), str(item["raw"])) for item in summary["files"]
    }


def _paths(summary: dict) -> list[str]:
    return sorted(_listed(summary))


# --------------------------------------------------------------------------
# 删除那一头
# --------------------------------------------------------------------------

def test_a_real_delete_lists_the_file_that_is_gone(tmp_path: Path) -> None:
    """轨迹里确有这一行——面板一个也不列。"""
    workspace = _workspace(tmp_path, "real")
    _delete(workspace, "notes.md")
    summary = _summary(workspace)
    assert _paths(summary) == ["notes.md"], summary
    assert _listed(summary)["notes.md"] == ("deleted", "audit"), summary


def test_a_synthetic_delete_record_lists_the_file_that_is_gone(tmp_path: Path) -> None:
    """轨迹可以是编辑器之外的人写的：认的是同一份证据——删之前 digest 过内容。"""
    workspace = _workspace(tmp_path, "synthetic")
    (workspace / "notes.md").unlink()
    _audit(workspace, _records(("delete", "notes.md")))
    assert _listed(_summary(workspace))["notes.md"] == ("deleted", "audit")


def test_the_listed_deletion_is_not_answered_a_clean_tree(tmp_path: Path) -> None:
    """清单列了它，详情页就不能再说它 `clean`。

    第五百四十三批这一格只钉得住状态：那时补丁还是空的（那条批次的 §6 写了它不
    声称什么）。第五百四十四批把预像从编辑器自己留的副本里读了回来，所以这里
    钉的是「状态 + 内容都说得出」。
    """
    workspace = _workspace(tmp_path, "detail")
    _delete(workspace, "notes.md")
    diff = ChangeInspector(workspace).diff("notes.md")
    assert diff["status"] == "deleted", diff
    assert diff["deletions"] == 2 and "-hello world" in diff["patch"], diff


def test_an_untracked_file_removed_from_a_repository_is_listed(tmp_path: Path) -> None:
    """git 只看得见跟踪过的文件：从没提交过的那个删掉了，git 一字不提。"""
    workspace = _workspace(tmp_path, "untracked")
    _repo(workspace)
    (workspace / "fresh.md").write_text("never committed\n", encoding="utf-8")
    _delete(workspace, "fresh.md")
    summary = _summary(workspace)
    assert _listed(summary) == {"fresh.md": ("deleted", "audit")}, summary
    assert summary["total_files"] == 1, summary


def test_a_gitignored_deletion_is_still_listed(tmp_path: Path) -> None:
    """git 拒绝看的那个位置，审计替它作证。"""
    workspace = _workspace(tmp_path, "ignored", {"drafts/x.md": "draft\n", "keep.txt": "stay\n"})
    (workspace / ".gitignore").write_text("drafts/\n", encoding="utf-8")
    _repo(workspace)
    _delete(workspace, "drafts/x.md")
    summary = _summary(workspace)
    assert _listed(summary) == {"drafts/x.md": ("deleted", "audit")}, summary


def test_the_control_a_deletion_git_can_see_keeps_its_provenance(tmp_path: Path) -> None:
    """git 报得出这一条时，出处仍是 git，且一个路径只列一次。"""
    workspace = _workspace(tmp_path, "git-visible")
    _repo(workspace)
    _delete(workspace, "notes.md")
    summary = _summary(workspace)
    assert _listed(summary) == {"notes.md": ("deleted", " D notes.md")}, summary
    assert summary["total_files"] == 1, summary


def test_the_deletion_counts_the_lines_the_copy_kept(tmp_path: Path) -> None:
    """git 看不见这条删除，编辑器留下的副本看得见——数它不是硬造行数。

    第五百四十三批把这一格钉成对照（「不硬造」）；第五百四十四批从副本里读回了
    预像，第五百四十五批让清单跟着同一个数走，于是这一条从对照变成了作证。
    """
    workspace = _workspace(tmp_path, "counts")
    _delete(workspace, "notes.md")
    entry = _summary(workspace)["files"][0]
    assert (entry["additions"], entry["deletions"]) == (0, 2), entry


# --------------------------------------------------------------------------
# 先后与净零：一条 `delete` 是不是净效果，看窗口里的首末动作
# --------------------------------------------------------------------------

def test_a_file_created_then_deleted_claims_no_deletion(tmp_path: Path) -> None:
    """窗口里生又灭：工作区前后一样，列成 `deleted` 是凭空报一次改动。"""
    workspace = _workspace(tmp_path, "net-zero")
    _audit(workspace, _records(("create", "temp.md"), ("delete", "temp.md")))
    assert _paths(_summary(workspace)) == [], _summary(workspace)


def test_a_file_written_then_deleted_still_claims_the_deletion(tmp_path: Path) -> None:
    """先写过再删掉：净效果就是那个文件没了。"""
    workspace = _workspace(tmp_path, "write-then-delete")
    _audit(workspace, _records(("write", "notes.md"), ("delete", "notes.md")))
    (workspace / "notes.md").unlink(missing_ok=True)
    assert _listed(_summary(workspace))["notes.md"] == ("deleted", "audit")


def test_a_file_deleted_then_rewritten_is_answered_a_change_not_a_deletion(
    tmp_path: Path,
) -> None:
    """树说了算：文件又在了，就是改动而不是消失（修前已经是这个答案，别改道）。"""
    workspace = _workspace(tmp_path, "delete-then-create")
    _audit(workspace, _records(("delete", "notes.md"), ("create", "notes.md")))
    assert _listed(_summary(workspace))["notes.md"] == ("modified", "audit")


def test_a_file_deleted_recreated_and_deleted_again_claims_the_deletion(
    tmp_path: Path,
) -> None:
    """首末动作之间绕了一圈：窗口开头它就在那儿，结尾它没了。"""
    workspace = _workspace(tmp_path, "delete-create-delete")
    (workspace / "notes.md").unlink()
    _audit(
        workspace,
        _records(("delete", "notes.md"), ("create", "notes.md"), ("delete", "notes.md")),
    )
    assert _listed(_summary(workspace))["notes.md"] == ("deleted", "audit")


def test_the_last_line_about_a_path_decides_whether_it_is_gone(tmp_path: Path) -> None:
    """窗口里最后一行说的是移动：这份内容还在，只是换了名字（第五百四十二批那一头）。"""
    workspace = _workspace(tmp_path, "delete-then-move")
    (workspace / "out").mkdir()
    (workspace / "out" / "renamed.md").write_text("hello world\n", encoding="utf-8")
    (workspace / "notes.md").unlink()
    _audit(
        workspace,
        _records(("delete", "notes.md"))
        + [{"action": "move", "path": "notes.md", "detail": "→ out/renamed.md"}],
    )
    summary = _summary(workspace)
    assert _listed(summary) == {"out/renamed.md": ("modified", "audit")}, summary


# --------------------------------------------------------------------------
# 证据不足时，什么都不许造
# --------------------------------------------------------------------------

def test_a_delete_that_never_digested_a_file_claims_no_deletion(tmp_path: Path) -> None:
    """没有 `before_digest` 的这一行说不出它删掉了什么内容。"""
    workspace = _workspace(tmp_path, "no-witness")
    (workspace / "notes.md").unlink()
    _audit(workspace, [{"action": "delete", "path": "notes.md", "detail": ""}])
    summary = _summary(workspace)
    assert _paths(summary) == [], summary
    assert summary["audit_read_error"] is None, summary


def test_a_digest_that_is_not_a_string_is_not_a_witness(tmp_path: Path) -> None:
    """强转在第五百三十七、五百三十九两批各吃过一次亏：这里 `123` 会变成一个证人。"""
    for index, digest in enumerate((123, ["abc"], True, 4.5)):
        workspace = _workspace(tmp_path, f"shaped-digest{index}")
        (workspace / "notes.md").unlink()
        _audit(workspace, [{"action": "delete", "path": "notes.md", "before_digest": digest}])
        assert _paths(_summary(workspace)) == [], (index, digest)


def test_a_blank_digest_is_not_a_witness(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, "blank-digest")
    (workspace / "notes.md").unlink()
    _audit(workspace, [{"action": "delete", "path": "notes.md", "before_digest": "   "}])
    assert _paths(_summary(workspace)) == []


def test_a_refused_delete_lists_nothing(tmp_path: Path) -> None:
    """第五百四十批那道闸门在前：一行拒绝既没删文件，也没留证人。"""
    workspace = _workspace(tmp_path, "refused")
    (workspace / "notes.md").unlink()
    _audit(
        workspace,
        [{"action": "delete", "path": "notes.md", "detail": "拒绝: 权限不足", "before_digest": DIGEST}],
    )
    summary = _summary(workspace)
    assert _paths(summary) == [], summary
    assert summary["audit_refused_records"] == 1, summary


def test_a_record_without_an_action_still_holds_the_clean_shortcut(
    tmp_path: Path,
) -> None:
    """第五百四十一批那本账不变：说不出动作的行不是一次删除，也不列任何路径。"""
    workspace = _workspace(tmp_path, "no-action")
    (workspace / "notes.md").unlink()
    _audit(workspace, [{"action": "", "path": "notes.md", "before_digest": DIGEST}])
    summary = _summary(workspace)
    assert _paths(summary) == [], summary
    assert summary["audit_records_without_action"] == 1, summary


def test_a_delete_inside_the_tools_own_state_is_not_listed(tmp_path: Path) -> None:
    """`.minicc/` 里的东西不是工作区的改动——第五百三十六批那条规矩也管删除。"""
    workspace = _workspace(tmp_path, "internal")
    _audit(workspace, _records(("delete", ".minicc/backup/notes.md.2026")))
    assert _paths(_summary(workspace)) == []


def test_a_delete_outside_the_workspace_is_not_listed(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, "escape")
    (tmp_path / "escape.md").write_text("out of tree\n", encoding="utf-8")
    _audit(workspace, _records(("delete", "../escape.md")))
    summary = _summary(workspace)
    assert _paths(summary) == [], summary
    assert summary["audit_records_without_path"] == 0, summary


def test_a_directory_shaped_deletion_is_not_listed(tmp_path: Path) -> None:
    """`delete` 只删得掉文件：那一格被一个目录占着时，谁也没消失。"""
    workspace = _workspace(tmp_path, "dir-deletion")
    (workspace / "somedir").mkdir()
    _audit(workspace, _records(("delete", "somedir")))
    assert _paths(_summary(workspace)) == []


# --------------------------------------------------------------------------
# 相邻的形状：本批不改它们
# --------------------------------------------------------------------------

def test_a_move_source_is_not_answered_a_deletion(tmp_path: Path) -> None:
    """移动的内容还在（换了名字）——第五百四十二批给的是目标那一头，源另说。"""
    workspace = _workspace(tmp_path, "move")
    Editor(workspace, audit_path=workspace / ".minicc" / "audit.jsonl").move(
        "notes.md", "out/renamed.md"
    )
    assert _paths(_summary(workspace)) == ["out/renamed.md"]


def test_a_backup_line_claims_no_deletion(tmp_path: Path) -> None:
    """`backup` 也写 `→ 名字` 也带 digest，但它不删任何东西（M8-T313）。"""
    workspace = _workspace(tmp_path, "backup")
    (workspace / "notes.md").unlink()
    _audit(
        workspace,
        [{"action": "backup", "path": "notes.md", "detail": "→ notes.md.2026", "before_digest": DIGEST}],
    )
    assert _paths(_summary(workspace)) == []


def test_an_absent_trail_claims_no_deletion(tmp_path: Path) -> None:
    """没有轨迹就是没有轨迹：一条删除也不许报（第五百三十四批那条理由也别惊动）。"""
    workspace = _workspace(tmp_path, "no-trail")
    (workspace / "notes.md").unlink()
    summary = _summary(workspace)
    assert _paths(summary) == [], summary
    assert summary["audit_read_error"] is None, summary


# --------------------------------------------------------------------------
# 家规
# --------------------------------------------------------------------------

def test_the_witness_is_read_through_one_home(tmp_path: Path) -> None:
    """「这一行删掉过什么内容」的读法只有一个家，面板不能自己拼一份。"""
    root = Path(__file__).resolve().parents[1] / "minicc"
    sources = {
        path.name: path.read_text(encoding="utf-8") for path in sorted(root.rglob("*.py"))
    }
    owners = [name for name, text in sources.items() if "def deletion_witness(" in text]
    assert owners == ["editor.py"], owners
    changes = sources["changes.py"]
    assert "deletion_witness(" in changes, "面板没有问那个家"
    assert '"before_digest"' not in changes, "面板自己复制了字段名"


def test_the_editor_writes_the_witness_this_batch_reads(tmp_path: Path) -> None:
    """家和写这行的是同一份账：编辑器删之前 digest 过内容，那个字段就在行里。"""
    from minicc.tools.editor import deletion_witness

    workspace = _workspace(tmp_path, "written-trail")
    _delete(workspace, "notes.md")
    lines = (workspace / ".minicc" / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[-1])
    assert record["action"] == "delete", record
    assert deletion_witness(record), "编辑器写的证人，读法读不出来"
    without = dict(record)
    del without["before_digest"]
    assert deletion_witness(without) == "", "读法没有落在字段上"
    assert deletion_witness(record["before_digest"]) == "", "读法要的是那条记录"
