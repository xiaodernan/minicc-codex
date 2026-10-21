"""M8-T350 — deny 规则也管得住快照留下的那份拷贝

`permissions.json` 的 deny 规则是绝对否决：路径 `secrets/*` 被拒，agent 读它
被拒。但**快照**在工作区里留下了另一份：

1. 任务开始时，`capture()` 把工作区的脏文件**逐个拷贝**成前置镜像，落到
   `.minicc/snapshots/<task>/files/<原路径>`；
2. 那条路径**不再匹配** `secrets/*`（它以 `.minicc/` 开头）；
3. 于是 agent 用 `read_file(".minicc/snapshots/<task>/files/secrets/k.txt")`
   读到了**规则拒过的那个文件的内容**——原路径被拒，拷贝没人管。

被拒路径的前置镜像本来也**不需要**：agent 改不了那条路径，没有什么可回滚。

本门钉住：被规则覆盖的路径不进快照（并且在快照的 skipped 理由里写明为什么）；
控制组——没被规则碰到的脏文件照旧留镜像（回滚能力不受影响）。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from minicc.snapshots import capture
from minicc.tools import build_registry
from minicc.tools.editor import Editor
from minicc.tools.schemas import ToolCall


def _git(workspace: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=str(workspace), capture_output=True,
        encoding="utf-8", errors="replace",
    )


def _workspace(tmp_path: Path, *, deny_paths: list[str] | None) -> Path:
    workspace = tmp_path / "ws"
    (workspace / "secrets").mkdir(parents=True)
    (workspace / "secrets" / "k.txt").write_text("old\n", encoding="utf-8")
    (workspace / "src").mkdir()
    (workspace / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    _git(workspace, "init")
    _git(workspace, "config", "user.email", "t@example.test")
    _git(workspace, "config", "user.name", "t")
    _git(workspace, "add", "-A")
    _git(workspace, "commit", "-m", "seed")
    # Both files are dirty now, so the capture has something to preserve.
    (workspace / "secrets" / "k.txt").write_text("TOPSECRET\n", encoding="utf-8")
    (workspace / "src" / "app.py").write_text("x = 2\n", encoding="utf-8")
    if deny_paths is not None:
        (workspace / ".minicc").mkdir(exist_ok=True)
        (workspace / ".minicc" / "permissions.json").write_text(
            json.dumps({"deny": {"paths": deny_paths}}), encoding="utf-8"
        )
    return workspace


def test_a_denied_path_is_not_copied_into_the_snapshot(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, deny_paths=["secrets/*"])
    result = capture(workspace, "t1")
    assert "secrets/k.txt" not in (result.get("files") or []), result
    copy = workspace / ".minicc" / "snapshots" / "t1" / "files" / "secrets" / "k.txt"
    assert not copy.exists(), "the pre-image of a denied path was written anyway"


def test_the_agent_cannot_read_the_denied_content_through_the_snapshot(
    tmp_path: Path,
) -> None:
    """The observable site: the secret is not reachable by any path."""
    workspace = _workspace(tmp_path, deny_paths=["secrets/*"])
    capture(workspace, "t1")
    registry = build_registry(Editor(workspace))
    result = registry.execute(ToolCall(
        "read_file",
        {"path": ".minicc/snapshots/t1/files/secrets/k.txt"},
    ))
    assert result.status != "ok", result.summary
    assert "TOPSECRET" not in ((result.head or "") + (result.output or "")), result


def test_the_skip_is_disclosed(tmp_path: Path) -> None:
    """A skip the user cannot see is a silent hole."""
    workspace = _workspace(tmp_path, deny_paths=["secrets/*"])
    result = capture(workspace, "t1")
    assert "secrets/k.txt" in (result.get("skipped") or []), result
    reasons = result.get("skipped_reasons") or {}
    assert "permissions.json" in str(reasons.get("secrets/k.txt") or ""), reasons


def test_an_ordinary_dirty_file_is_still_preserved(tmp_path: Path) -> None:
    """The control: the rollback ability is untouched."""
    workspace = _workspace(tmp_path, deny_paths=["secrets/*"])
    result = capture(workspace, "t1")
    assert "src/app.py" in (result.get("files") or []), result
    copy = workspace / ".minicc" / "snapshots" / "t1" / "files" / "src" / "app.py"
    assert copy.exists(), "the ordinary pre-image is gone"
