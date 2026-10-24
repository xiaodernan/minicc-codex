"""M8-T506 — 快照路径越界判词两个家：_relative 与 _within 各拼一句

「快照路径越界: X」在 `snapshots.py` 里有两个家：`_relative` 拒绝原始拼写
里就含 `..`/盘符/绝对路径的路径，`_within` 拒绝解析后落到工作区外的路
径。两处逐字相同（主语都是 rel）。一条坏路径从哪扇门进来，读到的就是哪
份拼写——一处改了措词其余没跟上，没有任何测试会红。

家安在 `minicc/snapshots.py` 模块层，紧挨 `_relative`——两个调用点都在
这个模块。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/snapshots.py"
SENTENCE = "快照路径越界: "


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
    from minicc.snapshots import snapshot_path_escapes_message

    assert snapshot_path_escapes_message("../x") == "快照路径越界: ../x"


def test_the_sentence_is_spelled_exactly_once_in_the_package() -> None:
    offenders = [
        f"{path.relative_to(REPO).as_posix()}:{lineno}"
        for path, lineno, text in _literal_shapes()
        if text == SENTENCE
    ]
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the snapshot-escape sentence is spelled by hand outside its one "
        "home: " + ", ".join(offenders)
    )


def test_both_gates_ask_the_home() -> None:
    source = (REPO / HOME).read_text(encoding="utf-8")
    assert source.count("snapshot_path_escapes_message(") == 3, (
        "snapshots.py asks the home "
        f"{source.count('snapshot_path_escapes_message(')} times, expected 3 "
        "(one definition plus two gates)"
    )


def test_the_raw_spelling_gate_emits_the_homes_sentence() -> None:
    from minicc.snapshots import SnapshotError, _relative

    # A backslash spelling: the gate normalizes it for the check but the
    # verdict names the normalized rel, not the raw bytes the caller wrote.
    with pytest.raises(SnapshotError) as excinfo:
        _relative("..\\escape.txt")
    assert str(excinfo.value) == "快照路径越界: ../escape.txt", excinfo.value


def test_the_resolved_path_gate_emits_the_homes_sentence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import minicc.snapshots as snapshots

    # ``_within`` re-runs ``_relative`` on the same rel; feeding it a
    # parent-escaping spelling isolates the resolved-path gate (a raw
    # ``..`` is refused by ``_relative`` first, which is the other gate's
    # own test above).  The gate names the caller's rel, not the spelling
    # ``_relative`` handed back.
    monkeypatch.setattr(snapshots, "_relative", lambda rel: "../escape.txt")
    with pytest.raises(snapshots.SnapshotError) as excinfo:
        snapshots._within(tmp_path, "whatever")
    assert str(excinfo.value) == "快照路径越界: whatever", excinfo.value
