"""A handler that swallows everything must say why, in the same breath.

The eight fail-open sites M8-T117..T125 closed were all of one shape: an ``except
Exception`` whose body hides the failure. Not every such handler is a defect - a
status listener, a logger and a best-effort teardown must not take the run down with
them - and the codebase already says so at 14 of 17 sites. The other three did not:

* ``minicc/main.py``: the ``/status`` command printed nothing when the provider could
  not report its channel, which is indistinguishable from the ``callable`` branch that
  means "this build has no channel status". It now names the failure (type only, since
  provider text can carry a URL) - that one was a real defect, not a wording gap.
* ``minicc/llm/anthropic_provider.py`` and ``minicc/web.py``: both are legitimate
  boundaries and now state it.

Why a gate rather than a one-off sweep: the sweep is only true until the next handler
is written, and the cost of a wrong one is exactly the class this milestone spent
eight batches closing. The rule is deliberately narrow so it cannot become noise - it
asks about the *broadest* handlers (bare, ``Exception``, ``BaseException``) whose body
is a single silent statement, not about every ``except``.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AUDITED_DIRS = ("minicc", "scripts")

#: Measured on the plane this gate landed on: 17 broad silent handlers, 14 with a stated
#: reason, 3 without. The three were then dealt with, which moved the count to **16**: the
#: ``/status`` handler in ``minicc/main.py`` stopped being silent (it reports the failure
#: now), so it left this population, while the other two only gained a stated reason. The
#: floor is the anti-vacuity arm: a walker that stops finding handlers reports a pass.
MIN_HANDLERS = 16

SILENT_BODIES = (ast.Pass, ast.Continue, ast.Return)


def _sources() -> list[Path]:
    files: list[Path] = []
    for directory in AUDITED_DIRS:
        files.extend(
            sorted(path for path in (REPO_ROOT / directory).rglob("*.py") if "__pycache__" not in path.parts)
        )
    return files


def _is_broad(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    rendered = ast.unparse(handler.type)
    return rendered in {"Exception", "BaseException"} or "Exception" in rendered


def _is_silent(handler: ast.ExceptHandler) -> bool:
    return len(handler.body) == 1 and isinstance(handler.body[0], SILENT_BODIES)


def _states_a_reason(handler: ast.ExceptHandler, lines: list[str]) -> bool:
    """A reason is a ``# noqa: BLE001 - <why>`` on the handler line, or a comment inside it.

    Comments do not survive parsing, so this reads the source lines the handler spans -
    from the ``except`` line through the end of its body. A trailing comment on the
    silent statement counts too.
    """
    head = lines[handler.lineno - 1]
    if "noqa: BLE001" in head and "-" in head.split("BLE001")[-1]:
        return True
    last = max((statement.end_lineno or statement.lineno) for statement in handler.body)
    for line in lines[handler.lineno - 1 : last]:
        stripped = line.strip()
        if stripped.startswith("#"):
            return True
        if "#" in stripped and not stripped.startswith(("pass", "return", "continue")):
            return True
    return False


def _audit() -> tuple[list[str], list[str]]:
    """Return (handlers seen, offenders). Both are repo-relative ``path:line`` strings."""
    seen: list[str] = []
    offenders: list[str] = []
    for path in _sources():
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            if not (_is_broad(node) and _is_silent(node)):
                continue
            where = f"{path.relative_to(REPO_ROOT).as_posix()}:{node.lineno}"
            seen.append(where)
            if not _states_a_reason(node, lines):
                offenders.append(where)
    return seen, offenders


def test_every_broad_silent_handler_states_a_reason() -> None:
    seen, offenders = _audit()
    assert len(seen) >= MIN_HANDLERS, (
        f"only {len(seen)} broad silent handlers found, below the measured {MIN_HANDLERS} - "
        f"the walker is looking at the wrong shape, not at a clean tree: {seen}"
    )
    assert offenders == [], (
        "these handlers swallow every exception and say nothing about why; either state the "
        "boundary (a status listener, a logger, a best-effort teardown) or stop swallowing: "
        f"{offenders}"
    )
