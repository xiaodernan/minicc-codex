"""M8-T562（第五百四十四批）：审计说文件没了，备份里那份内容还没人读。

第五百四十三批让面板说出「这个文件被删掉了」，但它说不出**删掉了什么**：
`diff` 的 `before` 只问 HEAD（`minicc/changes.py:564` 的 `_baseline`），
`after` 对一个不在的文件答 `""`（`minicc/changes.py:569` 的 `_text`），于是
`additions`/`deletions` 双双为 0、补丁 0 字节——探针 probe_562 实测 E1/E10：
`deleted` 一格 `patch_len=0`。

内容并没有丢。`Editor.delete` 在 `unlink` 之前先 `_backup(target)`
（`minicc/tools/editor.py:838`），那条 `backup` 行把副本的名字写进 `detail`
（`:474-479`，`→ {name}`）、把副本内容的 digest 写进 `before_digest`——
和紧随其后的 `delete` 行是同一个值。副本就躺在 `.minicc/backup/` 里
（`minicc/tools/editor.py:287` 的 `backup_directory`），面板从来不去看那一格。

探针实测的形状：

  E1  无仓库真跑 delete，问 diff        -> 补丁 0 字节（副本就在，digest 也对得上）
  E2  先 edit 再 delete，两条 backup    -> 只有 digest 相等的那一份是预像
  E3  副本被裁剪掉（行还在、文件不在）  -> 现在同样答 0 字节，与「从来没记过」同词
  E4  副本后来被改写                     -> 认名字不认内容，会把别人的内容当预像
  E5  副本是二进制                       -> `_text` 那一条读法答 ""，又坍缩成「没有内容」
  E6  对照：git 看得见这条删除           -> 补丁本来就有 71 字节，本批不抢
  E7  净零（窗口里 create 后 delete）    -> 根本不该有预像
  E8  detail 的名字走到 backup 目录之外  -> 配对不许离开那一格
  E9  digest 不是字符串                  -> 与本批同一道闸门（第五百四十三批已拒）
  E11 同一个 digest 提名两份副本         -> 只有一份的字节真能 digest 成它
  E12 对得上 digest 的行是**别的路径**的  -> 配对按路径，不按 digest 全局找
  E13 backup 行写在 delete 行之后         -> 窗口顺序不是一句承诺
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
        ["git", "config", "user.email", "t562@example.com"],
        ["git", "config", "user.name", "t562"],
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


def _editor(workspace: Path) -> Editor:
    return Editor(workspace, audit_path=workspace / ".minicc" / "audit.jsonl")


def _backup_dir(workspace: Path) -> Path:
    return workspace / ".minicc" / "backup"


def _diff(workspace: Path, path: str) -> dict:
    return ChangeInspector(workspace).diff(path)


def _preimage(workspace: Path, path: str) -> str:
    return str(_diff(workspace, path).get("deletion_preimage") or "")


def _copies(workspace: Path) -> list[str]:
    directory = _backup_dir(workspace)
    return sorted(p.name for p in directory.iterdir()) if directory.is_dir() else []


# --------------------------------------------------------------------------
# 读得出来的那一路
# --------------------------------------------------------------------------

def test_a_witnessed_deletion_shows_the_content_the_copy_kept(tmp_path: Path) -> None:
    """删除确有其事、副本就在隔壁一格——补丁该把它说出来。"""
    workspace = _workspace(tmp_path, "E1")
    _editor(workspace).delete("notes.md")
    diff = _diff(workspace, "notes.md")
    assert diff["status"] == "deleted", diff
    assert diff["deletions"] == 2, diff
    assert "-hello world" in diff["patch"], diff
    assert "-second line" in diff["patch"], diff
    assert diff["deletion_preimage"] == "copy", diff


def test_the_pair_is_made_by_the_digest_not_by_the_newest_line(tmp_path: Path) -> None:
    """同一文件先后两份副本：预像是 digest 对得上那一份，不是最后写的那条。"""
    workspace = _workspace(tmp_path, "E2")
    editor = _editor(workspace)
    editor.write_file("notes.md", "changed once\n")
    editor.delete("notes.md")
    assert len(_copies(workspace)) == 2, _copies(workspace)
    diff = _diff(workspace, "notes.md")
    assert diff["deletion_preimage"] == "copy", diff
    assert "-changed once" in diff["patch"], diff
    assert "hello world" not in diff["patch"], diff


def test_only_the_copy_that_digests_to_the_witness_is_believed(tmp_path: Path) -> None:
    """两条 backup 行报同一个 digest，其中一份的字节并不是它——只认真能 digest 成它的那份。"""
    workspace = _workspace(tmp_path, "E11")
    editor = _editor(workspace)
    editor.delete("notes.md")
    real = _copies(workspace)[0]
    witness = json.loads(
        (workspace / ".minicc" / "audit.jsonl").read_text(encoding="utf-8").splitlines()[1]
    )["before_digest"]
    (_backup_dir(workspace) / "impostor.md").write_text("impostor copy\n", encoding="utf-8")
    _audit(workspace, [
        {"action": "backup", "path": "notes.md", "detail": f"→ {real}", "before_digest": witness},
        {"action": "backup", "path": "notes.md", "detail": "→ impostor.md", "before_digest": witness},
        {"action": "delete", "path": "notes.md", "detail": "", "before_digest": witness},
    ])
    diff = _diff(workspace, "notes.md")
    assert diff["deletion_preimage"] == "copy", diff
    assert "impostor copy" not in diff["patch"], diff
    assert "-hello world" in diff["patch"], diff


def test_a_backup_line_written_after_the_delete_line_still_pairs(tmp_path: Path) -> None:
    """窗口里的顺序不是一句承诺：名字写在后面也还是那一份。"""
    workspace = _workspace(tmp_path, "E13")
    editor = _editor(workspace)
    editor.delete("notes.md")
    real = _copies(workspace)[0]
    witness = json.loads(
        (workspace / ".minicc" / "audit.jsonl").read_text(encoding="utf-8").splitlines()[1]
    )["before_digest"]
    _audit(workspace, [
        {"action": "delete", "path": "notes.md", "detail": "", "before_digest": witness},
        {"action": "backup", "path": "notes.md", "detail": f"→ {real}", "before_digest": witness},
    ])
    diff = _diff(workspace, "notes.md")
    assert diff["deletion_preimage"] == "copy", diff
    assert "-hello world" in diff["patch"], diff


def test_the_last_witnessed_deletion_is_the_one_answered(tmp_path: Path) -> None:
    """同一个路径删过两次：答的是最后一次删掉的那份内容。"""
    workspace = _workspace(tmp_path, "twice")
    editor = _editor(workspace)
    editor.delete("notes.md")
    editor.write_file("notes.md", "second life\n")
    editor.delete("notes.md")
    diff = _diff(workspace, "notes.md")
    assert diff["status"] == "deleted", diff
    assert diff["deletion_preimage"] == "copy", diff
    assert "-second life" in diff["patch"], diff
    assert "hello world" not in diff["patch"], diff


def test_the_recovered_patch_is_still_redacted(tmp_path: Path) -> None:
    """读回来的是磁盘上的字节，脱敏那一步不能因为换了出处就跳过。

    值写成 16 个字符：`redact_text` 的 `sk-` 规则要 8 个以上（:121），本仓库
    的提交前钩子把 20 个以上的这一形当疑似密钥拦下——这一格要钉的是「脱敏
    还走不走」，不是「能不能把一段真钥形状的字串提交进去」。
    """
    workspace = _workspace(tmp_path, "secret", {"token.txt": "sk-abcdefgh12345678\n"})
    _editor(workspace).delete("token.txt")
    diff = _diff(workspace, "token.txt")
    assert diff["patch"], diff  # 内容确实从副本里读了回来
    assert "sk-abcdefgh12345678" not in diff["patch"], diff


# --------------------------------------------------------------------------
# 读不出来的那一路：三种说法是三种事实
# --------------------------------------------------------------------------

def test_a_pruned_copy_is_answered_as_not_readable(tmp_path: Path) -> None:
    """行里点名了副本，副本已经被裁剪掉——这跟「从来没记过」不是一回事。"""
    workspace = _workspace(tmp_path, "E3")
    editor = _editor(workspace)
    editor.delete("notes.md")
    for copy in _backup_dir(workspace).iterdir():
        copy.unlink()
    diff = _diff(workspace, "notes.md")
    assert diff["deletion_preimage"] == "not-readable", diff
    assert diff["patch"] == "", diff


def test_a_missing_backup_directory_is_answered_as_not_recorded(tmp_path: Path) -> None:
    """轨迹说删过，可没有任何一行说过副本——这才是「没记过」。"""
    workspace = _workspace(tmp_path, "no-copy")
    _audit(workspace, [{"action": "delete", "path": "notes.md", "detail": "", "before_digest": DIGEST}])
    (workspace / "notes.md").unlink()
    diff = _diff(workspace, "notes.md")
    assert diff["deletion_preimage"] == "not-recorded", diff
    assert not _backup_dir(workspace).exists(), _copies(workspace)


def test_a_binary_copy_is_answered_as_not_readable(tmp_path: Path) -> None:
    """副本读得出来但不是文本：说「这份内容显示不出来」，不说「里面没东西」。"""
    from minicc.tools.editor import sha256_digest

    workspace = _workspace(tmp_path, "E5")
    _editor(workspace).delete("notes.md")
    copy = _copies(workspace)[0]
    body = b"\xff\xfe\x00binary\x00\n"
    (_backup_dir(workspace) / copy).write_bytes(body)
    digest = sha256_digest(body)
    _audit(workspace, [
        {"action": "backup", "path": "notes.md", "detail": f"→ {copy}", "before_digest": digest},
        {"action": "delete", "path": "notes.md", "detail": "", "before_digest": digest},
    ])
    assert _diff(workspace, "notes.md")["deletion_preimage"] == "not-readable", copy


def test_a_copy_whose_bytes_are_not_the_witness_says_so(tmp_path: Path) -> None:
    """副本被后来的人改写过：按名字读它会答出一份并不属于这次删除的内容。"""
    workspace = _workspace(tmp_path, "E4")
    editor = _editor(workspace)
    editor.delete("notes.md")
    copy = _copies(workspace)[0]
    (_backup_dir(workspace) / copy).write_text("somebody overwrote this\n", encoding="utf-8")
    diff = _diff(workspace, "notes.md")
    assert diff["deletion_preimage"] == "digest-mismatch", diff
    assert "somebody overwrote" not in diff["patch"], diff


def test_a_name_that_leaves_the_backup_directory_is_not_read(tmp_path: Path) -> None:
    """detail 写的是 `→ ../secret.md`：配对不许走出那一格。

    这一格**必须**让窗外那份文件真的读得到——否则「地址闸门掉了」也只会因为
    「找不到文件」而红不起来（第五百四十四批臂 C9 第一次就是这个形状：
    `rc=0`）。所以窗外那份就摆在 `.minicc/` 里，digest 也按它写：掉了闸门
    面板就会读它，并把一份轨迹从没说它复制过的内容当成预像。
    """
    from minicc.tools.editor import sha256_digest

    workspace = _workspace(tmp_path, "E8")
    body = b"a file the trail never said it copied\n"
    (workspace / ".minicc").mkdir(parents=True, exist_ok=True)
    (workspace / ".minicc" / "secret.md").write_bytes(body)
    digest = sha256_digest(body)
    _audit(workspace, [
        {"action": "backup", "path": "notes.md", "detail": "→ ../secret.md", "before_digest": digest},
        {"action": "delete", "path": "notes.md", "detail": "", "before_digest": digest},
    ])
    (workspace / "notes.md").unlink()
    diff = _diff(workspace, "notes.md")
    assert diff["deletion_preimage"] == "not-readable", diff
    assert "never said it copied" not in diff["patch"], diff
    assert diff["patch"] == "", diff


def test_a_copy_recorded_for_another_path_is_not_read(tmp_path: Path) -> None:
    """digest 相同、路径不同：配对按路径查，不拿别条路径的副本顶上去。"""
    workspace = _workspace(tmp_path, "E12", {"keep.txt": "stay\n", "other.md": "stay\n"})
    _audit(workspace, [
        {"action": "backup", "path": "other.md", "detail": "→ other.md.2026.x", "before_digest": DIGEST},
        {"action": "delete", "path": "keep.txt", "detail": "", "before_digest": DIGEST},
    ])
    (workspace / "keep.txt").unlink()
    diff = _diff(workspace, "keep.txt")
    assert diff["deletion_preimage"] == "not-recorded", diff


def test_a_refused_backup_line_names_no_copy(tmp_path: Path) -> None:
    """拒绝的 backup 行拼不出副本名（写出它的只有 `_backup`，而它在复制成功之后才落一行）。"""
    workspace = _workspace(tmp_path, "refused")
    editor = _editor(workspace)
    editor.delete("notes.md")
    copy = _copies(workspace)[0]
    digest = json.loads(
        (workspace / ".minicc" / "audit.jsonl").read_text(encoding="utf-8").splitlines()[1]
    )["before_digest"]
    _audit(workspace, [
        {"action": "backup", "path": "notes.md", "detail": "拒绝: 目标已存在", "before_digest": digest},
        {"action": "delete", "path": "notes.md", "detail": "", "before_digest": digest},
    ])
    assert _diff(workspace, "notes.md")["deletion_preimage"] == "not-recorded", _copies(workspace)
    _audit(workspace, [
        {"action": "backup", "path": "notes.md", "detail": "拒绝: 目标已存在", "before_digest": digest},
        {"action": "backup", "path": "notes.md", "detail": f"→ {copy}", "before_digest": digest},
        {"action": "delete", "path": "notes.md", "detail": "", "before_digest": digest},
    ])
    diff = _diff(workspace, "notes.md")
    assert diff["deletion_preimage"] == "copy", _copies(workspace)
    assert "-hello world" in diff["patch"], diff


# --------------------------------------------------------------------------
# 不该开口的形状（对照）
# --------------------------------------------------------------------------

def test_a_git_visible_deletion_keeps_its_own_patch(tmp_path: Path) -> None:
    """git 说得出这条删除和它的内容：本批不去抢它的答案。"""
    workspace = _repo(_workspace(tmp_path, "E6"))
    _editor(workspace).delete("notes.md")
    diff = _diff(workspace, "notes.md")
    assert diff["status"] == "deleted", diff
    assert diff["deletions"] == 2, diff
    assert _preimage(workspace, "notes.md") == "", diff


def test_a_net_zero_window_has_no_preimage_to_read(tmp_path: Path) -> None:
    """窗口里生又死：路径根本不进清单，也就没有预像可问。"""
    workspace = _workspace(tmp_path, "E7", {"temp.md": "made\n"})
    _audit(workspace, [
        {"action": "backup", "path": "temp.md", "detail": "→ temp.md.2026.a", "before_digest": DIGEST},
        {"action": "create", "path": "temp.md", "detail": "5 chars"},
        {"action": "delete", "path": "temp.md", "detail": "", "before_digest": DIGEST},
    ])
    (workspace / "temp.md").unlink()
    summary = ChangeInspector(workspace).summary()
    assert summary["total_files"] == 0, summary
    assert _preimage(workspace, "temp.md") == "", _diff(workspace, "temp.md")


def test_a_non_string_digest_is_still_not_a_witness(tmp_path: Path) -> None:
    """digest 不是字符串就配不成一对——第五百四十一批那道闸门在本批同样拦住。"""
    workspace = _workspace(tmp_path, "E9")
    _audit(workspace, [
        {"action": "backup", "path": "notes.md", "detail": "→ notes.md.2026.b", "before_digest": 123},
        {"action": "delete", "path": "notes.md", "detail": "", "before_digest": 123},
    ])
    (workspace / "notes.md").unlink()
    directory = _backup_dir(workspace)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "notes.md.2026.b").write_text("coerced witness content\n", encoding="utf-8")
    summary = ChangeInspector(workspace).summary()
    assert summary["total_files"] == 0, summary
    assert "coerced witness content" not in _diff(workspace, "notes.md")["patch"], summary


def test_a_file_that_came_back_is_not_answered_a_deletion(tmp_path: Path) -> None:
    """树说它还在：这一路不该读任何副本，也不该有预像。"""
    workspace = _workspace(tmp_path, "back")
    _audit(workspace, [
        {"action": "backup", "path": "notes.md", "detail": "→ notes.md.2026.c", "before_digest": DIGEST},
        {"action": "delete", "path": "notes.md", "detail": "", "before_digest": DIGEST},
    ])
    diff = _diff(workspace, "notes.md")
    assert diff["status"] == "modified", diff
    assert _preimage(workspace, "notes.md") == "", diff


def test_every_diff_carries_the_verdict(tmp_path: Path) -> None:
    """预像这一格是详情页的答案之一：每一次 `diff` 都答得出它，包括没删过谁的路径。"""
    workspace = _workspace(tmp_path, "shape")
    editor = _editor(workspace)
    editor.write_file("notes.md", "changed\n")
    editor.delete("keep.txt")
    inspector = ChangeInspector(workspace)
    for path in ("notes.md", "keep.txt", "never-seen.md"):
        assert "deletion_preimage" in inspector.diff(path), path


def test_the_list_still_says_no_numbers(tmp_path: Path) -> None:
    """数不出来的那一路，清单仍是 0/0——第五百四十五批对齐的是读得出来的那条。

    本批写下这一条时它钉的是「清单不跟着补丁走」；那件事现在成立了，名字留下
    （本批的 §2、§4、§6 都按这个名字引用过它），形状换成**真正数不出来**的一种：
    delete 行有 witness，窗口里没有配得上它的 backup 行。
    """
    from minicc.tools.editor import sha256_digest

    workspace = _workspace(tmp_path, "E10")
    digest = sha256_digest(FILES["notes.md"].encode("utf-8"))
    _audit(workspace, [
        {"action": "delete", "path": "notes.md", "detail": "", "before_digest": digest},
    ])
    (workspace / "notes.md").unlink()
    entry = ChangeInspector(workspace).summary()["files"][0]
    assert (entry["status"], entry["raw"], entry["additions"], entry["deletions"]) == (
        "deleted", "audit", 0, 0
    ), entry
    diff = _diff(workspace, "notes.md")
    assert diff["deletions"] == 0, diff
    assert diff["deletion_preimage"] == "not-recorded", diff


# --------------------------------------------------------------------------
# 家规：一件事一个家
# --------------------------------------------------------------------------

def test_the_backup_directory_has_one_spelling(tmp_path: Path) -> None:
    """.minicc/backup 这一格的名字只许拼一次——面板问路，不自己造地址。"""
    import inspect

    from minicc import changes as changes_module
    from minicc.tools import editor as editor_module
    from minicc.tools.editor import backup_directory

    editor = _editor(tmp_path / "one-spelling")
    changes_source = inspect.getsource(changes_module)
    assert editor.backup_dir == backup_directory(editor.workspace)
    assert inspect.getsource(editor_module).count('".minicc" / "backup"') == 1
    assert '".minicc" / "backup"' not in changes_source, "面板自己造了副本的地址"
    assert "backup_copy_path(" in changes_source, "面板没有向编辑器问路"


def test_the_arrow_form_is_read_through_one_home(tmp_path: Path) -> None:
    """`→ 名字` 的拼法由编辑器读；面板不自己拆箭头。"""
    import inspect

    from minicc import changes as changes_module

    source = inspect.getsource(changes_module)
    assert "→" not in source, "面板自己拆了箭头"
    assert "DETAIL_TARGET_PREFIX" not in source, "面板自己拼了前缀"
    from minicc.tools import editor as editor_module

    editor_source = inspect.getsource(editor_module)
    assert editor_source.count("DETAIL_TARGET_PREFIX.strip()") == 1, editor_source.count(
        "DETAIL_TARGET_PREFIX.strip()"
    )


def test_the_copy_is_verified_before_it_is_believed(tmp_path: Path) -> None:
    """认 digest 这一步在面板里只有一个出处：读副本、算 digest、比见证。"""
    import inspect

    from minicc import changes as changes_module
    from minicc.tools import editor as editor_module

    changes_source = inspect.getsource(changes_module)
    assert changes_source.count("sha256_digest(") == 1, changes_source.count("sha256_digest(")
    editor_source = inspect.getsource(editor_module)
    assert "def sha256_digest(" in editor_source
