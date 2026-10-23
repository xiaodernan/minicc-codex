"""The ``.minicc`` credential refusal must have one home.

``_reject_minicc_sensitive`` existed and nobody called it, while the three
file-tool handlers hand-wrote its sentence four times over - and one of the
four (``read_file``) had already drifted to ``拒绝读取`` where the other
three said ``拒绝访问``.  A guard whose sentence has two spellings reads
like two guards, and the only way to notice is to read both.

This door pins:

* the sentence the read path raises and the sentence the write/edit paths
  raise, byte for byte, through the real handlers;
* the skeleton and the suffix each live in exactly one string constant;
* the builder is called from exactly the three handlers, with exactly the
  two verbs the pinned contract allows;
* the dead duplicate raiser is gone.
"""

from __future__ import annotations

import ast
import json
import pathlib

import pytest

from minicc.tools.editor import Editor
from minicc.tools.fs import (
    MINICC_SENSITIVE_REFUSAL_SUFFIX,
    FsTools,
    _minicc_sensitive_refusal,
)

REPO = pathlib.Path(__file__).resolve().parents[1]
HOME = "minicc/tools/fs.py"

HEAD = ".minicc 下的认证/授权文件: "
TAIL = " (请由用户在工作区外手动处理)"
BUILDER = "_minicc_sensitive_refusal"
DEAD = "_reject_minicc_sensitive"
TOKEN = "/w/.minicc/web_token.json"


def _trees():
    for path in sorted((REPO / "minicc").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path, ast.parse(path.read_bytes().decode("utf-8"))


def _carriers(needle: str) -> list[str]:
    """Every string constant carrying the needle - f-string parts included."""
    hits = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if needle in node.value:
                    hits.append(f"{path.relative_to(REPO).as_posix()}:{node.lineno}")
    return hits


def _definitions(name: str) -> list[str]:
    hits = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name:
                hits.append(path.relative_to(REPO).as_posix())
    return hits


def _bindings(name: str) -> list[str]:
    hits = []
    for path, tree in _trees():
        rel = path.relative_to(REPO).as_posix()
        if rel == HOME:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and node.id == name:
                hits.append(f"{rel}:{node.lineno}")
            elif isinstance(node, ast.arg) and node.arg == name:
                hits.append(f"{rel}:{node.lineno}")
    return hits


def _calls(name: str) -> tuple[list[str], list[object]]:
    """Where the builder is called, and with which first argument."""
    sites: list[str] = []
    verbs: list[object] = []
    for path, tree in _trees():
        rel = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name:
                sites.append(f"{rel}:{node.lineno}")
                first = node.args[0] if node.args else None
                verbs.append(first.value if isinstance(first, ast.Constant) else None)
    return sites, verbs


# --- the sentence itself -------------------------------------------------------


def test_the_read_path_refuses_with_the_read_verb():
    assert _minicc_sensitive_refusal("读取", TOKEN) == (
        f"拒绝读取 .minicc 下的认证/授权文件: {TOKEN}{TAIL}"
    )


def test_the_write_paths_refuse_with_the_access_verb():
    assert _minicc_sensitive_refusal("访问", TOKEN) == (
        f"拒绝访问 .minicc 下的认证/授权文件: {TOKEN}{TAIL}"
    )


def test_the_suffix_is_one_constant():
    assert MINICC_SENSITIVE_REFUSAL_SUFFIX == TAIL


# --- the census ----------------------------------------------------------------


def test_the_skeleton_is_spelled_in_exactly_one_place():
    hits = _carriers(HEAD)
    assert len(hits) == 1, hits
    assert hits[0].startswith(f"{HOME}:"), hits


def test_the_suffix_is_spelled_in_exactly_one_place():
    hits = _carriers(TAIL)
    assert len(hits) == 1, hits
    assert hits[0].startswith(f"{HOME}:"), hits


def test_the_builder_is_defined_exactly_once():
    assert _definitions(BUILDER) == [HOME], _definitions(BUILDER)


def test_no_other_module_re_binds_the_refusal_vocabulary():
    for name in (BUILDER, "MINICC_SENSITIVE_REFUSAL_SUFFIX"):
        assert _bindings(name) == [], (name, _bindings(name))


def test_the_builder_is_called_from_exactly_the_three_handlers():
    sites, _ = _calls(BUILDER)
    assert len(sites) == 3, sites
    assert all(site.startswith(f"{HOME}:") for site in sites), sites


def test_only_the_two_pinned_verbs_reach_the_builder():
    _, verbs = _calls(BUILDER)
    assert sorted({v for v in verbs if v}) == ["访问", "读取"], verbs


def test_the_dead_duplicate_raiser_is_gone():
    assert _definitions(DEAD) == [], _definitions(DEAD)


# --- the real doors ------------------------------------------------------------


def _workspace(tmp_path: pathlib.Path) -> pathlib.Path:
    workspace = tmp_path / "ws"
    (workspace / ".minicc").mkdir(parents=True)
    (workspace / ".minicc" / "web_token.json").write_text(
        json.dumps({"token": "SUPER-SECRET-BEARER-abc123"}), encoding="utf-8"
    )
    return workspace


def test_the_read_door_raises_the_pinned_sentence(tmp_path: pathlib.Path) -> None:
    tools = FsTools(Editor(_workspace(tmp_path)))
    with pytest.raises(Exception) as excinfo:
        tools.read_file({"path": ".minicc/web_token.json"})
    assert str(excinfo.value) == (
        f"拒绝读取 .minicc 下的认证/授权文件: .minicc/web_token.json{TAIL}"
    )


def test_the_write_door_raises_the_pinned_sentence(tmp_path: pathlib.Path) -> None:
    workspace = _workspace(tmp_path)
    tools = FsTools(Editor(workspace))
    with pytest.raises(Exception) as excinfo:
        tools.write_file({"path": ".minicc/web_token.json", "content": "{}"})
    assert str(excinfo.value) == (
        f"拒绝访问 .minicc 下的认证/授权文件: .minicc/web_token.json{TAIL}"
    )
    assert "SUPER-SECRET" in (workspace / ".minicc" / "web_token.json").read_text(
        encoding="utf-8"
    )


def test_the_edit_door_raises_the_pinned_sentence(tmp_path: pathlib.Path) -> None:
    workspace = _workspace(tmp_path)
    tools = FsTools(Editor(workspace))
    with pytest.raises(Exception) as excinfo:
        tools.edit_file({
            "path": ".minicc/web_token.json",
            "old": "SUPER-SECRET",
            "new": "leaked",
        })
    assert str(excinfo.value) == (
        f"拒绝访问 .minicc 下的认证/授权文件: .minicc/web_token.json{TAIL}"
    )
    assert "SUPER-SECRET" in (workspace / ".minicc" / "web_token.json").read_text(
        encoding="utf-8"
    )
