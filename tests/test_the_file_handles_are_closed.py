"""M8-T531 — 套件的文件句柄不许留给回收器

``f2f2af5`` 的全量围栏在 ``-W error`` 下报了两条红、却只算一次泄漏：
``test_the_task_stream_length_has_one_meaning.py`` 里的一条门写了
``open("minicc/task_manager.py").read()``——表达式结束时没有任何人持有句柄，
只能等 GC。回收发生在**下一个**测试里，于是外层 ``TextIOWrapper`` 走
``-W error`` 的警告通道、怀里的 ``FileIO`` 走 pytest 的 unraisable 通道，
同一条泄漏被记了两次账，两次都不在漏它的那条门上。

本门做两件事：

1. 结构：``minicc/``、``scripts/``、``tests/`` 三棵树里，``open(...)`` 的结果
   不许**当场被消费**（``open(p).read()``、``open(p)[0]``）——那个表达式里没有
   任何东西能关它。放进 ``with`` 或赋给变量都可以：仓里现存的 6 处全是后者
   （锁与「邻居握着暂存名」的场景要靠握着句柄）。
2. 机制：同两条写法各起一个子进程，``-W error::ResourceWarning`` 加一次强制
   ``gc.collect()``，读的是**子进程的 stderr**：当场消费的那条必须报
   ``unclosed file``，``read_text`` 的那条必须一个字都不报。注意前者的退出码
   仍是 0——``ResourceWarning`` 在析构里被吞成 ``Exception ignored``，所以
   断言不许押在退出码上。探测器的自检也在这里：一段故意写坏的源码必须被点名，
   一段握在手里的不许被点名。
"""

from __future__ import annotations

import ast
import os
import pathlib
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
ROOTS = ("minicc", "scripts", "tests")


def _inline_consumption(tree: ast.AST) -> list[tuple[int, str]]:
    """``open(...)`` calls whose result is consumed inside the same expression."""
    parent: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[child] = node
    sites: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "open"
        ):
            continue
        holder = parent.get(node)
        if isinstance(holder, ast.Attribute) and holder.value is node:
            sites.append((node.lineno, "." + holder.attr))
        elif isinstance(holder, ast.Subscript) and holder.value is node:
            sites.append((node.lineno, "[...]"))
    return sites


def test_no_open_result_is_consumed_inside_its_own_expression() -> None:
    walked = 0
    offenders: list[str] = []
    for root in ROOTS:
        for path in sorted((REPO_ROOT / root).rglob("*.py")):
            walked += 1
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for line, access in _inline_consumption(tree):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{line} (open(...){access})")
    assert walked >= 500, (
        f"the walker saw only {walked} Python files under {', '.join(ROOTS)}; "
        "a shrinking population makes 'no offender' cheap"
    )
    assert offenders == [], (
        "an open() handle is consumed inside the expression that creates it, so nothing "
        "closes it and the collector reports the leak against whichever test runs next: "
        + "; ".join(offenders)
    )


def test_the_detector_names_a_leak_and_spares_a_held_handle() -> None:
    leak = ast.parse('src = open("x", encoding="utf-8").read()\n')
    assert _inline_consumption(leak) == [(1, ".read")], (
        "the detector did not name an inline read; the structural gate above would be deaf"
    )
    held = ast.parse('handle = open("x", encoding="utf-8")\nhandle.close()\n')
    assert _inline_consumption(held) == [], (
        "a handle someone holds is not this gate's business"
    )
    context = ast.parse('with open("x", encoding="utf-8") as handle:\n    handle.read()\n')
    assert _inline_consumption(context) == [], (
        "a with-statement closes its handle; it is not this gate's business either"
    )


def _child(code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-W", "error::ResourceWarning", "-c", code],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=dict(os.environ, PYTHONIOENCODING="utf-8"),
        timeout=60,
    )


def test_the_leak_and_the_closed_idiom_differ_in_the_childs_stderr(tmp_path: pathlib.Path) -> None:
    target = tmp_path / "payload.txt"
    target.write_text("x\n", encoding="utf-8")
    leaked = _child(
        "import gc\n"
        f"open({str(target)!r}, encoding='utf-8').read()\n"
        "gc.collect()\n"
    )
    assert "unclosed file" in leaked.stderr, (
        "the child did not report the inline open as an unclosed file; this witness "
        "cannot tell a leak from a closed handle "
        f"(rc={leaked.returncode}, stderr={leaked.stderr!r})"
    )
    closed = _child(
        "import gc\n"
        "from pathlib import Path\n"
        f"Path({str(target)!r}).read_text(encoding='utf-8')\n"
        "gc.collect()\n"
    )
    assert closed.returncode == 0, closed.stderr
    assert closed.stderr.strip() == "", (
        "the read_text idiom reported something; the leak witness above proves nothing "
        f"unless the closed form is silent (stderr={closed.stderr!r})"
    )
