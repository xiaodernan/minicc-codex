"""M8-T498 — 无法写入判词三个家：三个原子写手各拼一句

「无法写入 X: 原因」有三个家：session 的 `_write_payload_at`、webauth 的
token store 保存、allowlist 的保存。三处逐字相同。一个文件写不进去，用户
读到哪句措词取决于哪个写手失败——一处改了措词其余两处没跟上，没有任何测
试会红。写手的失败方式各不相同（抛各自的异常），所以家只拥有措词，主语
（写的是什么）是参数。

家安在 `minicc/config.py`，紧挨「无法读取」判词的家——它们是同一个文件
IO 判词家族，而 config.py 不 import 任何包内模块，读者 import 它不成环。

「无法写入日志文件 %s，已回退到 stderr: %s」（日志回退，另一个事实）和
「无法设置 X 权限」（chmod 失败，另一个事实）都不以「无法写入 」开头，
被 census 的形状判据天然排除。
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/config.py"
HEAD = "无法写入 "
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
    """Every literal of the exact shape 无法写入 X: <slot>."""
    return [
        f"{path.relative_to(REPO).as_posix()}:{lineno}"
        for path, lineno, text in _literal_shapes()
        if text.startswith(HEAD) and text.endswith(TAIL)
    ]


def test_the_home_pins_the_sentence() -> None:
    from minicc.config import unwritable_file_message

    exc = OSError("boom")
    assert unwritable_file_message("x.json", exc) == f"无法写入 x.json: {exc}"
    assert unwritable_file_message(Path("x.json"), exc) == f"无法写入 x.json: {exc}"
    assert unwritable_file_message("allowlist", exc) == f"无法写入 allowlist: {exc}"


def test_the_sentence_is_spelled_exactly_once_in_the_package() -> None:
    offenders = _sentence_sites()
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the unwritable-file sentence is spelled by hand outside its one home: "
        + ", ".join(offenders)
    )


def test_all_three_writers_ask_the_home() -> None:
    expected = {
        "config.py": 1,  # the definition only - config itself writes nothing
        "session.py": 1,
        "webauth.py": 1,
        "allowlist.py": 1,
    }
    for module, count in expected.items():
        source = (REPO / "minicc" / module).read_text(encoding="utf-8")
        assert source.count("unwritable_file_message(") == count, (
            f"{module} asks the home {source.count('unwritable_file_message(')} "
            f"times, expected {count}"
        )


def test_all_three_writers_share_one_object() -> None:
    from minicc import allowlist, config, session, webauth
    from minicc.config import unwritable_file_message

    for module in (allowlist, config, session, webauth):
        assert module.unwritable_file_message is unwritable_file_message


# --- one behavioural assertion per writer -------------------------------------


def test_the_session_writer_emits_the_homes_sentence(
    tmp_path: Path, monkeypatch
) -> None:
    from minicc import session as session_module
    from minicc.session import SessionError, SessionStore

    def raiser(source: Path, target: Path) -> None:
        raise OSError("boom")

    monkeypatch.setattr(session_module, "_replace_with_retry", raiser)
    store = SessionStore(tmp_path, "s")
    with pytest.raises(SessionError) as excinfo:
        store.save_view({})
    assert str(excinfo.value).startswith(
        f"无法写入 {store.path}: "
    ), excinfo.value


def test_the_token_store_writer_emits_the_homes_sentence(
    tmp_path: Path, monkeypatch
) -> None:
    from minicc import webauth as webauth_module
    from minicc.webauth import WebAuthError, load_or_create_token, token_store_path

    def raiser(source: Path, dest: Path) -> None:
        raise OSError("boom")

    monkeypatch.delenv("MINICC_WEB_TOKEN", raising=False)
    monkeypatch.setattr(webauth_module, "_atomic_replace", raiser)
    with pytest.raises(WebAuthError) as excinfo:
        load_or_create_token(tmp_path)
    assert str(excinfo.value).startswith(
        f"无法写入 {token_store_path(tmp_path)}: "
    ), excinfo.value


def test_the_allowlist_writer_emits_the_homes_sentence(
    tmp_path: Path, monkeypatch
) -> None:
    from minicc import allowlist as allowlist_module
    from minicc.allowlist import AllowlistError, save_allowlist

    def raiser(source: Path, dest: Path) -> None:
        raise OSError("boom")

    monkeypatch.setattr(allowlist_module.os, "replace", raiser)
    with pytest.raises(AllowlistError) as excinfo:
        save_allowlist(tmp_path, {})
    assert str(excinfo.value).startswith("无法写入 allowlist: "), excinfo.value
