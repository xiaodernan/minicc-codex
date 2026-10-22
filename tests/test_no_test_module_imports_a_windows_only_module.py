"""M8-T366 — 任何测试模块都不许**无条件** import Windows 专有模块

CI 有两条腿 ✓：Windows ✓ 与 Ubuntu ✓。一个测试模块在**模块层** import 了
Windows 专有模块 ✓（`msvcrt` ✓ / `winreg` ✓ / …）→ 在 Ubuntu 上**收集阶段**就死
✓ → 整条腿红 ✓✓（而 Windows 那条腿一路绿 ✓✓——所以这种失败很容易被"本机全绿"
掩盖 ✓）。

实测代价 ✓：`tests/test_the_session_sidecar_lock_waits_no_longer_than_its_own_constants_promise.py`
无条件 `import msvcrt` ✓ → Ubuntu 腿每次都死在
`ModuleNotFoundError: No module named 'msvcrt'` ✓，**连续多批提交都是红的** ✓，
而 Windows 腿全绿 ✓✓——**红灯只出现在 CI 的另一条腿上** ✓。

本门钉住：测试目录里**没有任何模块**在模块层无条件 import Windows 专有模块 ✓
（条件 import ✓ / `pytest.importorskip` ✓ 都算数 ✓）——这一条让"只在本机绿"的
失败**在提交前就红** ✓✓。
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
