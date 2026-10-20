"""M8-T285 — 一个不是 UTF-8 的文件，不该让整个运行崩掉

``UnicodeDecodeError`` 是 ``ValueError`` 的子类，但**不是**
``json.JSONDecodeError`` 的子类。所以只捕 JSON 那一个的 except 子句，
接不住它——于是一个手改过编码的配置文件（记事本、GBK 编辑器、或者
一个被别的程序写坏的 JSON）让裸异常逃出了模块。

而这些模块各自的契约都写着"坏文件不致命"。

This door pins:

* a permissions.json that is not UTF-8 is reported, not raised;
* a checklist that is not UTF-8 is read as empty, not raised;
* the controls: a well-formed file still works, and a wrong *shape* is
  still reported as a configuration error.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from minicc.permissions import load_permission_rules, match_permission_rule
from minicc.tools.todo import TodoTools


def _permissions(workspace: Path, raw: bytes) -> Path:
    path = workspace / ".minicc" / "permissions.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return path


def test_a_permissions_file_that_is_not_utf8_is_reported(tmp_path: Path) -> None:
    """It used to raise a bare UnicodeDecodeError out of the module."""
    _permissions(tmp_path, '{"model": "中文"}'.encode("gbk"))
    rules, error = load_permission_rules(tmp_path)
    assert error, "the unreadable file was not reported"
    assert rules == {"allow": {"commands": [], "paths": [], "tools": []},
                     "deny": {"commands": [], "paths": [], "tools": []}}


def test_a_permissions_file_that_is_not_utf8_does_not_break_a_decision(
    tmp_path: Path,
) -> None:
    """The control: the gate still answers."""
    _permissions(tmp_path, '{"model": "中文"}'.encode("gbk"))
    assert match_permission_rule(tmp_path, "read_file", {"path": "a.py"}) is None


def test_a_well_formed_permissions_file_still_works(tmp_path: Path) -> None:
    _permissions(tmp_path, json.dumps({"deny": {"paths": ["secrets/*"]}}).encode("utf-8"))
    rules, error = load_permission_rules(tmp_path)
    assert error == ""
    assert rules["deny"]["paths"] == ["secrets/*"]


def test_a_wrong_shape_is_still_reported_as_a_config_error(tmp_path: Path) -> None:
    """A non-object top level is a configuration mistake, not a decode error."""
    _permissions(tmp_path, b"[]")
    rules, error = load_permission_rules(tmp_path)
    assert "非法" in error, error
    assert rules["deny"]["paths"] == []


def test_a_checklist_that_is_not_utf8_reads_as_empty(tmp_path: Path) -> None:
    """The todo tool must not raise on a broken checklist."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    path = workspace / ".minicc" / "todos.json"
    path.parent.mkdir(parents=True)
    path.write_bytes('{"todos": [{"content": "中文"}]}'.encode("gbk"))
    result = TodoTools(workspace).read({})
    assert result.status == "ok", result.summary
