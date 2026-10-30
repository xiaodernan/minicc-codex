"""M8-T554: a test directory larger than the scan window is not a directory
whose tail was checked.

``_test_files`` yielded at most 500 test files and stopped; the selection
answered with whatever the first 500 held.  A test file past the window was
never examined, and it got the same answer as a file that provably does not
import the changed module.  Measured on HEAD (500 filler test files + one
importer, sorted last):

| 形状 | walker 产量 | 选择结果 |
| --- | --- | --- |
| A 501 个测试文件，importer 排第 501 个 | 500 | [] |
| B 501 个测试文件，没有 importer | 500 | [] |
| C 500 个测试文件，importer 排第 500 个（对照） | 500 | [importer] |
| D 小目录，importer 在内（对照） | 1 | [importer] |

The fix makes ``_test_files`` a pure walker and moves the budget to the
reader: ``relevant_python_tests`` refuses (``ValueError``) when the walk
would stop before the directory ends.  A refusal is not a shrunken list -
the caller turns it into a blocked verification with the message, or runs
the full regression instead.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from minicc.agent.test_selection import _test_files, relevant_python_tests
from minicc.agent.verification_plan import build_verification_plan

CHANGED = "src/package/module.py"
GOOD = "from package.module import Thing\n"


def _workspace(root: Path) -> Path:
    workspace = root / "ws"
    (workspace / "src" / "package").mkdir(parents=True)
    (workspace / "src" / "package" / "__init__.py").write_text("", encoding="utf-8")
    (workspace / "src" / "package" / "module.py").write_text("Thing = 1\n", encoding="utf-8")
    (workspace / "tests").mkdir()
    return workspace


def _fill(workspace: Path, count: int) -> None:
    tests = workspace / "tests"
    for index in range(count):
        (tests / f"test_filler_{index:04d}.py").write_text("value = 1\n", encoding="utf-8")


def _importer(workspace: Path) -> Path:
    importer = workspace / "tests" / "test_zzz_importer.py"
    importer.write_text(GOOD, encoding="utf-8")
    return importer


@pytest.fixture(scope="module")
def large_501(tmp_path_factory: pytest.TempPathFactory) -> Path:
    workspace = _workspace(tmp_path_factory.mktemp("large501"))
    _fill(workspace, 500)
    _importer(workspace)
    return workspace


@pytest.fixture(scope="module")
def large_500(tmp_path_factory: pytest.TempPathFactory) -> Path:
    workspace = _workspace(tmp_path_factory.mktemp("large500"))
    _fill(workspace, 499)
    _importer(workspace)
    return workspace


def test_the_walker_yields_every_test_file(large_501: Path) -> None:
    found = [path.name for path in _test_files(large_501 / "tests")]
    assert len(found) == 501, f"walker 只走了 {len(found)} 个测试文件，目录里有 501 个"
    assert found[-1] == "test_zzz_importer.py", found[-3:]


def test_a_directory_past_the_scan_window_is_refused(large_501: Path) -> None:
    with pytest.raises(ValueError, match="500"):
        relevant_python_tests(large_501, [CHANGED])


def test_the_plan_refuses_a_directory_past_the_scan_window(large_501: Path) -> None:
    with pytest.raises(ValueError, match="500"):
        build_verification_plan(large_501, [CHANGED])


def test_the_control_the_last_file_inside_the_window_is_selected(large_500: Path) -> None:
    selected = relevant_python_tests(large_500, [CHANGED])
    assert selected == ["tests/test_zzz_importer.py"], (
        f"第 500 个（窗口内最后一个）测试文件被丢掉了：{selected}"
    )


def test_the_control_a_small_directory_still_selects_the_importer(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    (workspace / "tests" / "test_unrelated.py").write_text("value = 1\n", encoding="utf-8")
    _importer(workspace)
    selected = relevant_python_tests(workspace, [CHANGED])
    assert selected == ["tests/test_zzz_importer.py"], selected


def test_the_control_a_small_directory_without_an_importer_selects_nothing(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    (workspace / "tests" / "test_unrelated.py").write_text("value = 1\n", encoding="utf-8")
    assert relevant_python_tests(workspace, [CHANGED]) == []
