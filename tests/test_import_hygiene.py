"""M8-T69: a module must not use a stdlib name it never imported.

This class of defect was stepped in twice while adding readiness probes to the
HTTP fixtures (batches 52 and 53): the probe called ``time.monotonic()`` in a
module without ``import time``.  Python only answers at *runtime*, so the first
report a reviewer sees is a page of NameErrors from an unrelated test.  The
check itself is cheap enough to run at collection time, which is where it
belongs.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Only names in this table are answered for; a base outside it is ignored so a
# locally shadowed name (a variable called ``json``) cannot invent a violation.
STDLIB_BASES = {
    "argparse", "asyncio", "base64", "copy", "csv", "dataclasses", "hashlib", "http",
    "importlib", "io", "json", "logging", "math", "os", "pathlib", "pickle", "queue",
    "random", "re", "shutil", "socket", "sqlite3", "string", "subprocess", "sys",
    "tempfile", "threading", "time", "traceback", "types", "unicodedata", "urllib",
    "uuid", "zoneinfo",
}


def _imported_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def _bound_names(tree: ast.Module) -> set[str]:
    """Plain variables, parameters, defs, classes and except aliases."""
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            bound.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                arguments = node.args
                bound.update(a.arg for a in arguments.args)
                bound.update(a.arg for a in arguments.kwonlyargs)
                if arguments.posonlyargs:
                    bound.update(a.arg for a in arguments.posonlyargs)
                if arguments.vararg:
                    bound.add(arguments.vararg.arg)
                if arguments.kwarg:
                    bound.add(arguments.kwarg.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
    return bound


def missing_imports(source: str) -> set[str]:
    """Stdlib bases read as ``base.attr`` that the module neither imports nor binds."""
    tree = ast.parse(source)
    readable = _imported_names(tree) | _bound_names(tree)
    return {
        node.value.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id in STDLIB_BASES
        and node.value.id not in readable
    }


def _modules() -> list[Path]:
    roots = [ROOT / "tests", ROOT / "minicc", ROOT / "scripts"]
    files: list[Path] = []
    for root in roots:
        files.extend(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)
    return sorted(set(files))


def test_the_scanner_answers_both_ways_on_synthetic_source() -> None:
    # The gate is only worth shipping if a missing import is what it reports.
    assert missing_imports("import os\nprint(os.sep)\n") == set()
    assert missing_imports("import time as clock\nprint(clock.monotonic())\n") == set()
    assert missing_imports("import os.path\nprint(os.path.join('a'))\n") == set()
    assert missing_imports("def run(time):\n    return time.time()\n") == set(), (
        "a parameter shadowing the module name is not a missing import"
    )
    assert missing_imports("print(time.monotonic())\n") == {"time"}
    assert missing_imports("import os\nprint(os.sep, time.monotonic(), json.dumps({}))\n") == {"time", "json"}


def test_no_module_reads_a_stdlib_name_it_does_not_import() -> None:
    files = _modules()
    assert files, "the scan found nothing to read — the roots moved"
    offenders = {
        str(path.relative_to(ROOT)): sorted(missing_imports(path.read_text(encoding="utf-8")))
        for path in files
    }
    reported = {name: bases for name, bases in offenders.items() if bases}
    assert not reported, f"modules using a stdlib name they never import: {reported!r}"
    assert len(files) > 100, f"the scan should cover the whole repo, saw {len(files)} files"
