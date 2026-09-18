"""Select relevant Python tests using import syntax, without importing code."""
from __future__ import annotations

import ast
import os
import threading
from collections import OrderedDict
from pathlib import Path

_IMPORTS: OrderedDict[str, tuple[tuple[int, int, int], set[str]]] = OrderedDict()
_LOCK = threading.Lock()


def _test_imports(path: Path) -> set[str]:
    stat = path.stat()
    signature = (stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size)
    key = str(path)
    with _LOCK:
        cached = _IMPORTS.get(key)
        if cached and cached[0] == signature:
            _IMPORTS.move_to_end(key)
            return cached[1]
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            imports.add(node.module)
            imports.update(f"{node.module}.{alias.name}" for alias in node.names)
    with _LOCK:
        _IMPORTS[key] = (signature, imports)
        while len(_IMPORTS) > 512:
            _IMPORTS.popitem(last=False)
    return imports


def _test_files(tests: Path):
    count = 0
    for folder, dirs, files in os.walk(tests):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in {"node_modules", "__pycache__"} and not (Path(folder) / d).is_symlink())
        for name in sorted(files):
            if not name.endswith(".py") or not (name.startswith("test_") or name.endswith("_test.py")):
                continue
            yield Path(folder) / name
            count += 1
            if count >= 500:
                return


def relevant_python_tests(root: Path, changed: list[str]) -> list[str]:
    modules: set[str] = set()
    selected: set[str] = set()
    for relative in changed:
        path = Path(relative)
        if path.suffix != ".py":
            continue
        module = path.with_suffix("").as_posix().replace("/", ".")
        modules.add(module)
        if module.startswith("src."):
            modules.add(module[4:])
        if module.endswith(".__init__"):
            modules.add(module[:-9])
        if (path.name.startswith("test_") or path.name.endswith("_test.py")) and (root / path).is_file():
            selected.add(path.as_posix())
        for candidate in (Path("tests") / f"test_{path.stem}.py", path.parent / f"test_{path.stem}.py"):
            if (root / candidate).is_file():
                selected.add(candidate.as_posix())
    if not modules:
        return sorted(selected)
    tests = root / "tests"
    if tests.is_dir():
        for test in _test_files(tests):
            if test.is_symlink() or not test.resolve().is_relative_to(root):
                continue
            try:
                if test.stat().st_size > 250_000:
                    continue
                imports = _test_imports(test)
            except (OSError, UnicodeError, SyntaxError):
                continue
            if modules & imports:
                selected.add(test.relative_to(root).as_posix())
    return sorted(path for path in selected if (root / path).resolve().is_relative_to(root) and not (root / path).is_symlink())
