"""M8-T566 — the verification event is the one record, asked for by kind.

``trace.py`` pinned ``kind="trace"`` with no parameter, so the verifier
could not ask the home for a ``"verification"`` record and spelled the
seven-key shape by hand - leaving two homes for one shape, six months
apart from the same fix that had just collapsed the other forty-six.

The home now knows kinds (``"trace"`` is still the default, byte-for-byte)
and the verifier asks for ``kind="verification"`` and adds its flat
extras at the mint site.  This gate pins:

* the home builds any kind, with the same seven keys and order;
* the verifier asks the home;
* no module in the package spells the six-key core of the record
  outside the home.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME_FILE = "minicc/trace.py"
CORE = {"kind", "name", "status", "phase", "code", "summary"}


def _read(relative: str) -> str:
    return (REPO / relative).read_text(encoding="utf-8")


def test_the_home_builds_any_kind() -> None:
    from minicc.trace import trace_event

    event = trace_event(
        name="verifier", status="ok", phase="verify",
        code="verification_passed", summary="验证通过: pytest -q",
        kind="verification", detail={"checks": []},
    )
    assert list(event) == ["kind", "name", "status", "phase", "code", "summary", "detail"]
    assert event["kind"] == "verification"
    # The default kind is unchanged and kind-less callers get the old shape.
    assert trace_event("a", "ok", "planning", "milestone", "s")["kind"] == "trace"


def test_the_verifier_asks_the_home() -> None:
    source = _read("minicc/agent/verifier.py")
    assert "trace_event(" in source, "the verifier must ask the one home for the record"
    assert '"kind": "verification"' not in source, (
        "the verifier spells the record inline instead of asking the home"
    )


def test_no_module_spells_the_six_key_core_inline() -> None:
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_bytes().decode("utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        relative = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            keys = {
                key.value
                for key in node.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
            if CORE <= keys:
                offenders.append(f"{relative}:{node.lineno}")
    assert all(o.startswith(HOME_FILE + ":") for o in offenders), (
        "the six-key core of the event record is spelled outside its one "
        f"home ({HOME_FILE}): " + ", ".join(offenders)
    )
    assert len(offenders) == 1, offenders
