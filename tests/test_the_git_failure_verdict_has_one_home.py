"""M8-T496 — git 命令失败判词三个家：三个 runner 各拼一句

「git 命令失败: X」在 `tools/git.py` 里有三个家：`GitTools._run`、
`merge_precheck`、`_capture`，三处逐字相同。git 表面有三扇门（普通命
令、merge 预检、摘要抓取），模型从哪扇门进去，读到的就是哪份拼写——一处
改了措词其余两处没跟上，没有任何测试会红。

家安在 `minicc/tools/git.py` 模块层，紧挨 `GitTools`——它服务的类。
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/tools/git.py"
VERDICT = "git 命令失败"


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


def test_the_home_pins_the_sentence() -> None:
    from minicc.tools.git import git_command_failed

    exc = OSError("boom")
    assert git_command_failed(exc) == f"git 命令失败: {exc}"


def test_the_verdict_is_spelled_exactly_once_in_the_package() -> None:
    offenders = _sites(VERDICT)
    assert len(offenders) == 1 and offenders[0].startswith(HOME + ":"), (
        "the git-failure verdict is spelled by hand outside its one home: "
        + ", ".join(offenders)
    )


def test_all_three_runners_ask_the_home() -> None:
    source = (REPO / HOME).read_text(encoding="utf-8")
    assert source.count("git_command_failed(") == 4, (
        "the definition plus the three runners are the only spellings, found "
        f"{source.count('git_command_failed(')}"
    )


class _Boom:
    """A subprocess stand-in whose every run times out."""

    TimeoutExpired = subprocess.TimeoutExpired

    @staticmethod
    def run(*args: object, **kwargs: object):
        raise subprocess.TimeoutExpired(cmd="git", timeout=30)


@pytest.fixture()
def timing_out_git(monkeypatch) -> None:
    from minicc.tools import git

    monkeypatch.setattr(git, "subprocess", _Boom)


def test_the_run_runner_raises_the_homes_sentence(
    tmp_path: Path, timing_out_git
) -> None:
    from minicc.tools.git import GitTools, ToolError, git_command_failed

    with pytest.raises(ToolError) as excinfo:
        GitTools(tmp_path)._run(["status"])
    assert str(excinfo.value) == git_command_failed(
        subprocess.TimeoutExpired(cmd="git", timeout=30)
    )


def test_the_merge_precheck_runner_raises_the_homes_sentence(
    tmp_path: Path, timing_out_git
) -> None:
    from minicc.tools.git import GitTools, ToolError, git_command_failed

    with pytest.raises(ToolError) as excinfo:
        GitTools(tmp_path).merge_precheck({"branch": "feature"})
    assert str(excinfo.value) == git_command_failed(
        subprocess.TimeoutExpired(cmd="git", timeout=30)
    )


def test_the_capture_runner_raises_the_homes_sentence(
    tmp_path: Path, timing_out_git
) -> None:
    from minicc.tools.git import GitTools, ToolError, git_command_failed

    with pytest.raises(ToolError) as excinfo:
        GitTools(tmp_path).summary({})
    assert str(excinfo.value) == git_command_failed(
        subprocess.TimeoutExpired(cmd="git", timeout=30)
    )
