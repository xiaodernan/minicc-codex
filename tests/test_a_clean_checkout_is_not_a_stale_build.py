"""M8-T571（第五百五十三批）：干净检出不许被读成「源码建不出这份产物」。

`scripts/build-web.mjs --check` 把磁盘上的产物与 esbuild 吐出的文本逐字节比。
在 core.autocrlf=true 的机器上，clone 出来的是 CRLF，esbuild 吐的是 LF，于是
六份产物全部报 `is stale`——被比较的是行尾，不是内容。`scratch/probe571.py`
量到：干净 CRLF 检出 rc=1（六行 stale），把六份产物改写成 LF 后 rc=0，
真漂移仍然 rc=1。

行为格跑的是发出去的 `scripts/build-web.mjs` 本身，但整个工作台（web/、脚本、
esbuild）复制进临时目录再跑，不碰工作树。node 或 esbuild 不在时行为格 skip——
与 test_web_assets_are_fresh.py 的 P3 同一个理由。
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
ESBUILD = REPO / "node_modules" / "esbuild"
PLATFORM = REPO / "node_modules" / "@esbuild"

needs_node = pytest.mark.skipif(
    NODE is None or not ESBUILD.is_dir() or not PLATFORM.is_dir(),
    reason="node or esbuild is not installed",
)


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


def _check(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [NODE, str(root / "scripts" / "build-web.mjs"), "--check"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _output(proc: subprocess.CompletedProcess) -> str:
    return (proc.stdout or "") + (proc.stderr or "")


@needs_node
def test_a_crlf_checkout_is_up_to_date(tmp_path: Path) -> None:
    root = _copy_workbench(tmp_path)
    for artifact in _artifacts(root):
        _to_crlf(artifact)
    proc = _check(root)
    text = _output(proc)
    assert "is stale" not in text, text
    assert proc.returncode == 0, text
    assert "are up to date" in (proc.stdout or ""), text


@needs_node
def test_a_mixed_checkout_is_up_to_date(tmp_path: Path) -> None:
    root = _copy_workbench(tmp_path)
    for artifact in _artifacts(root):
        _to_crlf(artifact)
    _to_lf(root / "web" / "game.js")
    proc = _check(root)
    text = _output(proc)
    assert "is stale" not in text, text
    assert proc.returncode == 0, text


@needs_node
def test_a_real_edit_is_still_stale(tmp_path: Path) -> None:
    root = _copy_workbench(tmp_path)
    app = root / "web" / "app.js"
    app.write_bytes(app.read_bytes() + b"// drift\r\n")
    proc = _check(root)
    text = _output(proc)
    assert proc.returncode == 1, text
    assert "app.js is stale" in text, text


@needs_node
def test_a_trailing_space_is_still_stale(tmp_path: Path) -> None:
    root = _copy_workbench(tmp_path)
    manifest = root / "web" / "asset-manifest.json"
    manifest.write_bytes(manifest.read_bytes() + b" ")
    proc = _check(root)
    text = _output(proc)
    assert proc.returncode == 1, text
    assert "asset-manifest.json is stale" in text, text
