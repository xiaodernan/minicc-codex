"""M8-T353 — 部署级 yolo 放开写与命令，不放开联网

同一个"yolo"，在两个面上给出两个答案：

* **Web 面**（`minicc/task_contract.py`，被 `tests/test_task_contract.py` 钉住）：
  **任务级** `permission_mode: "yolo"` 打开写与联网两个开关；**部署级** yolo
  只打开写——"够到网络是另一份授权"；
* **CLI 面**（`minicc/main.py::_permission_gate`）：部署级 yolo 顺带把
  `allow_network` 也打开 ✗。

而 CLI 自己的 `--yolo` 帮助写的是"**自动允许写文件和执行命令**"——**没有提
联网**。所以旧行为与它自己的文案、与 Web 的已钉契约**都矛盾**：同一个部署，
在两个面上对"能不能联网"给出不同答案。

本门钉住：部署级 yolo 放开写与命令、**不**放开联网；显式的 `--allow-network`
照旧放行；**任务级** yolo 仍然"全部放行"（含联网 ✓，与 CLI 帮助一致）。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from minicc.main import _permission_gate
from minicc.tools import build_registry
from minicc.tools.editor import Editor
from minicc.tools.schemas import ToolCall


def _config(*, yolo: bool) -> Any:
    return SimpleNamespace(yolo=yolo)


def _gate(tmp_path: Path, *, yolo: bool, permission_mode: str = "default", allow_network: bool = False):
    registry = build_registry(Editor(tmp_path))
    return _permission_gate(
        _config(yolo=yolo),
        registry,
        permission_mode,
        allow_network=allow_network,
        workspace=tmp_path,
    )


def test_the_deployment_yolo_does_not_grant_the_network(tmp_path: Path) -> None:
    """The pinned contract: the network is a separate grant."""
    gate = _gate(tmp_path, yolo=True)
    allowed = gate("web_search", ToolCall("web_search", {"query": "x"}))
    assert allowed is False, "the deployment yolo granted the network"


def test_the_deployment_yolo_still_grants_writes_and_commands(tmp_path: Path) -> None:
    """The CLI's own promise: 自动允许写文件和执行命令."""
    gate = _gate(tmp_path, yolo=True)
    assert gate("write_file", ToolCall("write_file", {"path": "a.py", "content": "x"})) is True
    assert gate("bash", ToolCall("bash", {"command": "echo hi"})) is True


def test_an_explicit_network_grant_still_works(tmp_path: Path) -> None:
    """The control: --allow-network is the grant for the network."""
    gate = _gate(tmp_path, yolo=True, allow_network=True)
    assert gate("web_search", ToolCall("web_search", {"query": "x"})) is True


def test_the_task_level_yolo_still_allows_everything(tmp_path: Path) -> None:
    """The control: the task-level yolo mode is "全部放行"."""
    gate = _gate(tmp_path, yolo=False, permission_mode="yolo")
    assert gate("web_search", ToolCall("web_search", {"query": "x"})) is True
    assert gate("write_file", ToolCall("write_file", {"path": "a.py", "content": "x"})) is True


def test_the_web_face_agrees(tmp_path: Path) -> None:
    """The control: the two faces answer the same question the same way."""
    from minicc.task_contract import resolve_task_permissions

    changes, network, mode = resolve_task_permissions({}, yolo=True)
    assert (changes, network, mode) == (True, False, "default")
