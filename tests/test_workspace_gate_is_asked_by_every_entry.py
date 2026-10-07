"""The single workspace gate must be asked by every declared entry (M2-T1 wiring).

``minicc.workspaces.resolve_workspace_path`` is the only spot that enforces
``workspace_roots``. This file adds two witnesses the perimeter suite lacks:

* an AST census binding each declared entry — web.py ``_rpc_workspace_path`` /
  ``switch_workspace`` / ``restore_task_snapshot`` / ``_run_chat`` and
  task_manager.py ``_workspace_path`` — to an actual call inside its own body,
  the reverse direction (no call site outside the table) and the package-wide
  importer census. The older count-only gate in test_security_perimeter.py
  (``>= 4`` textual hits) stayed green when any single call site was deleted,
  because the true count had grown to 5.
* the behaviour row for ``AgentService.restore_task_snapshot`` — the one entry
  whose roots refusal had no witness anywhere, and the entry that writes
  captured bytes back to disk.
"""

from __future__ import annotations

import ast
import subprocess
import threading
import types
from pathlib import Path

import pytest

import minicc
import minicc.task_manager
import minicc.web
from minicc.config import Config
from minicc.snapshots import capture, snapshot_dir
from minicc.web import AgentService

# Every function the single workspace gate must be asked by, as
# (module file relative to the package, function name inside it).
DECLARED_ENTRIES: set[tuple[str, str]] = {
    ("web.py", "_rpc_workspace_path"),
    ("web.py", "switch_workspace"),
    ("web.py", "restore_task_snapshot"),
    ("web.py", "_run_chat"),
    ("task_manager.py", "_workspace_path"),
}


def _package_root() -> Path:
    root = Path(minicc.__file__).parent
    assert (root / "workspaces.py").is_file(), f"package root not found: {root}"
    return root


def _module_file(module: object) -> Path:
    path = Path(getattr(module, "__file__", "") or "")
    assert path.is_file(), f"module file not found: {path!r}"
    return path


def _parse(path: Path) -> ast.Module:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    assert tree.body, f"{path}: parsed to an empty module — the census would read nothing"
    return tree


