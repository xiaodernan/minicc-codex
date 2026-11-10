"""M8-T768 — ``minicc/agent/test_selection.py`` 的相关测试选取。

这个模块是"改动一个模块，该跑哪些测试"的唯一家（M8-T507 / M8-T551 / M8-T554），
零同名测试（模块→测试映射发现）。它的承诺：

1. `is_test_filename`（`test_` 前缀 / `_test.py` 后缀，`test_`-函数检查不在此）；
2. 改动 ``.py`` → 同名 `test_<stem>.py`（tests/ 或同目录）必选；
3. 测试文件的 `import` 与变更模块求交即选中（语法层、不导入代码）；
4. 无法读取的测试文件按"可能相关"保留（M8-T551），绝不静默丢弃；
5. 非 ``.py`` 变更 → 空集（不误跑全量）。
"""

from __future__ import annotations

import pytest

from minicc.agent import test_selection as ts


def test_is_test_filename_truth_table():
    assert ts.is_test_filename("test_alpha.py") is True
    assert ts.is_test_filename("alpha_test.py") is True
    assert ts.is_test_filename("alpha.py") is False
    assert ts.is_test_filename("conftest.py") is False
    assert ts.is_test_filename("latest.py") is False


def _root(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "minicc").mkdir()
    return tmp_path


def test_changed_module_selects_same_name_test(tmp_path):
    root = _root(tmp_path)
    (root / "tests" / "test_foo.py").write_text("import os\n", encoding="utf-8")
    (root / "minicc" / "foo.py").write_text("x = 1\n", encoding="utf-8")
    selected = ts.relevant_python_tests(root, ["minicc/foo.py"])
    assert "tests/test_foo.py" in selected


def test_changed_module_selects_test_that_imports_it(tmp_path):
    root = _root(tmp_path)
    (root / "tests" / "test_importer.py").write_text("import minicc.bar\n", encoding="utf-8")
    (root / "tests" / "test_unrelated.py").write_text("import os\n", encoding="utf-8")
    (root / "minicc" / "bar.py").write_text("x = 1\n", encoding="utf-8")
    selected = ts.relevant_python_tests(root, ["minicc/bar.py"])
    assert "tests/test_importer.py" in selected
    assert "tests/test_unrelated.py" not in selected


def test_changed_module_selects_from_import_variant(tmp_path):
    root = _root(tmp_path)
    (root / "tests" / "test_from.py").write_text("from minicc.baz import thing\n", encoding="utf-8")
    (root / "minicc" / "baz.py").write_text("thing = 1\n", encoding="utf-8")
    selected = ts.relevant_python_tests(root, ["minicc/baz.py"])
    assert "tests/test_from.py" in selected


def test_unreadable_test_file_is_kept_not_dropped(tmp_path):
    root = _root(tmp_path)
    (root / "tests" / "test_broken.py").write_text("def broken(:\n", encoding="utf-8")
    (root / "minicc" / "qux.py").write_text("x = 1\n", encoding="utf-8")
    selected = ts.relevant_python_tests(root, ["minicc/qux.py"])
    assert "tests/test_broken.py" in selected


def test_non_python_change_selects_nothing(tmp_path):
    root = _root(tmp_path)
    (root / "tests" / "test_foo.py").write_text("import minicc.foo\n", encoding="utf-8")
    selected = ts.relevant_python_tests(root, ["docs/notes.md"])
    assert selected == []


def test_changed_test_file_is_selected_for_itself(tmp_path):
    root = _root(tmp_path)
    (root / "tests" / "test_self.py").write_text("import os\n", encoding="utf-8")
    selected = ts.relevant_python_tests(root, ["tests/test_self.py"])
    assert "tests/test_self.py" in selected
