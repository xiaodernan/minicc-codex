"""M8-T422 — 授权审计事件八键两个家：to_event 与 planner 白名单门各写一份"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "minicc"
HOME = "minicc/audit.py"

FIELDS = {
    "authorization", "code", "kind", "name",
    "phase", "risk", "status", "summary",
}


def test_the_home_builds_the_event() -> None:
    """The constructor owns the eight keys and fixes the two invariants."""
    from minicc.audit import authorization_event

    event = authorization_event(
        "bash",
        status="denied",
        code="planner_tool_out_of_scope",
        summary="not on the list",
        risk="exec",
        authorization="planner_whitelist",
    )
    assert set(event) == FIELDS
    assert event["kind"] == "authorization"
    assert event["phase"] == "permission"
    assert event["name"] == "bash"
    assert event["status"] == "denied"


def test_the_eight_keys_are_spelled_exactly_once_in_the_package() -> None:
    """Zero hand spellings outside the home, one shape inside it.

    The T422 signature was ``FIELDS`` spelled exactly once (in the home).
    Batch 566 gave the record one home in ``trace.py`` with a ``kind``
    parameter, so the home now spells ``"kind": kind`` via the home instead
    of a literal - and an 8-key ``FIELDS`` literal anywhere in the package,
    inside the home included, is a hand-copied record again.
    """
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
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
            if keys == FIELDS:
                offenders.append(f"{relative}:{node.lineno}")
    assert offenders == [], (
        "the authorization event is spelled by hand outside its one "
        "home: " + ", ".join(offenders)
    )
    source = (REPO / HOME).read_text(encoding="utf-8")
    assert 'kind="authorization"' in source, (
        "the home no longer asks the trace home for the authorization kind"
    )
    assert 'event["authorization"] = authorization' in source, (
        "the home stopped attaching its own flat extras"
    )


def test_every_site_asks_the_home() -> None:
    """to_event derives from the home; web.py's gate calls it directly."""
    from minicc.audit import AuthorizationDecision

    decision = AuthorizationDecision(
        allowed=False, risk="exec", reason="nope", authorization="plan_mode_exec"
    )
    event = decision.to_event("bash")
    assert event["kind"] == "authorization"
    assert event["code"] == "tool_denied_by_policy"
    assert event["authorization"] == "plan_mode_exec"

    audit_source = (REPO / HOME).read_text(encoding="utf-8")
    assert audit_source.count("authorization_event(") == 2, (
        "the definition plus to_event's call are the only spellings in "
        f"audit.py, found {audit_source.count('authorization_event(')}"
    )
    web_source = (REPO / "minicc/web.py").read_text(encoding="utf-8")
    assert web_source.count("authorization_event(") == 1, (
        "the planner whitelist gate must call the home exactly once, "
        f"found {web_source.count('authorization_event(')}"
    )