def _imports_resolver(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in ("workspaces", "minicc.workspaces"):
            if any(alias.name == "resolve_workspace_path" for alias in node.names):
                return True
    return False


def _resolver_callers(path: Path) -> dict[str, int]:
    """Qualname of the nearest enclosing def -> count, for every resolver call."""
    calls: dict[str, int] = {}

    def walk(node: ast.AST, enclosing: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                walk(child, f"{enclosing}.{child.name}" if enclosing else child.name)
            else:
                if isinstance(child, ast.Call):
                    func = child.func
                    name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
                    if name == "resolve_workspace_path":
                        key = enclosing or "(module level)"
                        calls[key] = calls.get(key, 0) + 1
                walk(child, enclosing)

    walk(_parse(path), "")
    return calls


def _calls_by_file() -> dict[str, dict[str, int]]:
    root = _package_root()
    out: dict[str, dict[str, int]] = {}
    for module in (minicc.web, minicc.task_manager):
        rel = _module_file(module).relative_to(root).as_posix()
        out[rel] = _resolver_callers(root / rel)
    assert out, "census read no modules"
    return out


def _belongs_to_declared(rel: str, key: str) -> bool:
    return any(
        rel == decl_rel and (key == func or key.startswith(func + "."))
        for decl_rel, func in DECLARED_ENTRIES
    )


def test_web_and_task_manager_import_the_shared_resolver() -> None:
    for module in (minicc.web, minicc.task_manager):
        path = _module_file(module)
        assert _imports_resolver(_parse(path)), (
            f"{path.name} no longer imports resolve_workspace_path from minicc.workspaces — "
            "a same-named local function would satisfy the call census without the shared gate"
        )


def test_every_declared_entry_contains_a_resolver_call() -> None:
    calls = _calls_by_file()
    missing = [
        f"{rel}::{func}"
        for rel, func in sorted(DECLARED_ENTRIES)
        if not any(key == func or key.startswith(func + ".") for key in calls.get(rel, {}))
    ]
    assert not missing, (
        "these entries no longer ask the shared workspace gate (a workspace_roots "
        f"bypass is now reachable through them): {missing}"
    )


def test_no_resolver_call_site_lives_outside_the_declared_entries() -> None:
    undeclared = [
        f"{rel}::{key}"
        for rel, by_func in _calls_by_file().items()
        for key in by_func
        if not _belongs_to_declared(rel, key)
    ]
    assert not undeclared, (
        f"resolve_workspace_path is called from undeclared place(s): {undeclared} — "
        "declare them in DECLARED_ENTRIES (with a roots refusal witness) or drop the call"
    )


def test_no_undeclared_module_imports_the_resolver() -> None:
    root = _package_root()
    importers = {
        path.relative_to(root).as_posix()
        for path in sorted(root.rglob("*.py"))
        if _imports_resolver(_parse(path))
    }
    declared_files = {rel for rel, _ in DECLARED_ENTRIES}
    assert importers == declared_files, (
        "the set of minicc modules importing the shared workspace gate moved: "
        f"importers={sorted(importers)} declared={sorted(declared_files)}"
    )


def _git(workspace: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _init_repo(workspace: Path) -> None:
    _git(workspace, "init")
    _git(workspace, "config", "user.email", "minicc@example.test")
    _git(workspace, "config", "user.name", "minicc")
    (workspace / "tracked.txt").write_text("v1\n", encoding="utf-8")
    _git(workspace, "add", "tracked.txt")
    _git(workspace, "commit", "-m", "init")


def _service(workspace: Path, roots: tuple[Path, ...], monkeypatch: pytest.MonkeyPatch) -> AgentService:
    home = workspace.parent / "home"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("MINICC_HOME", str(home))
    config = Config(
        base_url="https://example.test/v1",
        api_key="test-key",
        model="test-model",
        sandbox_mode="host",
        sandbox_image="python:3.11-slim",
        workspace_roots=roots,
    )
    return AgentService(workspace, config)


def _fake_tasks(record: dict[str, object]) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        lock=threading.RLock(),
        get=lambda task_id: dict(record, task_id=task_id),
        has_active=lambda workspace: False,
    )


def test_restore_refuses_a_snapshot_recorded_outside_the_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    _init_repo(outside)
    (outside / "tracked.txt").write_text("v2\n", encoding="utf-8")
    capture(outside, "outside-task")
    assert snapshot_dir(outside, "outside-task").is_dir(), (
        "precondition: the snapshot must exist before its refusal — otherwise a "
        "missing-snapshot error could masquerade as the roots refusal"
    )
    (outside / "tracked.txt").write_text("v3-must-survive\n", encoding="utf-8")

    service = _service(allowed, roots=(allowed,), monkeypatch=monkeypatch)
    real_tasks = service.tasks
    try:
        service.tasks = _fake_tasks({"workspace_path": str(outside)})
        with pytest.raises(ValueError, match="白名单"):
            service.restore_task_snapshot("outside-task")
        assert (outside / "tracked.txt").read_text(encoding="utf-8") == "v3-must-survive\n", (
            "the refusal must happen before any write-back into the recorded workspace"
        )
    finally:
        service.tasks = real_tasks
        service.shutdown()


def test_restore_restores_into_the_recorded_workspace_when_inside_the_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    allowed = tmp_path / "allowed"
    main = allowed / "main"
    sub = allowed / "sub"
    main.mkdir(parents=True)
    sub.mkdir()
    _init_repo(sub)
    (sub / "tracked.txt").write_text("v2\n", encoding="utf-8")
    capture(sub, "sub-task")
    (sub / "tracked.txt").write_text("v3-should-revert\n", encoding="utf-8")

    service = _service(main, roots=(allowed,), monkeypatch=monkeypatch)
    real_tasks = service.tasks
    try:
        service.tasks = _fake_tasks({"workspace_path": str(sub)})
        outcome = service.restore_task_snapshot("sub-task")
        assert "tracked.txt" in outcome["restored"]
        assert (sub / "tracked.txt").read_text(encoding="utf-8") == "v2\n", (
            "the restore must land in the recorded (resolved) workspace"
        )
        assert not (main / "tracked.txt").exists(), (
            "the service's own workspace is not the recorded one and must stay untouched"
        )
    finally:
        service.tasks = real_tasks
        service.shutdown()
