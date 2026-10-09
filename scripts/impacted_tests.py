#!/usr/bin/env python
"""Which test files can notice a change to a given production module?

M8-T179 exists because of one measurement (第 206 批): a test assertion sat red
for sixty batches because it contradicted a deliberate change made in another
file, and the only reader that would have noticed - a full-suite run - is exactly
what this project stopped doing on purpose. The missing piece was not "run
everything" but "run the files that can see your change".

So this script answers one question, mechanically:

    given these changed paths, which test files import them (directly or through
    the import chain) or name them in a patch target?

It builds the graph from the working tree - ``minicc/`` modules importing each
other, and ``tests/`` files importing or string-referencing them - then inverts
it. Nothing is measured by running anything, so it costs a second, not twelve
minutes.

The floor covers ``scripts/`` too, and there the audience is not only tests:
``reliability_probe.py`` is run by CI, so CI is what notices a change to it.
An audience is an audience; a script nobody runs and nobody tests is the
``minicc/repl`` shape wearing a different hat.

Usage (repo root, any interpreter):

    python scripts/impacted_tests.py                       # uncommitted changes
    python scripts/impacted_tests.py --since HEAD~3        # changes since a ref
    python scripts/impacted_tests.py minicc/bench_tasks.py # explicit paths
    python scripts/impacted_tests.py --run                 # print the pytest command
    python scripts/impacted_tests.py --check               # also gate the floor

The floor: every module under ``minicc/`` must be reachable from at least one
test file, or be listed in ``EXEMPT`` with a reason. A module no test can notice
is a module whose regressions have no audience - the same shape as the
``load_tasks`` door that was a NameError for sixty batches (M8-T177).

Exit code 0 means the impact set was computed (and, with ``--check``, that the
floor holds). Exit 1 means a usage error, a floor violation, or a changed
production module that no test can see.
"""
from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = "minicc"
SCRIPTS = "scripts"
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
STRING_REF = re.compile(r"minicc(?:\.\w+)+")
SCRIPT_REF = re.compile(r"scripts/[\w.-]+\.py")

#: Modules no test reaches, with the reason. An entry without a reason is a bug:
#: the floor exists to be argued with, not to be quietly widened.
EXEMPT: dict[str, str] = {}


