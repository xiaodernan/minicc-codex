"""M8-T493 — 进程退出标记两个家：bash 与 git 各拼一遍 [exit N]

「[exit N]」是工具摘要里标记「进程非零退出」的前缀，有两个家：
`tools/bash.py` 的失败分支与 `tools/git.py` 的失败分支。模型和事件日志都
读这个标记——一个工具改了写法（`[exit code N]`、`(exit N)`）而另一个没
跟上，就是一类读者在一种工具上再也认不出的状态标记。两个工具**成功**时
的摘要形状各自不同（bash 带时长、git 带命令），那是对的；只有失败标记
是同一个事实。

家安在 `minicc/tools/registry.py`——两个工具本来就都 import 的工具词汇
表家（工具名、脱敏标记都住在这儿）。
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/tools/registry.py"
BASH = "minicc/tools/bash.py"
GIT = "minicc/tools/git.py"
MARKER = "[exit "


def _sites(fragment: str) -> list[str]:
    """Every string literal containing the fragment - f-string parts joined."""
    found: list[str] = []
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
            texts: list[str] = []
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                texts = [node.value]
            elif isinstance(node, ast.JoinedStr):
                texts = [
                    "".join(
                        part.value
                        for part in node.values
                        if isinstance(part, ast.Constant) and isinstance(part.value, str)
                    )
                ]
            for text in texts:
                if fragment in text:
                    found.append(f"{path.relative_to(REPO).as_posix()}:{node.lineno}")
    return found


def test_the_home_pins_the_marker() -> None:
    from minicc.tools.registry import exit_marker

    assert exit_marker(1) == "[exit 1]"
    assert exit_marker(127) == "[exit 127]"


def test_the_marker_is_spelled_exactly_once_in_the_package() -> None:
    offenders = _sites(MARKER)
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the exit marker is spelled by hand outside its one home: "
        + ", ".join(offenders)
    )


def test_both_tools_ask_the_home() -> None:
    bash = (REPO / BASH).read_text(encoding="utf-8")
    git = (REPO / GIT).read_text(encoding="utf-8")
    assert bash.count("exit_marker(") == 1, "bash must ask the home"
    assert git.count("exit_marker(") == 1, "git must ask the home"


def test_both_tools_share_one_object() -> None:
    from minicc.tools import bash, git
    from minicc.tools.registry import exit_marker

    assert bash.exit_marker is exit_marker
    assert git.exit_marker is exit_marker


def test_bash_reports_a_failing_command_with_the_homes_marker(tmp_path: Path) -> None:
    from minicc.tools.bash import run_bash
    from minicc.tools.registry import exit_marker

    command = subprocess.list2cmdline(
        [sys.executable, "-c", "import sys; sys.exit(3)"]
    )
    result = run_bash(command, tmp_path, timeout=30)
    assert result.status == "error"
    assert result.exit_code == 3
    assert result.summary.startswith(f"{exit_marker(3)} ("), result.summary
    assert "失败" in result.summary


def test_git_reports_a_failing_command_with_the_homes_marker(tmp_path: Path) -> None:
    from minicc.tools.git import GitTools
    from minicc.tools.registry import exit_marker

    result = GitTools(tmp_path)._run(["rev-parse", "--verify", "no-such-ref-xyz"])
    assert result.status == "error"
    assert result.exit_code != 0
    assert result.summary.startswith(exit_marker(result.exit_code) + " git "), (
        result.summary
    )
