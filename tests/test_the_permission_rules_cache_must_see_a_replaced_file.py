"""M8-T293 — 授权规则的缓存戳必须能看见"文件被换掉了"

`permissions.json` 的读取结果按 `(mtime, size)` 缓存。这条 memo 住在
**授权**路径上：一份**等长**的改写（`"secrets/*"` → `"secretz/*"`）会让旧的
规则继续生效——一份**陈旧的否决**。

程序改写配置文件的常见方式是**原子替换**（写临时文件再 rename），那会换掉
inode。旧戳看不见这件事。

本门禁钉住：原子替换后规则**立刻**更新；没有规则时默认放行。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from minicc.permissions import load_permission_rules, match_permission_rule


def _write_rules(workspace: Path, payload: dict[str, object]) -> Path:
    path = workspace / ".minicc" / "permissions.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_an_atomic_replace_invalidates_the_cached_rules(tmp_path: Path) -> None:
    """The rules are cached; a replaced file must not serve the old ones."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write_rules(workspace, {"deny": {"paths": ["secrets/*"]}})

    rules, error = load_permission_rules(workspace)
    assert error == ""
    assert rules["deny"]["paths"] == ["secrets/*"]

    # An atomic replace: a different file, same content length, and the
    # replacement's mtime pinned to the original's - so the *only* thing
    # that changed is the file itself.
    original = workspace / ".minicc" / "permissions.json"
    stat = original.stat()
    staging = workspace / ".minicc" / "permissions.json.new"
    staging.write_text(
        json.dumps({"deny": {"paths": ["secretz/*"]}}, ensure_ascii=False),
        encoding="utf-8",
    )
    os.utime(staging, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    os.replace(staging, original)

    rules, error = load_permission_rules(workspace)
    assert error == ""
    assert rules["deny"]["paths"] == ["secretz/*"], (
        "the replaced rules file still served the old deny rule"
    )


def test_the_cached_decision_follows_the_new_rules(tmp_path: Path) -> None:
    """The control: the decision itself changes with the rules."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write_rules(workspace, {"deny": {"paths": ["secrets/*"]}})
    assert match_permission_rule(workspace, "read_file", {"path": "secrets/k.txt"}) == "deny"

    staging = workspace / ".minicc" / "permissions.json.new"
    staging.write_text(
        json.dumps({"deny": {"paths": ["secretz/*"]}}, ensure_ascii=False),
        encoding="utf-8",
    )
    original = workspace / ".minicc" / "permissions.json"
    stat = original.stat()
    os.utime(staging, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    os.replace(staging, original)

    assert match_permission_rule(workspace, "read_file", {"path": "secrets/k.txt"}) is None, (
        "the old deny rule was still in force after the file was replaced"
    )


def test_no_rules_means_no_denial(tmp_path: Path) -> None:
    """The control: a workspace without the file is not denied by it."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    assert match_permission_rule(workspace, "read_file", {"path": "secrets/k.txt"}) is None
