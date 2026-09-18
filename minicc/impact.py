"""Bounded, explainable static change impact, without importing workspace code.

Edges point from a source file to files it imports. Reverse breadth-first
traversal explains every recommendation with a shortest dependency chain.
This is a conservative planning aid, never a claim of runtime test coverage.
"""
from __future__ import annotations

import ast
import os
import posixpath
import re
import threading
from collections import OrderedDict, deque
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

_JS_SUFFIXES = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"}
_SUFFIXES = _JS_SUFFIXES | {".py"}
_SKIP_DIRS = {"node_modules", "venv", "__pycache__", "dist", "build", "coverage", "output", "vendor"}
_CACHE: OrderedDict[str, tuple[tuple[int, int, int], "_Parsed"]] = OrderedDict()
_LOCK = threading.Lock()
_MAX_FILE_BYTES = 400_000
_MAX_TOTAL_BYTES = 16_000_000
_MAX_ENTRIES = 30_000
_MAX_CACHE = 4096
_MAX_IMPORTS = 1024


@dataclass(frozen=True)
class _Parsed:
    # Python (module, relative level, imported names); JS (specifier, 0, ()).
    imports: tuple[tuple[str, int, tuple[str, ...]], ...] = ()
    dynamic: int = 0
    error: str = ""
    test_definitions: bool = False


