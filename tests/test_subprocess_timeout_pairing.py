"""M2-T10: every subprocess.run given a timeout must catch TimeoutExpired.

The worktree batch (M2-T9) found the one module that set ``timeout=30``
but let ``subprocess.TimeoutExpired`` escape raw, and this audit then
found a second in ``tools/git.py``'s ``merge_precheck``. Both modules'
siblings already caught the ``(OSError, TimeoutExpired)`` pair, so the
convention was real; what was missing was a gate that keeps it from
drifting again. This file is that gate: an AST scan over ``minicc/``
flagging every ``subprocess.run`` call given ``timeout=`` without an
enclosing handler naming ``TimeoutExpired``, plus an explicit, commented
allowlist for the sites whose CALLERS guard them. Scope is ``.run`` only:
it is the shape every current call site uses, and the gate exists to
hold a convention, not to model the subprocess API.
"""

from __future__ import annotations

import ast
from pathlib import Path

import minicc

_PACKAGE_ROOT = Path(minicc.__file__).parent

#: Sites that pass ``timeout=`` but catch ``TimeoutExpired`` in their
#: caller, not in an enclosing try. Key is ``basename:function``; the
#: value names the guard, so a guard removal reddens the citing test
#: before the behavior can silently change.
_HANDLED_UPSTREAM = {
    "bench_tasks.py:_run_grader": (
        "both call sites catch (OSError, subprocess.TimeoutExpired) and "
        "map it to grader_unable"
    ),
    "behavior_bench.py:prepare_fixture": (
        "benchmarks.py's per-task except Exception maps prepare-stage "
        "failures to the named workspace_unwritable NO-RESULT (M8-T107)"
    ),
}

_CAUGHT_BY = {"TimeoutExpired", "SubprocessError", "Exception", "BaseException", "*"}


def _handler_names(handler: ast.ExceptHandler) -> set[str]:
    if handler.type is None:
        return {"*"}
    if isinstance(handler.type, ast.Tuple):
        return {getattr(e, "id", getattr(e, "attr", "?")) for e in handler.type.elts}
    return {getattr(handler.type, "id", getattr(handler.type, "attr", "?"))}


def _timed_run_sites() -> tuple[list[str], set[str]]:
    """Return (offenders, seen allowlist keys) for the minicc/ tree."""
    offenders: list[str] = []
    seen_keys: set[str] = set()
    for path in sorted(_PACKAGE_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        relative = path.relative_to(_PACKAGE_ROOT).as_posix()
        tries: list[ast.Try] = []
        funcs: list[str] = []

        def caught_timeout() -> bool:
            return any(
                _handler_names(handler) & _CAUGHT_BY
                for block in tries
                for handler in block.handlers
            )

        class _Visitor(ast.NodeVisitor):
            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                funcs.append(node.name)
                self.generic_visit(node)
                funcs.pop()

            visit_AsyncFunctionDef = visit_FunctionDef

            def visit_Try(self, node: ast.Try) -> None:
                tries.append(node)
                self.generic_visit(node)
                tries.pop()

            def visit_Call(self, node: ast.Call) -> None:
                func = node.func
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr == "run"
                    and isinstance(func.value, ast.Name)
                    and func.value.id in {"subprocess", "_subprocess", "sp"}
                    and any(kw.arg == "timeout" for kw in node.keywords)
                ):
                    key = f"{path.name}:{funcs[-1] if funcs else '<module>'}"
                    seen_keys.add(key)
                    if not caught_timeout() and key not in _HANDLED_UPSTREAM:
                        offenders.append(f"{relative}:{node.lineno}")
                self.generic_visit(node)

        _Visitor().visit(tree)
    return offenders, seen_keys


def test_every_timed_subprocess_run_catches_timeout_expired() -> None:
    offenders, _ = _timed_run_sites()
    assert not offenders, (
        "subprocess.run(timeout=...) without an enclosing TimeoutExpired "
        f"handler; catch the pair like the sibling modules do, or add the "
        f"caller's guard to _HANDLED_UPSTREAM with its shape quoted: {offenders}"
    )


def test_the_upstream_allowlist_stays_live() -> None:
    """A stale allowlist entry means the guard moved or died: re-check it."""
    _, seen_keys = _timed_run_sites()
    stale = sorted(set(_HANDLED_UPSTREAM) - seen_keys)
    assert not stale, (
        f"_HANDLED_UPSTREAM cites sites that no longer exist: {stale}; "
        "remove them or fix the cited guard"
    )
