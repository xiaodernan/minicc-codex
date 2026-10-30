"""M8-T551: a test file that could not be read is not an unrelated test.

``relevant_python_tests`` decides which test files the verification plan runs
by parsing their imports.  When the read or the parse failed
(``OSError``/``UnicodeError``/``SyntaxError``) the file was skipped — the
same answer as a test that imports nothing relevant.  Measured on HEAD through
``relevant_python_tests`` and ``build_verification_plan`` (changed file:
``src/package/module.py``):

| 形状 | 选择结果 | 计划命令 |
| --- | --- | --- |
| A 可读 importer + 语法坏 importer | 只有可读那个 | 只跑可读那个 |
| B 可读 importer + 非 UTF-8 importer | 只有可读那个 | 只跑可读那个 |
| C 可读 importer + 读取抛 OSError 的 importer | 只有可读那个 | 只跑可读那个 |
| D 可读、但 import 不相关（对照） | 只有可读那个 | — |
| E 文件名匹配（对照） | 被选中 | — |
| F 超过 250KB 的可读 importer | 不选（尺寸策略） | — |
| G 没有 tests 目录（对照） | 空 | — |

A file whose imports cannot be read **may import the changed module** — that
is exactly what could not be checked.  Dropping it shrank the verification
silently; the selection now keeps it, so pytest reports the file's own
failure instead of a green run that never looked at it.  The 250KB skip stays
a deliberate size policy, disclosed in the record, not a failed read.
"""

from __future__ import annotations

import pathlib
from pathlib import Path

from minicc.agent.test_selection import relevant_python_tests
from minicc.agent.verification_plan import build_verification_plan

CHANGED = "src/package/module.py"
GOOD = "from package.module import Thing\n"


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "ws"
    (workspace / "src" / "package").mkdir(parents=True)
    (workspace / "src" / "package" / "__init__.py").write_text("", encoding="utf-8")
    (workspace / "src" / "package" / "module.py").write_text("Thing = 1\n", encoding="utf-8")
    (workspace / "tests").mkdir()
    return workspace


def _planned(workspace: Path) -> str:
    plan = build_verification_plan(workspace, [CHANGED])
    return next((command.command for command in plan.commands if "pytest" in command.command), "")


def test_a_syntax_broken_importer_is_not_dropped(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    (workspace / "tests" / "test_good.py").write_text(GOOD, encoding="utf-8")
    (workspace / "tests" / "test_broken.py").write_text(
        "from package.module import Thing\n\ndef broken(:\n", encoding="utf-8"
    )
    selected = relevant_python_tests(workspace, [CHANGED])
    assert selected == ["tests/test_broken.py", "tests/test_good.py"], (
        f"读不出来的测试文件被当成与改动无关：{selected}"
    )


def test_an_invalid_utf8_importer_is_not_dropped(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    (workspace / "tests" / "test_good.py").write_text(GOOD, encoding="utf-8")
    (workspace / "tests" / "test_bytes.py").write_bytes(
        "from package.module import Thing\n".encode("utf-8") + b"\xff\xfe\n"
    )
    selected = relevant_python_tests(workspace, [CHANGED])
    assert selected == ["tests/test_bytes.py", "tests/test_good.py"], selected


def test_an_unreadable_importer_is_not_dropped(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace(tmp_path)
    (workspace / "tests" / "test_good.py").write_text(GOOD, encoding="utf-8")
    denied = workspace / "tests" / "test_denied.py"
    denied.write_text(GOOD, encoding="utf-8")

    real = pathlib.Path.read_text

    def read_text(self, *args, **kwargs):
        if Path(self) == denied:
            raise PermissionError("denied")
        return real(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "read_text", read_text)
    selected = relevant_python_tests(workspace, [CHANGED])
    assert selected == ["tests/test_denied.py", "tests/test_good.py"], selected


def test_the_plan_runs_the_file_it_could_not_read(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    (workspace / "tests" / "test_broken.py").write_text(
        "from package.module import Thing\n\ndef broken(:\n", encoding="utf-8"
    )
    command = _planned(workspace)
    assert "tests/test_broken.py" in command, (
        f"验证计划把一个读不出来的测试文件从命令里悄悄删掉了：{command!r}"
    )


def test_the_control_a_readable_unrelated_importer_stays_out(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    (workspace / "tests" / "test_good.py").write_text(GOOD, encoding="utf-8")
    (workspace / "tests" / "test_unrelated.py").write_text("import json\n", encoding="utf-8")
    assert relevant_python_tests(workspace, [CHANGED]) == ["tests/test_good.py"]


def test_the_control_a_filename_match_is_still_selected(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    (workspace / "tests" / "test_module.py").write_text("x = 1\n", encoding="utf-8")
    assert relevant_python_tests(workspace, [CHANGED]) == ["tests/test_module.py"]


def test_the_control_no_tests_directory_is_still_empty(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    (workspace / "tests").rmdir()
    assert relevant_python_tests(workspace, [CHANGED]) == []


def test_the_control_the_size_policy_is_unchanged(tmp_path: Path) -> None:
    """A >250KB test file is skipped by policy, not by a failed read."""
    workspace = _workspace(tmp_path)
    (workspace / "tests" / "test_big.py").write_text(
        GOOD + "# " + "p" * 300_000 + "\n", encoding="utf-8"
    )
    assert relevant_python_tests(workspace, [CHANGED]) == []
