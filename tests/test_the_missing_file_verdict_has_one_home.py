"""M8-T494 — 文件不存在判词五个家：editor 的五个门各拼一句

「文件不存在: X」在 `tools/editor.py` 里有五个家：`read_file_meta`、
`read_file`、`apply_edit`、`delete` 四个门各拼一遍完全相同的句子，
`move` 的源文件门拼的是同一形状换了个主语（「源文件不存在」）。模型从哪
扇门进去，读到的就是哪份拼写——一处改了措辞其余四处没跟上，没有任何测
试会红（T489 的教训：同文件重复比跨文件重复更危险，因为它连「不同作
者」的借口都没有）。

家安在 `minicc/tools/editor.py` 模块层，紧挨 `_validate_read_window`——
另一个「五个门共用一条规则」的家。主语做参数：move 的源文件是同一句子
换一个名词，形状仍然只有一个。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/tools/editor.py"
TAIL = "不存在: "


def _editor_literals():
    """Joined literal text of every string in editor.py (f-string parts joined)."""
    path = REPO / HOME
    tree = ast.parse(path.read_text(encoding="utf-8"))
    inside_fstring: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            for child in ast.iter_child_nodes(node):
                inside_fstring.add(id(child))
    for node in ast.walk(tree):
        if id(node) in inside_fstring:
            continue
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.lineno, node.value
        elif isinstance(node, ast.JoinedStr):
            parts = [
                part.value
                for part in node.values
                if isinstance(part, ast.Constant) and isinstance(part.value, str)
            ]
            yield node.lineno, "".join(parts)


def test_the_home_pins_both_subjects() -> None:
    from minicc.tools.editor import missing_file_message

    assert missing_file_message("a.py") == "文件不存在: a.py"
    assert missing_file_message("a.py", "源文件") == "源文件不存在: a.py"


def test_the_sentence_shape_is_spelled_exactly_once_in_the_module() -> None:
    offenders = [
        f"{HOME}:{lineno} {text!r}"
        for lineno, text in _editor_literals()
        if text.endswith(TAIL)
    ]
    assert len(offenders) == 1, (
        "the file-missing sentence is spelled by hand outside its one home: "
        + ", ".join(offenders)
    )


def test_nobody_spells_the_default_subjects_sentence_by_hand() -> None:
    """A second copy (constant or f-string) that names 文件 is a second home."""
    offenders = [
        f"{HOME}:{lineno} {text!r}"
        for lineno, text in _editor_literals()
        if "文件不存在" in text
    ]
    assert offenders == [], (
        "the default-subject sentence is spelled outside its one home: "
        + ", ".join(offenders)
    )


def test_all_five_gates_ask_the_home() -> None:
    source = (REPO / HOME).read_text(encoding="utf-8")
    assert source.count("missing_file_message(") == 6, (
        "the definition plus the five gates are the only spellings, found "
        f"{source.count('missing_file_message(')}"
    )


def test_the_read_gate_raises_the_homes_sentence(tmp_path: Path) -> None:
    from minicc.tools.editor import Editor, EditError, missing_file_message

    with pytest.raises(EditError) as excinfo:
        Editor(tmp_path).read_file("nope.txt")
    assert str(excinfo.value) == missing_file_message("nope.txt")


def test_the_move_gate_raises_the_homes_sentence_with_its_subject(
    tmp_path: Path,
) -> None:
    from minicc.tools.editor import Editor, EditError, missing_file_message

    with pytest.raises(EditError) as excinfo:
        Editor(tmp_path).move("missing-src.txt", "dst.txt")
    assert str(excinfo.value) == missing_file_message("missing-src.txt", "源文件")


def test_the_meta_gate_raises_the_homes_sentence(tmp_path: Path) -> None:
    from minicc.tools.editor import Editor, EditError, missing_file_message

    with pytest.raises(EditError) as excinfo:
        Editor(tmp_path).read_file_meta("nope.txt")
    assert str(excinfo.value) == missing_file_message("nope.txt")


def test_the_apply_edit_gate_raises_the_homes_sentence(tmp_path: Path) -> None:
    from minicc.tools.editor import Editor, EditError, missing_file_message

    with pytest.raises(EditError) as excinfo:
        Editor(tmp_path).apply_edit("nope.txt", "a", "b")
    assert str(excinfo.value) == missing_file_message("nope.txt")


def test_the_delete_gate_raises_the_homes_sentence(tmp_path: Path) -> None:
    from minicc.tools.editor import Editor, EditError, missing_file_message

    with pytest.raises(EditError) as excinfo:
        Editor(tmp_path).delete("nope.txt")
    assert str(excinfo.value) == missing_file_message("nope.txt")
