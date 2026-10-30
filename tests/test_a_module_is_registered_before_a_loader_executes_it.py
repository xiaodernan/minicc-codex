"""M8-T543: a module executed without registration is reported as a broken module.

``spec.loader.exec_module(module)`` runs a module's body without entering the
module in ``sys.modules``. With ``from __future__ import annotations`` every
annotation is a string, and ``dataclasses`` resolves those strings through
``sys.modules[cls.__module__]`` while the class is being built. A module that
defines a dataclass therefore dies with ``AttributeError: 'NoneType' object has
no attribute '__dict__'`` when it is executed before it is registered - a
finding about the loader, published as a finding about the script.

Thirteen loaders in ``tests/`` execute a script by hand. Twelve registered the
module first; ``test_impacted_tests.py`` did not, and T542 spent a batch
choosing a ``NamedTuple`` over a slots dataclass because the script appeared
not to survive being loaded. The script was never the problem.

Three legs:

1. every ``exec_module`` call under ``tests/`` registers the module it executes
   under that module's own name, before executing it;
2. the loader that lacked the line loads a script that defines a dataclass;
3. the control - a body executed while absent from ``sys.modules`` raises - so
   the rule guards a failure that exists, not a style preference.
"""
from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TESTS = REPO_ROOT / "tests"

DATACLASS_SCRIPT = '''\
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Reading:
    name: str
    count: int = 0
'''


def _enclosing_scope(tree: ast.Module, call: ast.Call) -> list[ast.stmt]:
    """The body of the innermost function around ``call``, or the module body."""
    best: ast.FunctionDef | ast.AsyncFunctionDef | None = None
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.lineno <= call.lineno <= (node.end_lineno or node.lineno):
            if best is None or node.lineno >= best.lineno:
                best = node
    return best.body if best is not None else tree.body


def _own_nodes(statements: list[ast.stmt]):
    """Every node under ``statements`` except the bodies of nested definitions."""
    stack = list(statements)
    while stack:
        node = stack.pop()
        yield node
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                continue
            stack.append(child)


def _registers_first(scope: list[ast.stmt], call: ast.Call, module_name: str) -> bool:
    for node in _own_nodes(scope):
        line = getattr(node, "lineno", call.lineno)
        if line >= call.lineno:
            continue
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        if not (isinstance(value, ast.Name) and value.id == module_name):
            continue
        for target in targets:
            if not (isinstance(target, ast.Subscript)
                    and isinstance(target.value, ast.Attribute)
                    and isinstance(target.value.value, ast.Name)
                    and target.value.value.id == "sys"
                    and target.value.attr == "modules"):
                continue
            key = target.slice
            if isinstance(key, ast.Attribute) and key.attr == "name":
                return True
    return False


def _loader_findings(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    findings = []
    for call in ast.walk(tree):
        if not (isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr == "exec_module"):
            continue
        if len(call.args) != 1 or not isinstance(call.args[0], ast.Name):
            findings.append(f"{path.name}:{call.lineno}: exec_module does not name the module it runs")
            continue
        module_name = call.args[0].id
        if not _registers_first(_enclosing_scope(tree, call), call, module_name):
            findings.append(f"{path.name}:{call.lineno}: executes {module_name} "
                            "without registering it in sys.modules")
    return findings


def test_every_loader_registers_the_module_before_it_executes_it() -> None:
    files = sorted(TESTS.glob("*.py"))
    assert len(files) >= 400, f"only {len(files)} test files scanned - the census saw nothing"
    findings = [finding for path in files for finding in _loader_findings(path)]
    assert findings == [], findings


def _load_by_path(name: str, path: Path) -> object:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_the_loader_that_skipped_the_registration_loads_a_dataclass(tmp_path, monkeypatch) -> None:
    script = tmp_path / "a_script_with_a_dataclass.py"
    script.write_text(DATACLASS_SCRIPT, encoding="utf-8")
    loader = _load_by_path("minicc_impacted_tests_loader_t543", TESTS / "test_impacted_tests.py")
    monkeypatch.setattr(loader, "SCRIPT", script)
    loaded = loader._load_script()
    reading = loaded.Reading("one", 1)
    assert (reading.name, reading.count) == ("one", 1)


def test_a_body_executed_without_registration_reports_its_own_class_as_broken() -> None:
    name = "minicc_unregistered_control_t543"
    assert name not in sys.modules
    namespace = {"__name__": name, "__file__": "<synthetic>"}
    with pytest.raises(AttributeError, match="__dict__"):
        exec(compile(DATACLASS_SCRIPT, "<synthetic>", "exec"), namespace)
