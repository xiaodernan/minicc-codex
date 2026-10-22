"""M8-T369 — 一个模块里，同一个顶层名字不许被定义两次

**一个事实两个家，等于这个事实没有主人。** ✓

`minicc/session.py` 曾经把 `list_sessions` 定义了**两次** ✓：一次在文件前部
（读者先遇到的那份）✓，一次在文件末尾 ✓。两份函数体**逐字节相同** ✓，所以
运行时**看不出任何异常** ✓——但 Python 只保留**后定义**的那份 ✓，于是：

* 维护者按阅读顺序改**前一份** ✓ → **改动静默失效** ✓（改的是死代码 ✓）；
* 事实变成两份 ✓ → 迟早漂移 ✓（M8-T277 那次修正就得**同时改两处** ✓，
  否则行为取决于改的是哪一份 ✓）。

这一批的做法 ✓：删掉末尾那份 ✓（已证明与前一份的**字节码、consts、names、
doc、可观察输出**全等 ✓，所以是**零行为变化**的删除 ✓），并把这条纪律写成
**类级门禁** ✓——**任何**模块的**任何**顶层名字只许有一个家 ✓。

门禁是**结构断言** ✓（用 AST 数顶层定义的个数 ✓，不看文本 ✓）：把末尾那份
复制回去 ✓ → 名字计数变成 2 ✓ → 红 ✓。
"""

from __future__ import annotations

import ast
from pathlib import Path

#: The package's own modules - the ones that ship to users.
PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "minicc"


def _top_level_definitions(path: Path) -> list[tuple[str, int]]:
    """Every name a module defines at *module* scope, with its line number.

    A ``def``/``class``/assignment at module scope is what a reader (and
    ``from module import name``) meets.  Names defined *inside* a function or
    a class are a different scope and are not counted: two methods with the
    same name in one class body are legal when they are a property and its
    setter, and two locals in two functions never meet.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return []
    found: list[tuple[str, int]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.append((node.name, node.lineno))
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    found.append((target.id, node.lineno))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            found.append((node.target.id, node.lineno))
    return found


def test_no_module_defines_the_same_top_level_name_twice() -> None:
    """Every module-scope name in the package has exactly one home."""
    offenders: list[str] = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        seen: dict[str, int] = {}
        for name, lineno in _top_level_definitions(path):
            if name in seen:
                offenders.append(
                    f"{path.relative_to(PACKAGE_ROOT.parent)}:{name} "
                    f"defined at lines {seen[name]} and {lineno}"
                )
            else:
                seen[name] = lineno
    assert not offenders, (
        "these module-scope names are defined twice in one module; the second "
        "definition silently shadows the first, so a maintainer who edits the "
        "one they meet first changes nothing at all: "
        + "; ".join(offenders)
    )


def test_the_session_listing_has_exactly_one_home() -> None:
    """The concrete case this batch fixed (M8-T369).

    An identity assertion cannot prove "there is no second copy" - the
    import binds *one* object no matter how many definitions there were.
    The count of definitions is the observable fact, so that is what this
    gate reads.
    """
    path = PACKAGE_ROOT / "session.py"
    definitions = [name for name, _ in _top_level_definitions(path) if name == "list_sessions"]
    assert len(definitions) == 1, (
        f"minicc/session.py defines list_sessions {len(definitions)} times; "
        "the extra copy is dead code that hides real edits"
    )


def test_the_one_home_is_the_one_python_keeps() -> None:
    """The surviving definition must be the one the module actually exports.

    This is what makes the deletion safe *and* meaningful: the exported
    function is the first (and only) definition in the file, so the copy a
    reader meets is the copy that runs.
    """
    import minicc.session as session_module

    source = (PACKAGE_ROOT / "session.py").read_text(encoding="utf-8")
    first_line = source.splitlines().index("def list_sessions(workspace: Path) -> list[dict[str, Any]]:")
    exported_line = session_module.list_sessions.__code__.co_firstlineno - 1
    assert exported_line == first_line, (
        "the exported list_sessions is not the first definition in the file "
        f"(file line {first_line + 1} vs exported line {exported_line + 1}); "
        "a reader who edits the first copy must be editing the one that runs"
    )
