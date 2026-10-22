"""M8-T366 / M8-T367 — 两条**只在另一条腿上才炸**的门禁纪律

**一、测试模块不许无条件 import Windows 专有模块**（M8-T366 ✓）

CI 有两条腿 ✓：Windows ✓ 与 Ubuntu ✓。一个测试模块在**模块层** import 了
Windows 专有模块 ✓（`msvcrt` ✓ / `winreg` ✓ / …）→ 在 Ubuntu 上**收集阶段**就死
✓ → 整条腿红 ✓✓（而 Windows 那条腿一路绿 ✓✓——所以这种失败很容易被"本机全绿"
掩盖 ✓）。

实测代价 ✓：`tests/test_the_session_sidecar_lock_waits_no_longer_than_its_own_constants_promise.py`
无条件 `import msvcrt` ✓ → Ubuntu 腿每次都死在
`ModuleNotFoundError: No module named 'msvcrt'` ✓，**连续多批提交都是红的** ✓，
而 Windows 腿全绿 ✓✓——**红灯只出现在 CI 的另一条腿上** ✓。

**二、只有 `communicate()` 能关子进程的 stdin**（M8-T367 ✓）

一个测试先 `proc.stdin.close()` ✓，随后 `proc.communicate()` ✓ 去 flush 那个**已经
关闭**的流 ✓ → POSIX 上抛 `ValueError: I/O operation on closed file` ✓（Windows 上
被容忍 ✓）→ 又是一条"**只在另一条腿上炸**"的失败 ✓。

两条纪律合起来 ✓：**"本机全绿"不等于"CI 全绿"** ✓——而 CI 的第二条腿**就是**这条
纪律的门禁 ✓✓。

本门钉住：测试目录里**没有任何模块**在模块层无条件 import Windows 专有模块 ✓；
**没有任何测试**自己去关 `Popen` 的 stdin ✓（`communicate()` 负责 ✓）。
"""

from __future__ import annotations

import ast
from pathlib import Path

#: Modules that only exist on Windows.  A test that needs one must either
#: import it inside a platform guard or skip itself with ``importorskip``.
WINDOWS_ONLY_MODULES = frozenset({
    "msvcrt",
    "winreg",
    "win32api",
    "win32com",
    "win32con",
    "win32evtlog",
    "win32file",
    "win32gui",
    "win32process",
    "win32security",
    "winsound",
    "msi",
    "nt",
    "pywintypes",
    "wincertstore",
    "win32pdh",
    "win32service",
    "winerror",
    "isapi",
})


def _top_level_imports(path: Path) -> set[str]:
    """The module names a file imports at the top level, unconditionally."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return set()
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def _closes_a_popen_stdin(path: Path) -> bool:
    """Whether the file closes a Popen's stdin itself."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "close":
            continue
        target = func.value
        if (
            isinstance(target, ast.Attribute)
            and target.attr == "stdin"
        ):
            return True
    return False


def test_no_test_module_imports_a_windows_only_module() -> None:
    root = Path(__file__).resolve().parents[1] / "tests"
    offenders: list[str] = []
    for path in sorted(root.glob("*.py")):
        imported = _top_level_imports(path)
        windows_only = sorted(imported & WINDOWS_ONLY_MODULES)
        if windows_only:
            offenders.append(f"{path.name}: {', '.join(windows_only)}")
    assert not offenders, (
        "these test modules import a Windows-only module at the top level, so the "
        "POSIX leg of CI dies during collection while the Windows leg stays green: "
        + "; ".join(offenders)
    )


def test_no_test_closes_a_popen_stdin_itself() -> None:
    """Only ``communicate()`` may close the child's stdin (M8-T367)."""
    root = Path(__file__).resolve().parents[1] / "tests"
    offenders = [path.name for path in sorted(root.glob("*.py")) if _closes_a_popen_stdin(path)]
    assert not offenders, (
        "these tests close a Popen's stdin themselves; the later communicate() "
        "flushes that closed stream and raises 'I/O operation on closed file' on "
        "POSIX (Windows tolerates it), so the failure only shows up on one CI leg: "
        + ", ".join(offenders)
    )
