"""M8-T609 — the retry budget constants have one home each.

``atomic_file.py`` owns the intra-process answer for a sharing-violated
file (``DEFAULT_ATTEMPTS = 24``, ``DEFAULT_DELAY = 0.05``);
``sidecar_lock.py`` owns the inter-process answer for a cross-process
refusal (``DEFAULT_ATTEMPTS = 40``, ``DEFAULT_DELAY = 0.05``). Both pairs
used to be re-spelled at call sites — catalog/memory each carried their own
``_LOCK_ATTEMPTS = 40`` / ``_LOCK_RETRY_DELAY = 0.05`` fork of the sidecar
answer, and session.py kept its own three copies of the atomic answer —
one for replace, one for read, one for the shared delay, each guaranteed
to drift.

This gate pins:

* the 0.05 delay literal may not appear outside ``atomic_file.py`` and
  ``sidecar_lock.py``;
* no module re-assigns the budget names the homes define;
* session.py's own ``_LOCK_ATTEMPTS`` (the deliberately larger session
  ceiling, 400) is the only one of its kind under minicc/.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOMES = {PACKAGE / "atomic_file.py", PACKAGE / "sidecar_lock.py"}


def test_the_delay_literal_lives_only_in_the_two_homes() -> None:
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        if path in HOMES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value == 0.05:
                offenders.append(f"{path.relative_to(REPO).as_posix()}:{node.lineno}")
    assert offenders == [], (
        "the 0.05 retry delay is spelled outside its two homes - ask "
        "``DEFAULT_DELAY`` instead:\n" + "\n".join(offenders)
    )


def test_no_module_reassigns_the_budget_names() -> None:
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        if path in HOMES:
            continue
        relative = path.relative_to(REPO).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            names = [
                t.id
                for t in (node.targets if isinstance(node, ast.Assign) else [node.target])
                if isinstance(t, ast.Name)
            ]
            for name in names:
                if name in {"DEFAULT_ATTEMPTS", "_LOCK_ATTEMPTS", "_LOCK_RETRY_DELAY", "_READ_ATTEMPTS", "_REPLACE_ATTEMPTS"}:
                    offenders.append(f"{relative}:{node.lineno}: {name}")
    # Only session.py's private deliberate ceiling may keep a lock-attempts symbol.
    offenders = [item for item in offenders if not item.startswith("minicc/session.py:")]
    assert offenders == [], (
        "these modules re-assign a retry budget constant instead of asking "
        "its home:\n" + "\n".join(offenders)
    )


def test_the_session_delta_decision_stays_the_only_one() -> None:
    session = (PACKAGE / "session.py").read_text(encoding="utf-8")
    assert "_LOCK_ATTEMPTS = " in session
    import minicc.session as m
    assert m._LOCK_ATTEMPTS == 400
