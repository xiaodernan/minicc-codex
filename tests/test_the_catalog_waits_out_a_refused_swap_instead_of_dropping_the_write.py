"""M8-T523: a refused swap is a moment, not an answer.

On Windows a destination that another handle still has open makes
``os.replace`` fail with ``PermissionError`` (WinError 5) for as long as that
handle is open - microseconds for a reader that is mid-read.  The file on disk
is always one complete version, so "the operation was refused for a moment" is
not a reason to report "the write did not happen" or "the catalog is empty".

The workspace catalog had no answer to that window at all:

* ``_write`` called ``os.replace`` once.  One refusal dropped the write with a
  warning - the recently-opened folder simply never appears, and the caller
  (the web server's service object, the task worker, the benchmark runner) is
  never told.
* ``_read`` caught ``OSError`` and returned ``[]``.  One refusal on the read
  side made the whole recent-folder list come back empty.

Three call sites in this repository had three different answers to one
question: ``minicc/session.py`` rode it out (flat 24 x 50ms), ``minicc/webauth.py``
rode it out (8 attempts, growing backoff), and ``minicc/workspaces.py`` had none.
``minicc/atomic_file.py`` is now the one answer; the budgets stay with the call
sites, because they are not the same decision.

What this does NOT claim: the retry rides out a *transient* refusal.  A
destination that stays refused still fails, still degrades (the catalog never
raises on this path - M8-T265 established that), and still says so in one
warning naming the catalog.
"""

from __future__ import annotations

import ast
import errno
import json
import logging
import os
from pathlib import Path

import pytest

from minicc.workspaces import WorkspaceCatalog

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "minicc"
CATALOG_NAME = "workspaces.json"
LOGGER_NAME = "minicc.workspaces"


def _catalog(root: Path) -> WorkspaceCatalog:
    return WorkspaceCatalog(path=root / CATALOG_NAME)


def _workspace(root: Path, name: str) -> Path:
    target = root / name
    target.mkdir(parents=True, exist_ok=True)
    return target


def _seed(root: Path, entries: int = 1) -> Path:
    """A catalog file with a known, complete list already in it."""
    root.mkdir(parents=True, exist_ok=True)
    catalog = root / CATALOG_NAME
    payload = [{"name": f"old{i}", "path": f"/nowhere{i}", "last_opened": 1.0} for i in range(entries)]
    catalog.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    return catalog


def test_a_swap_refused_once_still_lands_the_write(tmp_path: Path, monkeypatch) -> None:
    """The refusal is a moment; the write must survive it."""
    catalog_path = _seed(tmp_path)
    real = os.replace
    calls: list[str] = []

    def flaky(source, target, *args, **kwargs):
        calls.append(str(target))
        if len(calls) == 1:
            raise PermissionError(errno.EACCES, "模拟一次共享冲突")
        return real(source, target, *args, **kwargs)

    monkeypatch.setattr(os, "replace", flaky)
    target = _workspace(tmp_path, "ws")
    _catalog(tmp_path).remember(target)

    assert len(calls) >= 2, calls
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    # The seeded entry is still there; the new one is in front of it.
    assert [item["path"] for item in payload] == [target.as_posix(), "/nowhere0"], payload


