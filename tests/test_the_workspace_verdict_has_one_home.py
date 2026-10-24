"""M8-T492 — 工作区判词两个家：CLI 与 Web 入口各拼一句

「工作区不是目录: X」有两个家：CLI 入口（``main.main``，`_fatal` 退出）与
Web 入口（``web.main``，`parser.error` 退出）。两个入口解析同一个
``--workspace``、拒绝同一种错误，句子却各拼一遍——一个入口改了措辞另一
个没跟上，就是同一件事在两个入口读到两句话。

家安在 `minicc/config.py`，紧挨 `home_dir`——工作区/配置根目录的解析本来就
住在这里。失败方式不同（退出码一个走 `_fatal` 一个走 argparse），所以家
只拥有**措词**，每个入口保留自己的退出路径。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/config.py"
CLI = "minicc/main.py"
WEB = "minicc/web.py"
VERDICT = "工作区不是目录"


def _sites(fragment: str) -> list[str]:
    found: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if fragment in node.value:
                    found.append(f"{path.relative_to(REPO).as_posix()}:{node.lineno}")
    return found


def test_the_home_pins_the_sentence() -> None:
    from minicc.config import workspace_not_directory_message

    assert workspace_not_directory_message(Path("my ws")) == "工作区不是目录: my ws"


def test_the_verdict_is_spelled_exactly_once_in_the_package() -> None:
    offenders = _sites(VERDICT)
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the workspace verdict is spelled by hand outside its one home: "
        + ", ".join(offenders)
    )


def test_both_entries_ask_the_home() -> None:
    cli = (REPO / CLI).read_text(encoding="utf-8")
    web = (REPO / WEB).read_text(encoding="utf-8")
    assert cli.count("workspace_not_directory_message(") == 1, (
        "the CLI entry must ask the home"
    )
    assert web.count("workspace_not_directory_message(") == 1, (
        "the web entry must ask the home"
    )


def test_both_entries_share_one_object() -> None:
    from minicc import main as cli_main
    from minicc import web
    from minicc.config import workspace_not_directory_message

    assert cli_main.workspace_not_directory_message is workspace_not_directory_message
    assert web.workspace_not_directory_message is workspace_not_directory_message


def test_the_cli_entry_refuses_with_the_homes_sentence(
    tmp_path: Path, capsys
) -> None:
    from minicc.config import workspace_not_directory_message
    from minicc.main import main

    missing = tmp_path / "nope"
    with pytest.raises(SystemExit) as excinfo:
        main(["--workspace", str(missing)])
    assert excinfo.value.code == 2
    assert f"minicc: {workspace_not_directory_message(missing)}" in capsys.readouterr().err


def test_the_web_entry_refuses_with_the_homes_sentence(
    tmp_path: Path, capsys
) -> None:
    from minicc.config import workspace_not_directory_message
    from minicc.web import main as web_main

    missing = tmp_path / "nope"
    with pytest.raises(SystemExit) as excinfo:
        web_main(["--workspace", str(missing)])
    assert excinfo.value.code == 2
    assert workspace_not_directory_message(missing) in capsys.readouterr().err