def _modules() -> dict[str, Path]:
    found: dict[str, Path] = {}
    for path in sorted((REPO_ROOT / PACKAGE).rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        found[".".join(path.relative_to(REPO_ROOT).with_suffix("").parts)] = path
    return found


def _resolver(modules: dict[str, Path]):
    """Longest-prefix resolution, with package roots answering for their __init__."""
    packages = {name[: -len(".__init__")]: name for name in modules if name.endswith(".__init__")}

    def resolve(dotted: str) -> str | None:
        parts = dotted.split(".")
        while parts:
            candidate = ".".join(parts)
            if candidate in packages:
                return packages[candidate]
            if candidate in modules:
                return candidate
            parts.pop()
        return None

    return resolve


def _imports(path: Path, resolve) -> set[str]:
    """Modules this file imports, relative or absolute, including ``from X import Y``."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError) as exc:  # pragma: no cover - reported by the caller
        raise SystemExit(f"cannot parse {path}: {exc}") from exc
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = resolve(alias.name)
                if name:
                    found.add(name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                prefix = PACKAGE + ("." + node.module if node.module else "")
            elif node.module:
                prefix = node.module
            else:
                continue
            name = resolve(prefix)
            if name:
                found.add(name)
            for alias in node.names:
                nested = resolve(prefix + "." + alias.name)
                if nested:
                    found.add(nested)
    return found


def _test_references(path: Path, resolve) -> set[str]:
    """What a test file reaches: imports plus every ``minicc.x`` string it carries.

    The string half is not decoration. ``monkeypatch.setattr("minicc.web.AgentService", ...)``
    reaches ``minicc.web`` without importing it, and a test that only patches a module
    still notices when that module changes.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    found: set[str] = set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = resolve(alias.name)
                if name:
                    found.add(name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            name = resolve(node.module)
            if name:
                found.add(name)
            for alias in node.names:
                nested = resolve(node.module + "." + alias.name)
                if nested:
                    found.add(nested)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            for mention in STRING_REF.findall(node.value):
                name = resolve(mention)
                if name:
                    found.add(name)
            for mention in SCRIPT_REF.findall(node.value):
                found.add(".".join(Path(mention).with_suffix("").parts))
    return found


def _document_references(name: str, path: Path, resolve) -> set[str]:
    """What one audience document reaches.

    A ``.py`` document is parsed: imports plus the ``minicc.x`` / ``scripts/x.py``
    strings it carries. A workflow is YAML and is read as text, because what it
    references is written as plain strings - ``run: python scripts/x.py`` - and
    parsing YAML as Python is how the first version of this function crashed.
    """
    if name.endswith(".py"):
        return _test_references(path, resolve)
    text = path.read_text(encoding="utf-8", errors="replace")
    found: set[str] = set()
    for mention in STRING_REF.findall(text):
        module = resolve(mention)
        if module:
            found.add(module)
    for mention in SCRIPT_REF.findall(text):
        found.add(".".join(Path(mention).with_suffix("").parts))
    return found


def _closure(seeds: set[str], graph: dict[str, set[str]]) -> set[str]:
    seen: set[str] = set()
    stack = list(seeds)
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(graph.get(current, ()))
    return seen


def _script_modules() -> dict[str, Path]:
    """``scripts/<stem>.py`` as ``scripts.<stem>`` - the CI-facing half of the floor."""
    return {f"{SCRIPTS}.{path.stem}": path
            for path in sorted((REPO_ROOT / SCRIPTS).glob("*.py"))}


def _audience_documents() -> list[tuple[str, Path]]:
    """Everything that can notice a change: the test suite, then the workflows.

    A CI step that runs a script is an audience for that script. Leaving it out
    would have flagged ``reliability_probe.py`` - an M1 exit criterion that has
    gated every push since M1 - as an orphan.
    """
    documents = [(path.name, path) for path in sorted((REPO_ROOT / "tests").glob("*.py"))]
    documents += [(path.name, path) for path in sorted(WORKFLOWS.glob("*.yml"))]
    return documents


def build() -> tuple[dict[str, set[str]], dict[str, set[str]], set[str]]:
    """(audience per module, per-document references, all test files)."""
    modules = _modules()
    resolve = _resolver(modules)
    production = {name: _imports(path, resolve) for name, path in modules.items()}
    documents = _audience_documents()
    references = {name: _document_references(name, path, resolve) for name, path in documents}
    audience: dict[str, set[str]] = {name: set() for name in modules}
    for name in _script_modules():
        audience.setdefault(name, set())
    for document, refs in references.items():
        for module in _closure(refs, production):
            if module in audience:
                audience[module].add(document)
    return audience, references, {name for name, _ in documents if name.endswith(".py")}


def _bound_names(path: Path) -> set[str]:
    """Every name this module binds: imports, defs, classes, assignments."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
    return names


def _promised_names(path: Path) -> set[str] | None:
    """The ``__all__`` of a module, or ``None`` when it declares none."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets
        ):
            return {element.value for element in node.value.elts
                    if isinstance(element, ast.Constant) and isinstance(element.value, str)}
    return None


def verified_facades(modules: dict[str, Path] | None = None) -> set[str]:
    """Package ``__init__`` files whose ``__all__`` is exactly what they bind.

    A pure re-export facade has no behaviour of its own to test, so the floor
    below cannot ask "which test notices a change here" and get a meaningful
    answer. What it *can* ask is the one thing such a file can get wrong: it
    promises names. ``minicc/repl`` - deleted in the batch that introduced this
    script - promised ``Repl`` from a module that has never existed in this
    repository's history, and nothing noticed for two hundred batches because
    nothing imported it.

    A facade earns its exemption by being checked, not by being listed.
    """
    modules = _modules() if modules is None else modules
    verified: set[str] = set()
    for name, path in modules.items():
        if not name.endswith(".__init__"):
            continue
        promised = _promised_names(path)
        if promised is None:
            continue
        if promised and promised <= _bound_names(path):
            verified.add(name)
    return verified


def _changed_paths(since: str | None) -> list[str]:
    if since:
        out = subprocess.run(("git", "-C", str(REPO_ROOT), "diff", "--name-only", since),
                             capture_output=True, text=True, errors="replace", check=False).stdout
    else:
        tracked = subprocess.run(("git", "-C", str(REPO_ROOT), "diff", "--name-only", "HEAD"),
                                 capture_output=True, text=True, errors="replace", check=False).stdout
        untracked = subprocess.run(("git", "-C", str(REPO_ROOT), "ls-files", "--others",
                                    "--exclude-standard"), capture_output=True, text=True, errors="replace", check=False).stdout
        out = tracked + untracked
    return [line.strip().replace("\\", "/") for line in out.splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="*", help="explicit changed paths (default: uncommitted)")
    parser.add_argument("--since", help="compare against this git ref instead of the worktree")
    parser.add_argument("--run", action="store_true", help="print the pytest command instead of the list")
    parser.add_argument("--check", action="store_true", help="also gate the coverage floor")
    args = parser.parse_args(argv)

    tests_per_module, _tests, all_tests = build()
    changed = args.paths or _changed_paths(args.since)
    if not changed:
        print("no changes to measure", file=sys.stderr)
        return 0

    impacted: set[str] = set()
    unseen: list[str] = []
    for raw in changed:
        path = raw.replace("\\", "/")
        if path.startswith("tests/") and path.endswith(".py"):
            if path in {f"tests/{name}" for name in all_tests}:
                impacted.add(Path(path).name)
            continue
        # M8-T183: a change under scripts/ is a change to a module the graph
        # knows, not a path to skip. Before this branch the impact set only
        # understood minicc/, so editing scripts/impacted_tests.py itself printed
        # "no test file reaches the changed paths" while the very same run's
        # --check listed tests/test_impacted_tests.py as its audience. The floor
        # and the impact set disagreed about the same file, and only the half a
        # human reads was wrong.
        if path.startswith(f"{SCRIPTS}/") and path.endswith(".py"):
            module = f"{SCRIPTS}.{Path(path).stem}"
        elif path.startswith(f"{PACKAGE}/") and path.endswith(".py"):
            module = ".".join(Path(path).with_suffix("").parts)
        else:
            continue
        if module not in tests_per_module:
            # A module the graph does not know. Deleted: nothing left to run.
            # New: nobody can see it, which is the finding, not a shrug.
            if (REPO_ROOT / path).exists():
                unseen.append(module)
            continue
        if tests_per_module[module]:
            # Only test files may enter the pytest command. ``audience`` counts a
            # CI workflow as an audience too (M8-T180 - that is what keeps
            # reliability_probe.py off the orphan list), and a workflow name is
            # not a path pytest can collect: printing it produced
            # ``pytest tests/ci.yml``, a command that cannot run. Batch 209
            # stripped it by hand and said nothing, which is how a tool that
            # gates other people's work stays broken.
            impacted |= tests_per_module[module] & all_tests
        else:
            unseen.append(module)

    if unseen:
        print("changed module(s) no test can notice: " + ", ".join(sorted(unseen)), file=sys.stderr)
        return 1

    ordered = sorted(impacted)
    if args.run:
        print("python -m pytest " + " ".join(f"tests/{name}" for name in ordered))
    else:
        for name in ordered:
            print(f"tests/{name}")
    if not ordered:
        print("no test file reaches the changed paths", file=sys.stderr)

    if args.check:
        floor = sorted(name for name, tests in tests_per_module.items()
                       if not tests and name not in EXEMPT
                       and name not in verified_facades())
        if floor:
            print("modules no test reaches: " + ", ".join(floor), file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