def test_a_swap_refused_for_the_whole_budget_is_a_warning_and_no_raise(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    """When the destination stays refused the catalog degrades, loudly."""
    catalog_path = _seed(tmp_path)
    before = catalog_path.read_text(encoding="utf-8")

    def always_refused(source, target, *args, **kwargs):
        raise PermissionError(errno.EACCES, "目的地一直被占着")

    monkeypatch.setattr(os, "replace", always_refused)
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        _catalog(tmp_path).remember(_workspace(tmp_path, "ws"))

    warnings = [r for r in caplog.records if r.name == LOGGER_NAME and r.levelno == logging.WARNING]
    assert len(warnings) == 1, f"expected one warning, got {len(warnings)}"
    message = warnings[0].getMessage()
    assert CATALOG_NAME in message, message
    assert "目的地一直被占着" in message, message
    assert catalog_path.read_text(encoding="utf-8") == before, (
        "a refused swap rewrote the catalog it could not replace"
    )


def test_a_read_refused_once_still_returns_the_catalog(tmp_path: Path, monkeypatch) -> None:
    """The read side has the same window, and the same wrong answer to avoid."""
    catalog_path = _seed(tmp_path, entries=2)
    real = Path.read_text
    calls: list[Path] = []

    def flaky(self, *args, **kwargs):
        calls.append(self)
        if len(calls) == 1:
            raise PermissionError(errno.EACCES, "模拟一次共享冲突")
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", flaky)
    items = _catalog(tmp_path).list()
    assert len(items) == 2, items
    assert len(calls) >= 2, calls


def test_a_read_refused_for_the_whole_budget_degrades_to_empty_without_raising(
    tmp_path: Path, monkeypatch
) -> None:
    """The catalog promises it never raises on this path - it must keep promising."""
    _seed(tmp_path, entries=2)

    def always_refused(self, *args, **kwargs):
        raise PermissionError(errno.EACCES, "文件一直被占着")

    monkeypatch.setattr(Path, "read_text", always_refused)
    assert _catalog(tmp_path).list() == []


def test_a_refused_swap_leaves_no_staging_file_behind(tmp_path: Path, monkeypatch) -> None:
    """The next writer must not find our leftovers where it looks."""
    _seed(tmp_path)

    def always_refused(source, target, *args, **kwargs):
        raise PermissionError(errno.EACCES, "目的地一直被占着")

    monkeypatch.setattr(os, "replace", always_refused)
    _catalog(tmp_path).remember(_workspace(tmp_path, "ws"))
    leftovers = sorted(p.name for p in tmp_path.glob("*.tmp"))
    assert not leftovers, f"staging files outlived the refusal: {leftovers}"


def test_a_plain_write_still_lands_and_reads_back(tmp_path: Path) -> None:
    """Control: the retry must not change what an untroubled write does."""
    catalog_path = _seed(tmp_path, entries=0)
    target = _workspace(tmp_path, "ws")
    catalog = _catalog(tmp_path)
    catalog.remember(target)
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    assert [item["path"] for item in payload] == [target.as_posix()], payload
    assert [item["path"] for item in catalog.list()] == [target.as_posix()]


def _modules() -> dict[str, ast.Module]:
    trees: dict[str, ast.Module] = {}
    for path in sorted(PACKAGE_ROOT.glob("*.py")):
        try:
            trees[path.name] = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
    return trees


def _calls_os_replace(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "replace"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "os"
        ):
            return True
    return False


def _is_permission_error(handler: ast.ExceptHandler) -> bool:
    return isinstance(handler.type, ast.Name) and handler.type.id == "PermissionError"


def _retry_shapes(tree: ast.Module) -> list[str]:
    """The shapes that mean "ride out a sharing violation" - written out by hand.

    Two of them: a loop that retries the swap, and a handler that catches
    ``PermissionError`` around a swap or a read.  A plain ``os.replace`` is
    neither - it is an atomic write, and whether *that* write needs to ride
    out a refusal is a separate question this batch does not answer.
    """
    shapes: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        if not any(_is_permission_error(h) for h in node.handlers):
            continue
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Call):
                continue
            func = inner.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "replace"
                and isinstance(func.value, ast.Name)
                and func.value.id == "os"
            ):
                shapes.append(f"os.replace at line {inner.lineno}")
            elif isinstance(func, ast.Attribute) and func.attr == "read_text":
                shapes.append(f"read_text at line {inner.lineno}")
    return shapes


def test_one_repository_one_answer_to_the_sharing_violation() -> None:
    """Four call sites had four answers; there is now one mechanism.

    Structural, because the behavioural gates cannot see a second copy: a
    second copy of this handler is correct code that quietly becomes the third
    answer the next time somebody changes the budget somewhere else.
    """
    trees = _modules()
    assert "atomic_file.py" in trees, sorted(trees)

    atomic = trees["atomic_file.py"]
    defined = {
        node.name
        for node in ast.walk(atomic)
        if isinstance(node, ast.FunctionDef) and node.name in {"replace_with_retry", "read_text_with_retry"}
    }
    assert defined == {"replace_with_retry", "read_text_with_retry"}, defined

    # The mechanism itself may only live in one place.
    copies = sorted(name for name, tree in trees.items() if _retry_shapes(tree))
    assert copies == ["atomic_file.py"], (
        f"these modules keep their own answer to the sharing violation: {copies}"
    )

    # And the call sites must actually import the one answer.
    for name in ("session.py", "webauth.py", "workspaces.py", "bench_tasks.py"):
        source = trees[name]
        imported = set()
        for node in ast.walk(source):
            if isinstance(node, ast.ImportFrom) and node.module == "atomic_file":
                imported.update(alias.name for alias in node.names)
        assert imported, f"{name} does not import the shared helpers"


def test_the_shared_helper_rides_out_a_refusal_and_gives_up_loudly(tmp_path: Path) -> None:
    """The helper itself: ride it out, then raise the last refusal."""
    from minicc.atomic_file import replace_with_retry

    source = tmp_path / "source.txt"
    target = tmp_path / "target.txt"
    source.write_text("new\n", encoding="utf-8")
    target.write_text("old\n", encoding="utf-8")

    real = os.replace
    calls: list[int] = []

    def flaky(src, dst, *args, **kwargs):
        calls.append(1)
        if len(calls) < 3:
            raise PermissionError(errno.EACCES, "模拟共享冲突")
        return real(src, dst, *args, **kwargs)

    os.replace = flaky
    try:
        replace_with_retry(source, target, attempts=8, delay=0.0)
    finally:
        os.replace = real
    assert len(calls) == 3, calls
    assert target.read_text(encoding="utf-8") == "new\n"

    source.write_text("newer\n", encoding="utf-8")

    def always_refused(src, dst, *args, **kwargs):
        raise PermissionError(errno.EACCES, "一直拒绝")

    os.replace = always_refused
    try:
        with pytest.raises(PermissionError):
            replace_with_retry(source, target, attempts=3, delay=0.0)
    finally:
        os.replace = real


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q", "-W", "error"]))
