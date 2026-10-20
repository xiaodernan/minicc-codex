"""M8-T311 — 解释器跑**内联代码**时，那次调用就是一次可能改写工作区的调用

`command_may_modify_workspace` 的 docstring 写着两句：

> Conservative: True when a bash command could rewrite the workspace.
> Over-reporting only forces an extra verification pass; under-reporting lets
> a real write skip the verifier, so the heuristic errs toward True.

而它的实现里有一段与这两句话**矛盾**的代码：

```python
if program in _INTERPRETERS:
    flags = {tok for tok in rest if tok.startswith("-")}
    # ``-c``/``-m`` run inline code or a module, not a workspace script.
    if "-c" in flags or "-m" in flags:
        continue
```

"内联代码不是工作区里的脚本"说的是**代码从哪来**，不是**它会不会写**。
于是：

* `python -c "open('f','w').write('x')"` → **不算写**
* `node -e "fs.writeFileSync('f','x')"` → **不算写**
* `bash -c "rm -rf build"` → **不算写**

后果与 M8-T308 的 `sed -i` **完全同形**：一次真实的写入被报告成"没有写入" →
验证阶段被跳过 → 任务在没有检查的情况下被认证；而检查点还会把它标成
`safe_readonly`（"这个任务没改过东西"）。

`-m` 则是**故意**不动的：一个模块的 main 通常是检查器，而检查留下的产物
不是输入（M8-T280）——所以 `python -m pytest` 仍然不是写。

本门禁钉住：内联代码是写；`-m` 不是；普通读命令仍然不是。
"""

from __future__ import annotations

import pytest

from minicc.agent.tool_policy import command_may_modify_workspace, is_workspace_write


@pytest.mark.parametrize(
    "command",
    [
        "python -c \"open('f.py','w').write('x')\"",
        "python3 -c \"open('f.py','w').write('x')\"",
        "node -e \"require('fs').writeFileSync('f.js','x')\"",
        "node --eval \"require('fs').writeFileSync('f.js','x')\"",
        "ruby -e \"File.write('f.rb','x')\"",
        "perl -e \"open(F,'>','f.pl'); print F 'x'\"",
        "php -r \"file_put_contents('f.php','x');\"",
        "bash -c \"rm -rf build\"",
        "sh -c \"echo x > f.txt\"",
    ],
)
def test_inline_code_may_rewrite_the_workspace(command: str) -> None:
    """The function's own contract: it errs toward True."""
    assert command_may_modify_workspace(command) is True, (
        f"inline code was reported as a non-write: {command!r}"
    )


@pytest.mark.parametrize(
    "command",
    [
        "python -m pytest -q",
        "python -m mypy pkg",
        'node --check "app.js"',
        "cat app.py",
        "pytest tests/",
        "ls -la",
    ],
)
def test_the_checkers_and_reads_are_still_not_writes(command: str) -> None:
    """The control: the artefacts a check leaves behind are not inputs."""
    assert command_may_modify_workspace(command) is False, command


def test_a_node_script_is_still_a_write() -> None:
    """The control: ``--check`` parses; running the script does not."""
    assert command_may_modify_workspace("node app.js") is True


def test_a_workspace_script_is_still_a_write() -> None:
    """The control: the ordinary path is unchanged."""
    assert command_may_modify_workspace("python patch.py") is True
    assert command_may_modify_workspace("sed -i 's/a/b/' app.py") is True


def test_the_canonical_predicate_agrees() -> None:
    """The same answer through the predicate the loop actually uses."""
    call = {"command": "python -c \"open('f.py','w').write('x')\""}
    assert is_workspace_write("bash", call, "ok") is True
    # A failed call wrote nothing.
    assert is_workspace_write("bash", call, "error") is False
