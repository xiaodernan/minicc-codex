"""M8-T572（第五百五十四批）：内容没变的构建不该改写文件。

`writeIfNeeded` 的写分支无条件 `writeFileSync`：在 CRLF 检出上，一次
`node scripts/build-web.mjs` 把六份产物全部改写成 LF。内容一个字节没变
（T571 修好的 `--check` 说「全部最新」），可 `git status` 说六份 ` M`，
`git diff` 说没有内容差异——同一棵树，两把尺子两个答案。
`scratch/probe572.py` 量到：构建后六份 crlf=0，status 6 行、numstat 0 行。

修法：写分支与检查分支用同一个判据——归一化行尾后相等就不写。
本门的行为格在临时副本里跑发出去的 `scripts/build-web.mjs`；node 或 esbuild
不在时 skip。
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "build-web.mjs"
NODE = shutil.which("node")
GIT = shutil.which("git")
ESBUILD = REPO / "node_modules" / "esbuild"
PLATFORM = REPO / "node_modules" / "@esbuild"

needs_node = pytest.mark.skipif(
    NODE is None or not ESBUILD.is_dir() or not PLATFORM.is_dir(),
    reason="node or esbuild is not installed",
)
needs_git = pytest.mark.skipif(GIT is None, reason="git is not on PATH")


def _copy_workbench(tmp_path: Path) -> Path:
    root = tmp_path / "checkout"
    shutil.copytree(REPO / "web", root / "web")
    (root / "scripts").mkdir()
    shutil.copy2(SCRIPT, root / "scripts" / "build-web.mjs")
    (root / "node_modules").mkdir()
    shutil.copytree(ESBUILD, root / "node_modules" / "esbuild")
    shutil.copytree(PLATFORM, root / "node_modules" / "@esbuild")
    return root


def _artifacts(root: Path) -> list[Path]:
    manifest = json.loads((root / "web" / "asset-manifest.json").read_text(encoding="utf-8"))
    names = ["web/app.js", "web/game.js", "web/asset-manifest.json"]
    names += [f"web/{value.lstrip('/')}" for value in manifest.values()]
    return [root / name for name in names]


def _to_crlf(path: Path) -> None:
    body = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    path.write_bytes(body)


def _to_lf(path: Path) -> None:
    path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))


def _build(root: Path, check: bool = False) -> subprocess.CompletedProcess:
    argv = [NODE, str(root / "scripts" / "build-web.mjs")]
    if check:
        argv.append("--check")
    return subprocess.run(
        argv, cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


def _output(proc: subprocess.CompletedProcess) -> str:
    return (proc.stdout or "") + (proc.stderr or "")


@needs_node
def test_a_crlf_checkout_is_byte_identical_after_a_build(tmp_path: Path) -> None:
    root = _copy_workbench(tmp_path)
    files = _artifacts(root)
    for path in files:
        _to_crlf(path)
    before = {path: path.read_bytes() for path in files}
    proc = _build(root)
    assert proc.returncode == 0, _output(proc)
    for path in files:
        assert path.read_bytes() == before[path], (
            f"{path.relative_to(root)} was rewritten by a build whose output is unchanged"
        )


def _worktree_clean(porcelain: str) -> bool:
    # 第一列是索引 vs HEAD（临时仓库里全是 `A`），第二列才是工作树 vs 索引。
    return all(len(line) > 1 and line[1] == " " for line in porcelain.splitlines())


@needs_node
@needs_git
def test_a_build_does_not_dirty_a_clean_checkout(tmp_path: Path) -> None:
    root = _copy_workbench(tmp_path)
    git = [GIT, "-C", str(root)]
    subprocess.run([*git, "init", "-q"], check=True, capture_output=True)
    subprocess.run([*git, "config", "core.autocrlf", "true"], check=True, capture_output=True)
    subprocess.run([*git, "add", "web"], check=True, capture_output=True)
    start = subprocess.run([*git, "status", "--porcelain", "--", "web"], capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
    assert _worktree_clean(start.stdout), start.stdout
    proc = _build(root)
    assert proc.returncode == 0, _output(proc)
    status = subprocess.run([*git, "status", "--porcelain", "--", "web"], capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    assert _worktree_clean(status.stdout), status.stdout


@needs_node
def test_a_stale_artifact_is_repaired_and_the_others_are_left_alone(tmp_path: Path) -> None:
    root = _copy_workbench(tmp_path)
    files = _artifacts(root)
    for path in files:
        _to_crlf(path)
    app = root / "web" / "app.js"
    app.write_bytes(app.read_bytes() + b"// stale\r\n")
    untouched = {path: path.read_bytes() for path in files if path != app}
    proc = _build(root)
    assert proc.returncode == 0, _output(proc)
    assert b"\r\n" not in app.read_bytes()
    check = _build(root, check=True)
    assert check.returncode == 0, _output(check)
    for path, body in untouched.items():
        assert path.read_bytes() == body, f"{path.relative_to(root)} was rewritten"


@needs_node
def test_a_missing_artifact_is_recreated_as_canonical_lf(tmp_path: Path) -> None:
    root = _copy_workbench(tmp_path)
    game = root / "web" / "game.js"
    game.unlink()
    proc = _build(root)
    assert proc.returncode == 0, _output(proc)
    assert game.is_file()
    assert b"\r\n" not in game.read_bytes()
    check = _build(root, check=True)
    assert check.returncode == 0, _output(check)


@needs_node
def test_an_lf_checkout_stays_lf_after_a_build(tmp_path: Path) -> None:
    root = _copy_workbench(tmp_path)
    files = _artifacts(root)
    for path in files:
        _to_lf(path)
    before = {path: path.read_bytes() for path in files}
    proc = _build(root)
    assert proc.returncode == 0, _output(proc)
    for path in files:
        assert path.read_bytes() == before[path], f"{path.relative_to(root)} was rewritten"
