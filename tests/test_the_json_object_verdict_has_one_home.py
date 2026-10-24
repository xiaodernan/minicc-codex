"""M8-T503 — JSON 对象判词两个家：pick_object 的两条拒绝路径各拼一句

「X 必须是 JSON 对象，实际是 T」在 `config.py` 的 `pick_object` 里有两个
家：config.json 里直接写了数组/标量（非字符串路径），和 JSON 字符串拼写
解析出来不是对象（字符串路径）。两处逐字相同（只有主语/实际类型来源不
同）。一个坏 shape 从哪条路进来，读到的就是哪份拼写——一处改了措词其余
没跟上，没有任何测试会红。

家安在 `minicc/config.py`，与「无法读取」「无法写入」判词家族相邻。同函
数里「X 必须是 JSON 对象（例如 {...}）: 解析错误」是另一个事实（JSON 本
身不合法），census 用精确相等天然不误伤。
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
SENTENCE = " 必须是 JSON 对象，实际是 "


def _literal_shapes():
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


def test_the_home_pins_the_sentence() -> None:
    from minicc.config import must_be_json_object_message

    assert (
        must_be_json_object_message("stage_routing", "list")
        == "stage_routing 必须是 JSON 对象，实际是 list"
    )


def test_the_sentence_is_spelled_exactly_once_in_the_package() -> None:
    offenders = [
        f"{path.relative_to(REPO).as_posix()}:{lineno}"
        for path, lineno, text in _literal_shapes()
        if text == SENTENCE
    ]
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the must-be-JSON-object sentence is spelled by hand outside its one "
        "home: " + ", ".join(offenders)
    )


def test_both_paths_ask_the_home() -> None:
    source = (REPO / HOME).read_text(encoding="utf-8")
    assert source.count("must_be_json_object_message(") == 3, (
        "config.py asks the home "
        f"{source.count('must_be_json_object_message(')} times, expected 3 "
        "(one definition plus two refusal paths)"
    )


def _home(tmp_path: Path, monkeypatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.chdir(tmp_path)
    for key in [k for k in os.environ if k.startswith("MINICC_")]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("MINICC_HOME", str(home))
    monkeypatch.setenv("MINICC_API_KEY", "sk-gate-key")
    monkeypatch.setenv("MINICC_BASE_URL", "https://gateway.test/v1")
    monkeypatch.setenv("MINICC_MODEL", "gate-model")
    return home


def test_the_non_string_path_emits_the_homes_sentence(
    tmp_path: Path, monkeypatch
) -> None:
    from minicc.config import ConfigError, load_config

    home = _home(tmp_path, monkeypatch)
    (home / "config.json").write_text(
        json.dumps({"stage_routing": ["fast"]}), encoding="utf-8"
    )
    with pytest.raises(ConfigError) as excinfo:
        load_config(workspace=home.parent)
    assert str(excinfo.value) == "stage_routing 必须是 JSON 对象，实际是 list", (
        excinfo.value
    )


def test_the_parsed_string_path_emits_the_homes_sentence(
    tmp_path: Path, monkeypatch
) -> None:
    from minicc.config import ConfigError, load_config

    home = _home(tmp_path, monkeypatch)
    monkeypatch.setenv("MINICC_STAGE_ROUTING", json.dumps(["fast"]))
    with pytest.raises(ConfigError) as excinfo:
        load_config(workspace=home.parent)
    assert (
        str(excinfo.value) == "MINICC_STAGE_ROUTING 必须是 JSON 对象，实际是 list"
    ), excinfo.value
