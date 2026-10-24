"""M8-T497 — 无法读取判词七个家：七个 JSON 读者各拼一句

「无法读取 X: 原因」有七个家，横跨七个模块：config 的配置层、hooks 的
hooks.json、permissions 的 permissions.json、webauth 的 token store、
allowlist 的 allowlist.json、mcp 的 mcp.json、session 的会话文件（含视
图）。一个文件坏了，用户读到哪句措词取决于坏的是哪个文件——一处改了措
词其余六处没跟上，没有任何测试会红。读者的失败方式各不相同（抛各自的
异常、降级成软错误串），所以家只拥有措词，主语（读的是什么）是参数。

家安在 `minicc/config.py`——七个读者里最大的那个，且它不 import 任何包
内模块，其余读者 import 它不会成环。

「无法读取 {path}: 文件不是合法 UTF-8 文本」是另一个时刻的另一件事（读
到了、但解码失败），按判别式留在原地；门禁的 census 用「以『无法读取』
开头且以『: 』结尾」把它排除。
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/config.py"
HEAD = "无法读取 "
TAIL = ": "


def _literal_shapes():
    """(path, lineno, text) for every string literal - f-string parts joined."""
    for path in sorted(PACKAGE.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        inside_fstring: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                for child in ast.iter_child_nodes(node):
                    inside_fstring.add(id(child))
        for node in ast.walk(tree):
            if id(node) in inside_fstring:
                continue
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                yield path, node.lineno, node.value
            elif isinstance(node, ast.JoinedStr):
                parts = [
                    part.value
                    for part in node.values
                    if isinstance(part, ast.Constant) and isinstance(part.value, str)
                ]
                yield path, node.lineno, "".join(parts)


def _sentence_sites() -> list[str]:
    """Every literal of the exact shape 无法读取 X: <slot>."""
    return [
        f"{path.relative_to(REPO).as_posix()}:{lineno}"
        for path, lineno, text in _literal_shapes()
        if text.startswith(HEAD) and text.endswith(TAIL)
    ]


def test_the_home_pins_the_sentence() -> None:
    from minicc.config import unreadable_file_message

    exc = OSError("boom")
    assert unreadable_file_message("x.json", exc) == f"无法读取 x.json: {exc}"
    assert unreadable_file_message(Path("x.json"), exc) == f"无法读取 x.json: {exc}"
    assert unreadable_file_message("session s.json", exc) == (
        f"无法读取 session s.json: {exc}"
    )


def test_the_sentence_is_spelled_exactly_once_in_the_package() -> None:
    offenders = _sentence_sites()
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the unreadable-file sentence is spelled by hand outside its one home: "
        + ", ".join(offenders)
    )


def test_all_seven_readers_ask_the_home() -> None:
    expected = {
        "config.py": 2,  # the definition plus the config-layer call
        "hooks.py": 1,
        "permissions.py": 1,
        "webauth.py": 1,
        "allowlist.py": 1,
        "mcp.py": 1,
        "session.py": 3,  # _read_payload, load_view, save_view
    }
    for module, count in expected.items():
        source = (REPO / "minicc" / module).read_text(encoding="utf-8")
        assert source.count("unreadable_file_message(") == count, (
            f"{module} asks the home {source.count('unreadable_file_message(')} "
            f"times, expected {count}"
        )


def test_all_seven_readers_share_one_object() -> None:
    from minicc import allowlist, config, hooks, mcp, permissions, session, webauth
    from minicc.config import unreadable_file_message

    for module in (allowlist, config, hooks, mcp, permissions, session, webauth):
        assert module.unreadable_file_message is unreadable_file_message


# --- one behavioural assertion per reader -------------------------------------


def test_the_config_reader_emits_the_homes_sentence(
    tmp_path: Path, monkeypatch
) -> None:
    from minicc.config import ConfigError, load_config

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("MINICC_HOME", str(home))
    monkeypatch.setenv("MINICC_API_KEY", "test-key-placeholder")
    for key in [
        k
        for k in os.environ
        if k.startswith("MINICC_") and k not in {"MINICC_HOME", "MINICC_API_KEY"}
    ]:
        monkeypatch.delenv(key)
    monkeypatch.chdir(tmp_path)
    (home / "config.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError) as excinfo:
        load_config()
    assert str(excinfo.value).startswith(f"无法读取 {home / 'config.json'}: "), (
        excinfo.value
    )


def test_the_hooks_reader_demotes_with_the_homes_sentence(
    tmp_path: Path, monkeypatch
) -> None:
    from minicc.hooks import HookRunner

    monkeypatch.setenv("MINICC_HOOKS", "1")
    (tmp_path / ".minicc").mkdir()
    (tmp_path / ".minicc" / "hooks.json").write_text("{not json", encoding="utf-8")
    runner = HookRunner(tmp_path)
    assert runner.specs == []
    assert runner.load_error.startswith(
        f"无法读取 {tmp_path / '.minicc' / 'hooks.json'}: "
    ), runner.load_error


def test_the_permissions_reader_reports_the_homes_sentence(tmp_path: Path) -> None:
    from minicc.permissions import PERMISSIONS_NAME, load_permission_rules

    (tmp_path / ".minicc").mkdir()
    (tmp_path / ".minicc" / PERMISSIONS_NAME).write_text("{not json", encoding="utf-8")
    _rules, error = load_permission_rules(tmp_path)
    assert error.startswith(f"无法读取 {PERMISSIONS_NAME}: "), error


def test_the_webauth_reader_emits_the_homes_sentence(
    tmp_path: Path, monkeypatch
) -> None:
    from minicc.webauth import WebAuthError, load_or_create_token, token_store_path

    monkeypatch.delenv("MINICC_WEB_TOKEN", raising=False)
    (tmp_path / ".minicc").mkdir()
    token_store_path(tmp_path).write_text("{not json", encoding="utf-8")
    with pytest.raises(WebAuthError) as excinfo:
        load_or_create_token(tmp_path)
    assert str(excinfo.value).startswith(
        f"无法读取 {token_store_path(tmp_path)}: "
    ), excinfo.value


def test_the_allowlist_reader_emits_the_homes_sentence(tmp_path: Path) -> None:
    from minicc.allowlist import AllowlistError, load_allowlist

    (tmp_path / ".minicc").mkdir()
    (tmp_path / ".minicc" / "allowlist.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(AllowlistError) as excinfo:
        load_allowlist(tmp_path)
    assert str(excinfo.value).startswith("无法读取 allowlist: "), excinfo.value


def test_the_mcp_reader_emits_the_homes_sentence(tmp_path: Path) -> None:
    from minicc.mcp import McpError, load_mcp_config

    (tmp_path / ".minicc").mkdir()
    (tmp_path / ".minicc" / "mcp.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(McpError) as excinfo:
        load_mcp_config(tmp_path)
    assert str(excinfo.value).startswith("无法读取 MCP 配置: "), excinfo.value


def test_the_session_readers_emit_the_homes_sentence(tmp_path: Path) -> None:
    from minicc.session import SessionError, SessionStore

    (tmp_path / ".minicc" / "sessions").mkdir(parents=True)
    (tmp_path / ".minicc" / "sessions" / "broken.json").write_text(
        "{not json", encoding="utf-8"
    )
    session = SessionStore(tmp_path, "broken")
    with pytest.raises(SessionError) as excinfo:
        session.fork(1)
    assert str(excinfo.value).startswith(
        f"无法读取 session {session.path}: "
    ), excinfo.value
    with pytest.raises(SessionError) as excinfo:
        session.load_view()
    assert str(excinfo.value).startswith(
        f"无法读取 session 视图 {session.path}: "
    ), excinfo.value
    with pytest.raises(SessionError) as excinfo:
        session.save_view({})
    assert str(excinfo.value).startswith(
        f"无法读取 session {session.path}: "
    ), excinfo.value
