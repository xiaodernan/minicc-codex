"""行为级栅栏：minicc.permissions 的规则解析与匹配纯逻辑。

`permissions.py` 是 `audit.authorize_tool` 委托的 deny/allow 规则匹配核心
（M7-T3 把 deny 规则收进 `authorize_tool` 之上），其解析/匹配契约长期零单测。
本文件把每条契约钉成可复跑断言：

- ``_empty_rules``：空规则的标准形状。
- ``_normalize_side``：列表规整（去空白、去重、512 字符/256 条截断、非 dict/非 list 跳过）。
- ``_validate``：顶层必须是对象、未知字段拒绝、``permissions`` 包裹展开、非法抛 PermissionConfigError。
- ``_match_patterns``：tool / bash 命令 / path 三轴匹配语义（fnmatch 通配）。
- ``match_permission_rule``：deny > allow > None 终态，含缺失文件与损坏文件兜底。

临时 workspace 用仓库外的 tempfile（不碰仓库、不触发 git 删除护栏）。
直接调用：`python tests/test_permissions_pure.py`。
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from minicc.permissions import (
    PermissionConfigError,
    _empty_rules,
    _match_patterns,
    _normalize_side,
    _validate,
    match_permission_rule,
)


# --------------------------------------------------------------------------
# _empty_rules
# --------------------------------------------------------------------------

def test_empty_rules_shape():
    rules = _empty_rules()
    assert set(rules) == {"allow", "deny"}
    for side in ("allow", "deny"):
        assert rules[side] == {"tools": [], "commands": [], "paths": []}


# --------------------------------------------------------------------------
# _normalize_side
# --------------------------------------------------------------------------

def test_normalize_non_dict_returns_empty():
    assert _normalize_side("nope") == {"tools": [], "commands": [], "paths": []}
    assert _normalize_side(None) == {"tools": [], "commands": [], "paths": []}


def test_normalize_strips_and_keeps_lists():
    side = _normalize_side({"tools": [" read_file ", "write_file"], "commands": [], "paths": ["src/*"]})
    assert side["tools"] == ["read_file", "write_file"]
    assert side["paths"] == ["src/*"]


def test_normalize_dedupes():
    assert _normalize_side({"tools": ["a", "a", "b"]})["tools"] == ["a", "b"]


def test_normalize_drops_empty_and_none_items():
    assert _normalize_side({"tools": ["", None, "x", "  "]})["tools"] == ["x"]


def test_normalize_skips_non_list_values():
    assert _normalize_side({"tools": "not-a-list", "commands": ["c"]}) == {
        "tools": [], "commands": ["c"], "paths": []
    }


def test_normalize_truncates_item_length():
    long_item = "a" * 600
    side = _normalize_side({"tools": [long_item]})
    assert len(side["tools"][0]) == 512


def test_normalize_truncates_item_count():
    many = [f"t{i}" for i in range(300)]
    side = _normalize_side({"tools": many})
    assert len(side["tools"]) == 256


# --------------------------------------------------------------------------
# _validate
# --------------------------------------------------------------------------

def test_validate_rejects_non_dict():
    with pytest.raises(PermissionConfigError):
        _validate("not a dict")


def test_validate_rejects_unknown_field():
    with pytest.raises(PermissionConfigError):
        _validate({"foo": 1})


def test_validate_accepts_plain_rules():
    rules, error = _validate({"allow": {"tools": ["read_file"]}, "deny": {"tools": ["x"]}})
    assert error == ""
    assert rules["allow"]["tools"] == ["read_file"]
    assert rules["deny"]["tools"] == ["x"]


def test_validate_unwraps_permissions_key():
    rules, error = _validate({"permissions": {"allow": {"tools": ["read_file"]}}})
    assert error == ""
    assert rules["allow"]["tools"] == ["read_file"]


# --------------------------------------------------------------------------
# _match_patterns (three axes)
# --------------------------------------------------------------------------

def test_match_tool_axis():
    side = {"tools": ["read_file"], "commands": [], "paths": []}
    assert _match_patterns("read_file", {}, side) is True
    assert _match_patterns("write_file", {}, side) is False


def test_match_tool_axis_wildcard():
    side = {"tools": ["*_file"], "commands": [], "paths": []}
    assert _match_patterns("read_file", {}, side) is True
    assert _match_patterns("read_dir", {}, side) is False


def test_match_bash_command_axis():
    side = {"tools": [], "commands": ["rm *"], "paths": []}
    assert _match_patterns("bash", {"command": "rm -rf /tmp/x"}, side) is True
    assert _match_patterns("bash", {"command": "ls -la"}, side) is False


def test_match_bash_command_axis_only_for_bash_tool():
    side = {"tools": [], "commands": ["rm *"], "paths": []}
    # Non-bash tool never reaches the command axis.
    assert _match_patterns("write_file", {"command": "rm -rf /tmp/x"}, side) is False


def test_match_path_axis():
    side = {"tools": [], "commands": [], "paths": ["src/*"]}
    assert _match_patterns("write_file", {"path": "src/main.py"}, side) is True
    assert _match_patterns("write_file", {"file": "src/x.py"}, side) is True
    assert _match_patterns("write_file", {"path": "tests/main.py"}, side) is False


def test_match_no_side_matches_returns_false():
    side = {"tools": [], "commands": [], "paths": []}
    assert _match_patterns("anything", {"path": "src/x"}, side) is False


# --------------------------------------------------------------------------
# match_permission_rule (deny > allow > None) via temp workspace
# --------------------------------------------------------------------------

def _write_permissions(rules: dict) -> Path:
    ws = Path(tempfile.mkdtemp(prefix="minicc_perm_"))
    minicc = ws / ".minicc"
    minicc.mkdir()
    (minicc / "permissions.json").write_text(json.dumps(rules), encoding="utf-8")
    return ws


def test_rule_deny_wins_over_allow():
    ws = _write_permissions({"deny": {"tools": ["x"]}, "allow": {"tools": ["x"]}})
    assert match_permission_rule(ws, "x", {}) == "deny"


def test_rule_allow_when_only_allow():
    ws = _write_permissions({"allow": {"tools": ["read_file"]}})
    assert match_permission_rule(ws, "read_file", {}) == "allow"


def test_rule_none_when_no_match():
    ws = _write_permissions({"allow": {"tools": ["read_file"]}})
    assert match_permission_rule(ws, "other_tool", {}) is None


def test_rule_missing_file_is_none():
    ws = Path(tempfile.mkdtemp(prefix="minicc_perm_"))
    assert match_permission_rule(ws, "anything", {}) is None


def test_rule_malformed_file_is_none():
    ws = _write_permissions({})  # writes "{}" which is valid -> refine below
    # Overwrite with invalid JSON to exercise the parse-error branch.
    (ws / ".minicc" / "permissions.json").write_text("{not json", encoding="utf-8")
    assert match_permission_rule(ws, "anything", {}) is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q", "-W", "error"]))
