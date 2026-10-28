"""行为级栅栏：minicc.changes 的纯逻辑契约（不 shell-out 到 git）。

`changes.py` 的多数方法要跑 git，但有几段纯逻辑长期零单测、且是安全/正确性边界：

- ``_ignored_path``：变更审计对 `.git`/`.venv`/`node_modules` 等路径的忽略判定，
  含 `./` 与 `/` 前导归一、前缀匹配。
- ``_parse_status``：git status 两字符码的 status 归类（无 `self`，类级可调）。
- ``_text``：文件读取的二进制/空字节/不存在兜底（静态方法）。
- ``_resolve``：进入变更检视前的路径安全闸门（空/绝对/越界路径必抛 ChangeError）。

全部用仓库外的临时目录（tempfile.mkdtemp），不碰仓库、不触发 git 删除护栏。
直接调用：`python tests/test_changes_pure.py`。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from minicc.changes import ChangeError, ChangeInspector, _ignored_path


# --------------------------------------------------------------------------
# _ignored_path
# --------------------------------------------------------------------------

def test_ignored_exact_dot_dirs():
    assert _ignored_path(".git") is True
    assert _ignored_path(".minicc") is True


def test_ignored_prefixes():
    assert _ignored_path(".git/config") is True
    assert _ignored_path("node_modules/x.js") is True
    assert _ignored_path("__pycache__/m.pyc") is True
    assert _ignored_path(".venv/lib/x") is True
    assert _ignored_path("output/log.txt") is True
    assert _ignored_path(".pytest_cache/x") is True
    assert _ignored_path("minicc.egg-info/x") is True


def test_not_ignored_source_paths():
    assert _ignored_path("src/main.py") is False
    assert _ignored_path("README.md") is False


def test_ignored_normalizes_leading_slash_and_dot():
    assert _ignored_path("./.git") is True
    assert _ignored_path("/.git") is True
    assert _ignored_path("./node_modules/x") is True


def test_ignored_does_not_match_embedded_prefix():
    # ".git" only counts at the path root after normalization.
    assert _ignored_path("src/.git/x") is False
    assert _ignored_path("a/.minicc/x") is False


# --------------------------------------------------------------------------
# _parse_status (class-level function, no self)
# --------------------------------------------------------------------------

def test_parse_status_added_untracked():
    assert ChangeInspector._parse_status("?? file.py") == ("added", "file.py")


def test_parse_status_added_staged():
    assert ChangeInspector._parse_status("A  file.py") == ("added", "file.py")


def test_parse_status_deleted():
    assert ChangeInspector._parse_status("D  file.py") == ("deleted", "file.py")


def test_parse_status_renamed_keeps_full_path_token():
    assert ChangeInspector._parse_status("R  a.py -> b.py") == ("renamed", "a.py -> b.py")


def test_parse_status_modified_default():
    assert ChangeInspector._parse_status("M  file.py") == ("modified", "file.py")
    assert ChangeInspector._parse_status("MM file.py") == ("modified", "file.py")


def test_parse_status_short_or_empty_raw_is_safe():
    # Slices beyond the string length return "" and never raise.
    assert ChangeInspector._parse_status("A") == ("added", "")
    assert ChangeInspector._parse_status("  ") == ("modified", "")


# --------------------------------------------------------------------------
# _text (staticmethod)
# --------------------------------------------------------------------------

def _temp_file(content: str, *, binary: bool = False, name: str = "f.txt") -> Path:
    base = Path(tempfile.mkdtemp(prefix="minicc_changes_"))
    path = base / name
    if binary:
        path.write_bytes(content.encode("utf-8", errors="surrogateescape"))
    else:
        path.write_text(content, encoding="utf-8")
    return path


def test_text_reads_plain_file():
    p = _temp_file("hello\nworld\n")
    assert ChangeInspector._text(p) == "hello\nworld\n"


def test_text_missing_file_is_empty():
    missing = Path(tempfile.mkdtemp(prefix="minicc_changes_")) / "nope.txt"
    assert ChangeInspector._text(missing) == ""


def test_text_null_byte_file_is_empty():
    p = _temp_file("ab\x00cd")
    assert ChangeInspector._text(p) == ""


def test_text_binary_file_is_empty():
    # Invalid UTF-8 decoded as replacement chars still contains a NUL-ish byte?
    # read_text raises UnicodeDecodeError -> _text returns "".
    p = _temp_file("\xff\xfe\x00binary", binary=True)
    assert ChangeInspector._text(p) == ""


# --------------------------------------------------------------------------
# _resolve (path safety gate before inspection)
# --------------------------------------------------------------------------

def _inspector_in_temp() -> tuple[ChangeInspector, Path]:
    # `.resolve()` is load-bearing on Windows, not cosmetic. `tempfile.mkdtemp`
    # hands back the 8.3 short form of the runner's temp dir (`RUNNER~1`), while
    # `ChangeInspector.__init__` stores `Path(workspace).resolve()` - the long form
    # (`runneradmin`). Comparing the two spelled differently makes
    # `is_relative_to` return False on a path that is in fact inside the workspace,
    # which is exactly how this file failed on windows-latest while staying green
    # on ubuntu. Resolve at the source so both sides use one spelling.
    ws = Path(tempfile.mkdtemp(prefix="minicc_ws_")).resolve()
    return ChangeInspector(ws), ws


def test_resolve_rejects_empty_path():
    insp, _ = _inspector_in_temp()
    with pytest.raises(ChangeError):
        insp._resolve("")
    with pytest.raises(ChangeError):
        insp._resolve("   ")


def test_resolve_rejects_absolute_path():
    insp, _ = _inspector_in_temp()
    with pytest.raises(ChangeError):
        insp._resolve("/etc/passwd")


def test_resolve_rejects_path_escaping_workspace():
    insp, _ = _inspector_in_temp()
    with pytest.raises(ChangeError):
        insp._resolve("../escape")


def test_resolve_accepts_relative_path_inside_workspace():
    insp, ws = _inspector_in_temp()
    # Pin the fixture to the inspector's own spelling first: if these ever diverge
    # (the Windows 8.3 short-name split this file shipped with), the claim below
    # would fail for the wrong reason - a path that really is inside the workspace.
    assert ws == insp.workspace, (
        f"fixture workspace {ws} is not the inspector's {insp.workspace}"
    )
    resolved = insp._resolve("src/main.py")
    assert resolved.is_relative_to(insp.workspace)
    assert resolved.as_posix().endswith("src/main.py")


@pytest.mark.parametrize("status", ["modified", "deleted", "renamed"])
def test_diff_refuses_an_unreadable_tracked_baseline(tmp_path, monkeypatch, status):
    target = tmp_path / "notes.txt"
    if status != "deleted":
        target.write_text("one\ntwo\n", encoding="utf-8")
    inspector = ChangeInspector(tmp_path)
    monkeypatch.setattr(inspector, "files_without_diff", lambda: [
        {"path": "notes.txt", "status": status, "raw": " M notes.txt"},
    ])

    def git(args):
        if args[0] == "show":
            return 128, "", "fatal: unable to read object"
        if args[0] == "ls-tree":
            return 0, "100644 blob " + "a" * 40 + "\tnotes.txt\0", ""
        if args[0] == "rev-parse":
            return 0, "b" * 40 + "\n", ""
        raise AssertionError(args)

    monkeypatch.setattr(inspector, "_git", git)
    with pytest.raises(ChangeError, match="Git.*notes.txt"):
        inspector.diff("notes.txt")


@pytest.mark.parametrize("code, error", [
    (127, "git unavailable"),
    (128, "fatal: bad config file"),
    (128, "fatal: detected dubious ownership in repository"),
    (128, "fatal: not a git repository: /missing/gitdir"),
])
def test_diff_refuses_git_failure_instead_of_inventing_additions(tmp_path, monkeypatch, code, error):
    (tmp_path / "notes.txt").write_text("one\ntwo\n", encoding="utf-8")
    inspector = ChangeInspector(tmp_path)
    monkeypatch.setattr(inspector, "files_without_diff", lambda: [
        {"path": "notes.txt", "status": "modified", "raw": "audit"},
    ])
    monkeypatch.setattr(inspector, "_git", lambda args: (code, "", error))
    with pytest.raises(ChangeError, match="Git.*notes.txt"):
        inspector.diff("notes.txt")


@pytest.mark.parametrize("baseline_kind", ["absent-path", "unborn", "non-repository"])
def test_diff_accepts_an_established_empty_baseline(tmp_path, monkeypatch, baseline_kind):
    (tmp_path / "notes.txt").write_text("one\ntwo\n", encoding="utf-8")
    inspector = ChangeInspector(tmp_path)
    monkeypatch.setattr(inspector, "files_without_diff", lambda: [
        {"path": "notes.txt", "status": "modified", "raw": "audit"},
    ])

    def git(args):
        if baseline_kind == "non-repository":
            return 128, "", "fatal: not a git repository (or any of the parent directories): .git"
        if args[0] == "show":
            return 128, "", "fatal: invalid object name 'HEAD'"
        if args[0] == "ls-tree":
            return (0, "", "") if baseline_kind == "absent-path" else (128, "", "fatal: Not a valid object name HEAD")
        if args[0] == "rev-parse":
            return 1, "", ""
        if args[0] == "symbolic-ref":
            return 0, "refs/heads/main\n", ""
        if args[0] == "show-ref":
            return 1, "", ""
        raise AssertionError(args)

    monkeypatch.setattr(inspector, "_git", git)
    result = inspector.diff("notes.txt")
    assert result["status"] == "modified"
    assert result["additions"] == 2
    assert result["deletions"] == 0
    assert "+one\n+two" in result["patch"]


@pytest.fixture
def nested_git_workspace(tmp_path):
    import subprocess

    workspace = tmp_path / "模块 workspace"
    workspace.mkdir()

    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=tmp_path, check=True, capture_output=True,
            text=True, encoding="utf-8", errors="replace",
        ).stdout.strip()

    git("init")
    (tmp_path / "notes.txt").write_text("ROOT_BASELINE\n", encoding="utf-8")
    (workspace / "notes.txt").write_text("NESTED_BASELINE\n", encoding="utf-8")
    git("add", "notes.txt", f"{workspace.name}/notes.txt")
    tree = git("write-tree")
    commit = git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit-tree", tree, "-m", "fixture")
    git("update-ref", "HEAD", commit)
    return tmp_path, workspace, git


def test_nested_workspace_uses_its_own_status_counts_and_baseline(nested_git_workspace):
    root, workspace, git = nested_git_workspace
    (root / "notes.txt").write_text("ROOT_CHANGED\nextra root line\n", encoding="utf-8")
    (workspace / "notes.txt").write_text("NESTED_CHANGED\n", encoding="utf-8")
    inspector = ChangeInspector(workspace)
    summary = inspector.summary()
    assert [item["path"] for item in summary["files"]] == ["notes.txt"], summary
    assert (summary["total_files"], summary["additions"], summary["deletions"]) == (1, 1, 1)
    diff = inspector.diff("notes.txt")
    assert diff["status"] == "modified"
    assert "-NESTED_BASELINE\n+NESTED_CHANGED" in diff["patch"]
    assert "ROOT_" not in diff["patch"]


def test_nested_workspace_ignores_changes_outside_its_root(nested_git_workspace):
    root, workspace, git = nested_git_workspace
    (root / "notes.txt").write_text("ROOT_CHANGED\n", encoding="utf-8")
    inspector = ChangeInspector(workspace)
    assert inspector.summary()["total_files"] == 0
    diff = inspector.diff("notes.txt")
    assert diff["status"] == "clean" and diff["patch"] == ""


@pytest.mark.parametrize("direction", ["within", "incoming", "outgoing"])
def test_nested_workspace_renames_stay_inside_the_selected_root(nested_git_workspace, direction):
    root, workspace, git = nested_git_workspace
    folder = workspace.name
    source = "notes.txt" if direction == "incoming" else f"{folder}/notes.txt"
    destination = "outside.txt" if direction == "outgoing" else f"{folder}/renamed.txt"
    git("mv", source, destination)
    inspector = ChangeInspector(workspace)
    expected_path = "notes.txt" if direction == "outgoing" else "renamed.txt"
    summary = inspector.summary()
    assert [item["path"] for item in summary["files"]] == [expected_path], summary
    diff = inspector.diff(expected_path)
    if direction == "within":
        assert diff["status"] == "renamed" and diff["patch"] == ""
        assert (summary["additions"], summary["deletions"]) == (0, 0)
    elif direction == "incoming":
        assert diff["status"] == "added" and "+ROOT_BASELINE" in diff["patch"]
        assert (summary["additions"], summary["deletions"]) == (1, 0)
    else:
        assert diff["status"] == "deleted" and "-NESTED_BASELINE" in diff["patch"]
        assert (summary["additions"], summary["deletions"]) == (0, 1)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q", "-W", "error"]))