def _python_imports(text: str) -> _Parsed:
    tree = ast.parse(text)
    imports = []
    dynamic = 0
    test_definitions = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            test_definitions = True
        if isinstance(node, ast.Import):
            imports.extend((alias.name, 0, ()) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append((node.module or "", node.level, tuple(alias.name for alias in node.names)))
        elif isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ""
            if name in {"__import__", "import_module"}:
                dynamic += 1
        if len(imports) > _MAX_IMPORTS:
            return _Parsed(tuple(imports[:_MAX_IMPORTS]), dynamic, "import limit reached", test_definitions)
    return _Parsed(tuple(imports), dynamic, test_definitions=test_definitions)


def _js_tokens(text: str) -> list[tuple[str, str]]:
    """Small lexer: retain literal strings but discard comments/templates.

    This deliberately avoids executing JS or loading a compiler from a repo.
    Unsupported syntax and computed imports remain an explicit limitation.
    """
    pattern = re.compile(r"//[^\n]*|/\*[\s\S]*?\*/|`(?:\\[\s\S]|[^`\\])*`|'(?:\\[\s\S]|[^'\\])*'|\"(?:\\[\s\S]|[^\"\\])*\"|[A-Za-z_$][\w$]*|[^\s]", re.ASCII)
    tokens = []
    for match in pattern.finditer(text):
        token = match.group()
        if token.startswith(("//", "/*")):
            continue
        if token[0] == "`":
            tokens.append(("template", ""))
        elif token[0] in "\"'" and len(token) >= 2:
            # Escaped specifiers are unusual; omitting them is safer than
            # inventing a filesystem path with an incomplete JS decoder.
            tokens.append(("string", token[1:-1] if "\\" not in token else ""))
        else:
            tokens.append(("code", token))
    return tokens


def _javascript_imports(text: str) -> _Parsed:
    tokens = _js_tokens(text)
    imports: list[tuple[str, int, tuple[str, ...]]] = []
    dynamic = 0
    for index, (kind, token) in enumerate(tokens):
        if kind != "code" or token not in {"import", "export", "require"}:
            continue
        if index and tokens[index - 1][1] in {".", "?."}:
            continue
        following = tokens[index + 1:index + 3]
        if following and following[0] == ("code", "("):
            # Computed/dynamic imports cannot establish guaranteed edges.
            if token == "import":
                dynamic += 1
            if len(following) == 2 and following[1][0] == "string" and following[1][1]:
                imports.append((following[1][1], 0, ()))
            elif token == "require":
                dynamic += 1
            continue
        if token == "require":
            continue
        if token == "import" and following and following[0][0] == "string":
            if following[0][1]:
                imports.append((following[0][1], 0, ()))
            continue
        # Only scan one declaration. A quoted string is terminal, which
        # prevents an ordinary export expression swallowing a later import.
        for offset in range(index + 1, min(len(tokens) - 1, index + 160)):
            current, after = tokens[offset], tokens[offset + 1]
            if current == ("code", "from") and after[0] == "string":
                if after[1]:
                    imports.append((after[1], 0, ()))
                break
            if current[1] in {";", "import", "export", "="} or current[0] in {"string", "template"}:
                break
        if len(imports) > _MAX_IMPORTS:
            return _Parsed(tuple(imports[:_MAX_IMPORTS]), dynamic, "import limit reached")
    return _Parsed(tuple(dict.fromkeys(imports)), dynamic)


def _parse(path: Path) -> tuple[_Parsed, bool]:
    stat = path.stat()
    signature = (stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size)
    key = str(path)
    with _LOCK:
        cached = _CACHE.get(key)
        if cached and cached[0] == signature:
            _CACHE.move_to_end(key)
            return cached[1], True
    try:
        text = path.read_text(encoding="utf-8-sig")
        parsed = _python_imports(text) if path.suffix == ".py" else _javascript_imports(text)
    except (SyntaxError, UnicodeError, RecursionError, ValueError):
        parsed = _Parsed(error="source could not be parsed")
    after = path.stat()
    if (after.st_mtime_ns, after.st_ctime_ns, after.st_size) != signature:
        return _Parsed(error="source changed during analysis"), False
    with _LOCK:
        _CACHE[key] = (signature, parsed)
        _CACHE.move_to_end(key)
        while len(_CACHE) > _MAX_CACHE:
            _CACHE.popitem(last=False)
    return parsed, False


def _normalized_changes(root: Path, changed_paths: list[str]) -> list[str]:
    if not isinstance(changed_paths, list) or len(changed_paths) > 500:
        raise ValueError("changed_paths must be an array with at most 500 paths")
    result = set()
    for value in changed_paths:
        if not isinstance(value, str) or not value.strip() or len(value) > 2048 or any(ord(char) < 32 for char in value):
            raise ValueError("changed paths must be nonempty relative paths")
        relative = value.replace("\\", "/")
        path = PurePosixPath(relative)
        if path.is_absolute() or PureWindowsPath(value).drive or ".." in path.parts:
            raise ValueError("changed paths must stay within the workspace")
        target = root / path
        if not target.resolve().is_relative_to(root) or target.is_symlink():
            raise ValueError("changed paths must stay within the workspace without symlinks")
        if path.as_posix() != ".":
            result.add(path.as_posix())
    return sorted(result)


def _module_aliases(path: str) -> set[str]:
    name = path[:-3].replace("/", ".")
    if name.endswith(".__init__"):
        name = name[:-9]
    aliases = {name}
    if name.startswith("src."):
        aliases.add(name[4:])
    return aliases


def _python_targets(path: str, parsed: _Parsed, modules: dict[str, set[str]]) -> tuple[set[str], int]:
    targets: set[str] = set()
    unresolved = 0
    package = path[:-3].replace("/", ".").split(".")[:-1]
    for module, level, names in parsed.imports:
        if level:
            if level > len(package):
                unresolved += 1
                continue
            base = ".".join([*package[:len(package) - level + 1], *([module] if module else [])])
        else:
            base = module
        references = {base, *(f"{base}.{name}" for name in names if name != "*")}
        matched = False
        for reference in references:
            for length in range(1, len(reference.split(".")) + 1):
                prefix = ".".join(reference.split(".")[:length])
                for candidate in modules.get(prefix, set()):
                    # Parent packages execute on import; parent plain modules
                    # do not supply arbitrary nested modules.
                    if prefix == reference or candidate.endswith("/__init__.py"):
                        targets.add(candidate)
                        matched = True
        if not matched:
            unresolved += 1
    targets.discard(path)
    return targets, unresolved


def _javascript_targets(path: str, parsed: _Parsed, known: set[str]) -> tuple[set[str], int]:
    targets = set()
    unresolved = 0
    for specifier, _, _ in parsed.imports:
        if not specifier.startswith(("./", "../")):
            unresolved += 1
            continue
        candidate = posixpath.normpath(posixpath.join(posixpath.dirname(path), specifier.split("?")[0].split("#")[0]))
        if candidate.startswith("../") or candidate.startswith("/"):
            unresolved += 1
            continue
        options = [candidate]
        suffix = PurePosixPath(candidate).suffix
        if not suffix:
            options += [candidate + extension for extension in sorted(_JS_SUFFIXES)]
            options += [candidate + "/index" + extension for extension in sorted(_JS_SUFFIXES)]
        elif suffix in {".js", ".jsx", ".mjs", ".cjs"}:
            # TypeScript projects commonly import their emitted .js names.
            options += [candidate[:-len(suffix)] + extension for extension in {".js": (".ts", ".tsx"), ".jsx": (".tsx",), ".mjs": (".mts",), ".cjs": (".cts",)}[suffix]]
        matches = set(options) & known
        if matches:
            targets.update(matches)
        else:
            unresolved += 1
    targets.discard(path)
    return targets, unresolved


def _is_test(path: str, parsed: _Parsed | None = None) -> bool:
    file = PurePosixPath(path)
    if file.suffix == ".py":
        name_matches = file.name.startswith("test_") or file.name.endswith("_test.py")
        test_location = len(file.parts) == 1 or bool(set(file.parts[:-1]) & {"test", "tests", "__tests__"})
        return name_matches and (test_location or bool(parsed and parsed.test_definitions))
    return bool(re.search(r"(?:^|[._-])(?:test|spec|smoke)(?:[._-]|$)", file.stem)) or "__tests__" in file.parts


def analyze_change_impact(workspace: Path | str, changed_paths: list[str], *, limit: int = 200, max_files: int = 4000) -> dict[str, Any]:
    """Return JSON-ready impact paths, test recommendations and honest limits.

    ``changed_paths`` includes deleted files so their remaining importers are
    still found. Results/cache/scanning are bounded and no subprocess runs.
    """
    root = Path(workspace).resolve()
    if not root.is_dir():
        raise ValueError("workspace must be an existing directory")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
        raise ValueError("limit must be between 1 and 500")
    if isinstance(max_files, bool) or not isinstance(max_files, int) or not 1 <= max_files <= 8000:
        raise ValueError("max_files must be between 1 and 8000")
    changed = _normalized_changes(root, changed_paths)
    parsed_files: dict[str, _Parsed] = {}
    warnings: list[dict[str, str]] = []
    scanned = entries = total_bytes = cache_hits = skipped = 0
    scan_truncated = False
    stop = False

    def walk_error(error: OSError) -> None:
        nonlocal skipped
        skipped += 1
        if len(warnings) < 100:
            warnings.append({"path": "", "reason": "directory could not be read"})

    for folder, dirs, files in os.walk(root, onerror=walk_error):
        dirs[:] = sorted(name for name in dirs if not name.startswith(".") and name not in _SKIP_DIRS and not name.endswith(".egg-info") and not (Path(folder) / name).is_symlink())
        entries += len(dirs) + len(files)
        if entries > _MAX_ENTRIES:
            scan_truncated = True
            break
        for name in sorted(files):
            path = Path(folder) / name
            if name.startswith(".") or path.suffix not in _SUFFIXES:
                continue
            if scanned >= max_files:
                scan_truncated = stop = True
                break
            scanned += 1
            relative = path.relative_to(root).as_posix()
            try:
                if path.is_symlink() or not path.resolve().is_relative_to(root):
                    skipped += 1
                    continue
                size = path.stat().st_size
                if size > _MAX_FILE_BYTES:
                    skipped += 1
                    if len(warnings) < 100:
                        warnings.append({"path": relative, "reason": "source exceeds 400 KB"})
                    continue
                total_bytes += size
                if total_bytes > _MAX_TOTAL_BYTES:
                    scan_truncated = stop = True
                    break
                parsed, cached = _parse(path)
                parsed_files[relative] = parsed
                cache_hits += int(cached)
                if parsed.error and len(warnings) < 100:
                    warnings.append({"path": relative, "reason": parsed.error})
            except OSError:
                skipped += 1
                if len(warnings) < 100:
                    warnings.append({"path": relative, "reason": "source could not be read"})
        if stop:
            break
    known = set(parsed_files) | {path for path in changed if PurePosixPath(path).suffix in _SUFFIXES}
    modules: dict[str, set[str]] = {}
    for path in sorted(known):
        if path.endswith(".py"):
            for alias in _module_aliases(path):
                modules.setdefault(alias, set()).add(path)
    reverse: dict[str, set[str]] = {}
    edge_count = unresolved = dynamic = 0
    for path, parsed in parsed_files.items():
        dependencies, missing = _python_targets(path, parsed, modules) if path.endswith(".py") else _javascript_targets(path, parsed, known)
        edge_count += len(dependencies)
        unresolved += missing
        dynamic += parsed.dynamic
        for dependency in dependencies:
            reverse.setdefault(dependency, set()).add(path)

    # Parent pointers keep deep import chains O(files), not O(files squared).
    parents: dict[str, str | None] = {path: None for path in changed}
    distances = dict.fromkeys(changed, 0)
    queue = deque(changed)
    while queue:
        dependency = queue.popleft()
        for dependent in sorted(reverse.get(dependency, set())):
            if dependent in parents:
                continue
            parents[dependent] = dependency
            distances[dependent] = distances[dependency] + 1
            queue.append(dependent)
    affected = sorted((path for path in parents if path not in changed), key=lambda path: (distances[path], path))
    tests = sorted(path for path in parents if path in parsed_files and _is_test(path, parsed_files[path]))
    limitations = [
        "Static imports describe possible impact, not runtime coverage or proof of correctness.",
        "Dynamic imports, reflection, dependency injection, JS aliases and custom Python import roots may be incomplete.",
        "Hidden, generated, dependency and vendor directories are excluded; only Python and JS/TS source is indexed.",
    ]
    if unresolved:
        limitations.append(f"{unresolved} import declarations were external or unresolved locally.")
    if dynamic:
        limitations.append(f"{dynamic} dynamic import calls were observed; computed targets cannot be resolved.")
    if scan_truncated or skipped or warnings:
        limitations.append("Some source could not be analyzed; an empty result does not establish absence of impact.")
    if len(affected) > limit or len(tests) > limit:
        limitations.append("Displayed results are limited; total counts include additional reachable files.")

    def row(path: str) -> dict[str, Any]:
        chain = []
        cursor: str | None = path
        while cursor is not None:
            chain.append(cursor)
            cursor = parents[cursor]
        chain.reverse()
        distance = distances[path]
        return {"path": path, "distance": distance, "chain": chain if len(chain) <= 32 else [*chain[:16], *chain[-16:]], "chain_truncated": len(chain) > 32,
                "reason": "changed test" if distance == 0 else "imports changed code" if distance == 1 else "transitive import dependency", "is_test": _is_test(path, parsed_files.get(path))}

    return {
        "schema_version": 1,
        "changed_paths": changed,
        "impacted_files": [row(path) for path in affected[:limit]],
        "recommended_tests": [row(path) for path in tests[:limit]],
        "stats": {"scanned_files": scanned, "indexed_files": len(parsed_files), "edges": edge_count, "cache_hits": cache_hits,
                  "impacted_files": len(affected), "recommended_tests": len(tests), "unresolved_imports": unresolved,
                  "dynamic_imports": dynamic, "skipped_files": skipped},
        "truncated": scan_truncated or len(affected) > limit or len(tests) > limit,
        "analysis_incomplete": scan_truncated or bool(skipped or warnings or dynamic),
        "warnings": warnings,
        "limitations": limitations,
    }
