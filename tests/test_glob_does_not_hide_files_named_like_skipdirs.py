"""M8-T119: FsTools.glob must not hide a FILE just because its name is in SKIP_DIRS.

The old skip filter sliced ``p.parts[len(root.parts):]``, which keeps the matched
entry's own basename, so a file literally named ``build`` / ``target`` / ``dist`` /
``venv`` was filtered out of glob results — while grep (which used ``rel.parts[:-1]``,
ancestors only) searched those same files. Two read-only tools disagreed about one
workspace.

The fix hides an entry only for a SKIP_DIRS *ancestor*, or when the entry is itself a
skipped *directory*. Cases 3 and 4 pin the half that a naive "drop the basename" fix
would regress: the skipped directories themselves must stay hidden.
"""

from __future__ import annotations

from pathlib import Path

from minicc.tools.editor import Editor
from minicc.tools.fs import FsTools


def _listing(result) -> set[str]:
    text = result.head
    if result.tail:
        text = f"{text}\n{result.tail}"
    return {line for line in text.splitlines() if line and line != "(无匹配)"}


def _workspace(tmp_path: Path) -> FsTools:
    (tmp_path / "build").write_text("a file named build\n", encoding="utf-8")
    (tmp_path / "keep.py").write_text("normal file\n", encoding="utf-8")
    src = tmp_path / "src"
    src.mkdir()
    (src / "target").write_text("a file named target\n", encoding="utf-8")
    nm = tmp_path / "node_modules"
    nm.mkdir()
    (nm / "pkg.js").write_text("inside a skipped dir\n", encoding="utf-8")
    pyc = tmp_path / "__pycache__"
    pyc.mkdir()
    (pyc / "m.pyc").write_text("inside a skipped dir\n", encoding="utf-8")
    return FsTools(Editor(tmp_path))


def test_glob_lists_file_named_like_skipdir(tmp_path: Path) -> None:
    shown = _listing(_workspace(tmp_path).glob({"pattern": "**/*"}))
    assert "build" in shown


def test_glob_lists_nested_file_named_like_skipdir(tmp_path: Path) -> None:
    shown = _listing(_workspace(tmp_path).glob({"pattern": "**/*"}))
    assert "src/target" in shown


def test_glob_still_hides_skipped_directory_itself(tmp_path: Path) -> None:
    shown = _listing(_workspace(tmp_path).glob({"pattern": "**/*"}))
    assert "node_modules" not in shown
    assert "__pycache__" not in shown


def test_glob_still_hides_files_under_skipped_directory(tmp_path: Path) -> None:
    shown = _listing(_workspace(tmp_path).glob({"pattern": "**/*"}))
    assert "node_modules/pkg.js" not in shown
    assert "__pycache__/m.pyc" not in shown


def test_glob_match_count_reflects_named_files(tmp_path: Path) -> None:
    # Aggregate lock: build + keep.py + src + src/target are the only survivors.
    result = _workspace(tmp_path).glob({"pattern": "**/*"})
    assert f"命中 {len(_listing(result))} 个" in result.summary
    assert _listing(result) == {"build", "keep.py", "src", "src/target"}
